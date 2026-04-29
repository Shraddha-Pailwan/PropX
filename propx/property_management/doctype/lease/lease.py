import frappe
from frappe.model.document import Document
from frappe.utils import add_days, add_months, date_diff, getdate, today, flt
from dateutil.relativedelta import relativedelta


class Lease(Document):

    # ── VALIDATION ────────────────────────────────────────────────

    def validate(self):
        self.validate_dates()
        self.fetch_unit_defaults()
        self.calculate_financial_fields()
        self.validate_unit_availability()
        self.auto_generate_pdc_schedule()
        self.check_rera_rent_cap()
        self.calculate_lease_duration()

    def validate_dates(self):
        if self.start_date and self.end_date:
            if getdate(self.end_date) <= getdate(self.start_date):
                frappe.throw("End Date must be after Start Date.")

    def fetch_unit_defaults(self):
        if not self.unit:
            return
        unit = frappe.get_doc("Property Unit", self.unit)
        self.property = unit.property
        self.usage_type = unit.usage_type
        self.is_vat_applicable = unit.is_vat_applicable

    def calculate_financial_fields(self):
        if not self.annual_rent:
            return
        self.monthly_rent = round(flt(self.annual_rent) / 12, 2)
        country = (
            frappe.db.get_value("Property", self.property, "country")
            if self.property else None
        )
        vat_rates = {
            "United Arab Emirates": 5 if self.is_vat_applicable else 0,
            "Saudi Arabia": 15,
            "Oman": 5 if self.is_vat_applicable else 0,
        }
        self.vat_rate = vat_rates.get(country or "", 0)
        self.vat_amount_annual = round(
            flt(self.annual_rent) * self.vat_rate / 100, 2
        )
        self.total_with_vat = flt(self.annual_rent) + flt(self.vat_amount_annual)

    def validate_unit_availability(self):
        if self.status in ["Draft", "Cancelled"]:
            return
        if not self.unit:
            return
        conflict = frappe.db.sql("""
            SELECT name FROM `tabLease`
            WHERE unit = %(unit)s
              AND name != %(name)s
              AND status IN ('Active', 'Expiring', 'Renewed')
              AND NOT (end_date < %(start)s OR start_date > %(end)s)
        """, {
            "unit": self.unit,
            "name": self.name or "NEW",
            "start": self.start_date,
            "end": self.end_date
        })
        if conflict:
            frappe.throw(
                f"Unit {self.unit} has an overlapping active lease: {conflict[0][0]}"
            )

    def auto_generate_pdc_schedule(self):
        """Generate PDC rows only when the table is empty."""
        if self.pdc_schedule or not self.annual_rent:
            return
        if not self.number_of_cheques or not self.start_date:
            return
        n = int(self.number_of_cheques)
        cheque_amount = round(flt(self.annual_rent) / n, 2)
        months_gap = 12 // n
        for i in range(n):
            due = add_months(self.start_date, i * months_gap)
            p_from = add_months(self.start_date, i * months_gap)
            p_to = add_days(add_months(self.start_date, (i + 1) * months_gap), -1)
            self.append("pdc_schedule", {
                "amount": cheque_amount,
                "due_date": due,
                "period_from": p_from,
                "period_to": p_to,
                "cheque_status": "Pending"
            })

    def check_rera_rent_cap(self):
        """UAE: Warn if renewal rent exceeds RERA-allowed increase cap."""
        if not self.parent_lease or not self.annual_rent:
            return
        country = frappe.db.get_value("Property", self.property, "country") if self.property else None
        if country != "United Arab Emirates":
            return
        if self.rera_current_rent and self.rera_allowed_increase_pct:
            max_rent = flt(self.rera_current_rent) * (
                1 + flt(self.rera_allowed_increase_pct) / 100
            )
            if flt(self.annual_rent) > max_rent:
                frappe.msgprint(
                    f"RERA Warning: Proposed rent AED {self.annual_rent:,.0f} "
                    f"exceeds maximum allowed AED {max_rent:,.0f} "
                    f"({self.rera_allowed_increase_pct}% increase cap). "
                    f"Check RERA Rental Index before proceeding.",
                    indicator="orange",
                    title="RERA Rent Cap Alert"
                )

    def calculate_lease_duration(self):
        if self.start_date and self.end_date:
            d = relativedelta(getdate(self.end_date), getdate(self.start_date))
            self.lease_duration_months = d.years * 12 + d.months

    # ── SUBMIT / CANCEL ───────────────────────────────────────────

    def before_submit(self):
        self._generate_escalation_schedule()

    def on_submit(self):
        self._set_unit_occupied()
        self._create_pdc_register_entries()

    def on_cancel(self):
        self._set_unit_vacant()

    def _set_unit_occupied(self):
        if not self.unit:
            return
        frappe.db.set_value("Property Unit", self.unit, {
            "status": "Occupied",
            "current_lease": self.name,
            "current_tenant": self.tenant,
            "vacancy_since": None,
            "days_vacant": 0
        })

    def _set_unit_vacant(self):
        if not self.unit:
            return
        frappe.db.set_value("Property Unit", self.unit, {
            "status": "Vacant",
            "current_lease": None,
            "current_tenant": None,
            "vacancy_since": today()
        })

    def _create_pdc_register_entries(self):
        frappe.enqueue(
            "propx.property_management.utils.billing_utils.create_pdc_entries",
            lease=self.name,
            queue="default",
            timeout=120
        )

    def _generate_escalation_schedule(self):
        """Auto-populate escalation rows if escalation is configured."""
        if not self.has_rent_escalation or not self.escalation_frequency_months:
            return
        if self.escalation_schedule:
            return
        freq = int(self.escalation_frequency_months)
        current_rent = flt(self.annual_rent)
        esc_date = add_months(self.start_date, freq)
        rows = []
        while getdate(esc_date) < getdate(self.end_date):
            if self.escalation_type == "Fixed %":
                new_rent = round(
                    current_rent * (1 + flt(self.escalation_pct) / 100), 2
                )
            else:
                new_rent = current_rent  # updated manually for CPI/RERA
            rows.append({
                "escalation_date": esc_date,
                "from_rent": current_rent,
                "to_rent": new_rent,
                "escalation_type": self.escalation_type,
                "change_pct": self.escalation_pct or 0,
                "applied": 0
            })
            current_rent = new_rent
            esc_date = add_months(esc_date, freq)
        for r in rows:
            self.append("escalation_schedule", r)

    # ── WHITELIST METHODS ─────────────────────────────────────────

    @frappe.whitelist()
    def initiate_renewal(self):
        """Create a draft renewal lease pre-filled from this one."""
        if self.status not in ["Active", "Expiring"]:
            frappe.throw("Can only renew an Active or Expiring lease.")

        new_lease = frappe.copy_doc(self)
        new_lease.status = "Draft"
        new_lease.start_date = add_days(self.end_date, 1)
        new_lease.end_date = add_months(new_lease.start_date, 12)
        new_lease.parent_lease = self.name
        new_lease.ejari_contract_no = None
        new_lease.ejari_status = "Not Filed"
        new_lease.pdc_schedule = []
        new_lease.escalation_schedule = []
        new_lease.renewal_status = None
        new_lease.signed_contract = None
        new_lease.esign_status = "Not Sent"
        new_lease.esign_request_id = None
        new_lease.insert()

        frappe.db.set_value("Lease", self.name, "renewal_status", "Offer Sent")
        return new_lease.name

    @frappe.whitelist()
    def terminate_early(self, termination_date, reason):
        """Terminate lease before end_date and calculate penalty."""
        days_remaining = date_diff(self.end_date, termination_date)
        penalty = 0
        if days_remaining > 0 and self.break_penalty_months:
            penalty = round(
                flt(self.monthly_rent) * int(self.break_penalty_months), 2
            )
        frappe.db.set_value("Lease", self.name, {
            "status": "Terminated",
            "end_date": termination_date
        })
        self.add_comment(
            "Info",
            f"Early termination on {termination_date}. "
            f"Reason: {reason}. Penalty: AED {penalty:,.2f}"
        )
        self._set_unit_vacant()
        return {"penalty": penalty, "days_remaining": days_remaining}

    @frappe.whitelist()
    def send_esign_request(self):
        """Trigger e-signature request via configured provider."""
        frappe.enqueue(
            "propx.property_management.utils.esign_utils.send_esign_request",
            lease=self.name,
            queue="default"
        )
        frappe.db.set_value("Lease", self.name, "esign_status", "Sent")
        return {"status": "sent"}
