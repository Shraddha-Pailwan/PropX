# CLAUDE.md — M02: Leasing & Contract Management
# propx/docs/CLAUDE_M02.md

## PURPOSE
Full lease lifecycle: application → draft → active → renew / terminate.
Handles residential, commercial, industrial, and short-term leases.
GCC-specific: PDC schedule auto-generation, Ejari tracking,
RERA rent cap compliance, rent escalation, percentage rent (retail),
e-signature workflow, and break clause management.

## DEPENDS ON
- M01: Property Unit (anchor DocType — must exist first)
- ERPNext: Customer (tenant), Sales Invoice (rent invoices)

## REUSE FROM ERPNext
- `Customer`  → tenant is a Customer. No new tenant DocType.
- `Sales Invoice` → rent invoices created from lease schedule.

---
## DOCTYPES TO BUILD (3 new + 4 children)

### DocType 1: Lease  ← CORE

Naming: `format:LAS-{YYYY}-{#####}`
Title field: `tenant_name`
Track changes: yes

```
# === PARTIES ===
tenant              Link→Customer   reqd, in_list_view
tenant_name         Data            read_only (fetched from Customer)
tenant_type         Select          reqd    Individual|Corporate
company_name        Data            depends_on: tenant_type==Corporate
trade_licence_no    Data            depends_on: tenant_type==Corporate
trade_licence_expiry Date           depends_on: tenant_type==Corporate

# === PROPERTY ===
property            Link→Property   reqd
unit                Link→Property Unit  reqd, in_list_view
usage_type          Select          read_only (fetched from unit)

# === LEASE TYPE ===
lease_category      Select          reqd
                    Residential|Commercial|Industrial|Short-Term|Monthly
lease_subtype       Select          Standard|Corporate|Diplomatic|Government
contract_language   Select          English|Arabic|Bilingual  default English

# === TERM ===
start_date          Date            reqd
end_date            Date            reqd
lease_duration_months Int           read_only  "auto-calculated"
notice_period_days  Int             default 90

# === BREAK CLAUSE ===
has_break_clause    Check           default 0
break_clause_date   Date            depends_on: has_break_clause==1
break_penalty_months Int            default 2  "months rent as penalty"

# === FINANCIAL ===
annual_rent         Currency        reqd, in_list_view
monthly_rent        Currency        read_only  "annual / 12"
currency            Link→Currency   default AED
is_vat_applicable   Check           default 0  read_only (from unit)
vat_rate            Percent         read_only  "5% UAE, 15% KSA, 5% Oman"
vat_amount_annual   Currency        read_only
total_with_vat      Currency        read_only

# === SERVICE CHARGE ===
service_charge_monthly  Currency    "Estimated monthly service charge"
service_charge_basis    Select      Per Sqft|Fixed Amount|None  default None
cam_reconciliation_date Date        "Annual CAM/service charge reconciliation date"

# === PERCENTAGE RENT (retail) ===
has_percentage_rent Check           default 0
percentage_rent_pct Percent         depends_on: has_percentage_rent==1
percentage_rent_threshold Currency  "Monthly sales above this trigger % rent"
percentage_rent_basis Select        Gross Sales|Net Sales

# === RENT ESCALATION ===
has_rent_escalation Check           default 0
escalation_type     Select          Fixed %|CPI Index|RERA Index|Negotiated
                                    depends_on: has_rent_escalation==1
escalation_pct      Percent         depends_on: escalation_type==Fixed %
escalation_frequency_months Int     default 12
next_escalation_date Date           read_only  auto-calculated
rera_current_rent   Currency        "Current market rent per RERA index (UAE)"
rera_allowed_increase_pct Percent   "Calculated from RERA index — max allowed"

# === SECURITY DEPOSIT ===
security_deposit    Currency
deposit_cheque_no   Data
deposit_status      Select          Pending|Received|Partly Received|Refunded  default Pending
deposit_refund_amount Currency      read_only  "Set during move-out inspection"

# === PDC SCHEDULE ===
number_of_cheques   Int             default 4  reqd
                    "GCC norm: 1, 2, 4, or 6 cheques/year"
pdc_schedule        Table→PDC Cheque Row  (child)

# === GCC COMPLIANCE ===
ejari_contract_no   Data            "UAE Ejari contract number"
ejari_status        Select          Not Filed|Filed|Renewed|Cancelled  default Not Filed
ejari_filing_date   Date
rera_permit_no      Data
tawtheeq_no         Data            "Abu Dhabi Tawtheeq number"

# === DOCUMENTS ===
signed_contract     Attach          "Signed lease PDF"
signed_date         Date
esign_status        Select          Not Sent|Sent|Signed|Declined  default Not Sent
esign_request_id    Data            read_only  "DocuSign/eSign envelope ID"

# === STATUS & RENEWAL ===
status              Select          reqd
                    Draft|Pending Approval|Active|Expiring|Renewed|Terminated|Cancelled
                    default Draft, in_list_view
renewal_status      Select
                    Not Initiated|Offer Sent|Negotiating|Agreed|Declined
renewal_offered_rent Currency
parent_lease        Link→Lease      "Previous lease (if this is a renewal)"

# === SPECIAL CONDITIONS ===
special_conditions  Text Editor
internal_notes      Text Editor     "Not visible to tenant"
```

**Permissions:**
- Lease Manager: CRUD
- Property Manager: CRUD
- Accountant: Read
- Tenant: Read own lease (portal)

---
### DocType 2: PDC Cheque Row (child table)

```
cheque_number       Data            in_list_view
bank_name           Data            in_list_view
account_number      Data
amount              Currency        reqd, in_list_view
due_date            Date            reqd, in_list_view
period_from         Date
period_to           Date
cheque_status       Select          Pending|Received|Deposited|Cleared|Bounced|Replaced
                                    default Pending, in_list_view
pdc_register_ref    Link→PDC Register  read_only  "Auto-linked when M03 creates PDC entry"
```

---
### DocType 3: Lease Inspection Link (child — links inspections to lease)

```
inspection          Link→Property Inspection  reqd
inspection_type     Select  Move-In|Move-Out|Periodic
inspection_date     Date    read_only (fetched)
status              Data    read_only (fetched)
```

---
### DocType 4: Rent Escalation Schedule (child)

```
escalation_date     Date        reqd
from_rent           Currency    reqd
to_rent             Currency    reqd
escalation_type     Select      Fixed %|CPI|RERA|Negotiated
change_pct          Percent
applied             Check       default 0
applied_date        Date
invoice_adjusted    Check       default 0
```

---
### DocType 5: Percentage Rent Entry (standalone, links to Lease)

Naming: `format:PRE-{YYYY}-{MM}-{#####}`

```
lease               Link→Lease      reqd
tenant              Link→Customer   reqd (fetched)
property            Link→Property   reqd (fetched)
unit                Link→Property Unit  reqd (fetched)
period_from         Date            reqd
period_to           Date            reqd
gross_sales         Currency        reqd
threshold           Currency        read_only (from lease)
overage_amount      Currency        read_only  "max(0, gross_sales - threshold)"
percentage_rate     Percent         read_only (from lease)
percentage_rent_due Currency        read_only  "overage × rate"
invoice             Link→Sales Invoice  read_only
status              Select          Pending|Invoiced  default Pending
```

---
## PYTHON CONTROLLER

```python
# propx/property_management/doctype/lease/lease.py

import frappe
from frappe.model.document import Document
from frappe.utils import (add_days, add_months, date_diff, getdate,
                           today, flt, now_datetime)
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
        # Determine VAT rate by country
        country = frappe.db.get_value(
            "Property", self.property, "country"
        ) if self.property else None
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
        """, {"unit": self.unit, "name": self.name or "NEW",
               "start": self.start_date, "end": self.end_date})
        if conflict:
            frappe.throw(
                f"Unit {self.unit} has an overlapping active lease: {conflict[0][0]}"
            )

    def auto_generate_pdc_schedule(self):
        """Generate PDC rows if table is empty."""
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
        """
        UAE: Warn if renewal rent exceeds RERA-allowed increase cap.
        Only checks if this is a renewal (parent_lease set) and property
        is in UAE.
        """
        if not self.parent_lease or not self.annual_rent:
            return
        country = frappe.db.get_value("Property", self.property, "country")
        if country != "United Arab Emirates":
            return
        if self.rera_current_rent and self.rera_allowed_increase_pct:
            max_rent = flt(self.rera_current_rent) * (
                1 + flt(self.rera_allowed_increase_pct) / 100
            )
            if flt(self.annual_rent) > max_rent:
                frappe.msgprint(
                    f"⚠️ RERA Warning: Proposed rent AED {self.annual_rent:,.0f} "
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

    def on_submit(self):
        self._set_unit_occupied()
        self._create_pdc_register_entries()
        self._generate_escalation_schedule()

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
        """Enqueue PDC Register creation after lease activation."""
        frappe.enqueue(
            "propx.property_management.utils.pdc_utils.create_pdc_entries",
            lease=self.name,
            queue="default",
            timeout=120
        )

    def _generate_escalation_schedule(self):
        """Auto-populate escalation rows if escalation is configured."""
        if not self.has_rent_escalation or not self.escalation_frequency_months:
            return
        if self.escalation_schedule:  # already generated
            return
        freq = int(self.escalation_frequency_months)
        current_rent = flt(self.annual_rent)
        esc_date = add_months(self.start_date, freq)
        while getdate(esc_date) < getdate(self.end_date):
            if self.escalation_type == "Fixed %":
                new_rent = round(current_rent * (1 + flt(self.escalation_pct) / 100), 2)
            else:
                new_rent = current_rent  # to be updated manually for CPI/RERA
            self.append("escalation_schedule", {
                "escalation_date": esc_date,
                "from_rent": current_rent,
                "to_rent": new_rent,
                "escalation_type": self.escalation_type,
                "change_pct": self.escalation_pct or 0,
                "applied": 0
            })
            current_rent = new_rent
            esc_date = add_months(esc_date, freq)
        self.save(ignore_permissions=True)

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
        new_lease.insert()

        frappe.db.set_value("Lease", self.name, "renewal_status", "Offer Sent")
        return new_lease.name

    @frappe.whitelist()
    def terminate_early(self, termination_date, reason):
        days_remaining = date_diff(self.end_date, termination_date)
        penalty = 0
        if days_remaining > 0 and self.break_penalty_months:
            penalty = round(flt(self.monthly_rent) * int(self.break_penalty_months), 2)

        self.status = "Terminated"
        self.end_date = termination_date
        self.add_comment("Info",
            f"Early termination on {termination_date}. "
            f"Reason: {reason}. Penalty: AED {penalty:,.2f}"
        )
        self.save()
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
```

---
## WORKFLOW

```python
# Create via Frappe Workflow DocType (or fixture JSON)
{
    "workflow_name": "Lease Approval Workflow",
    "document_type": "Lease",
    "is_active": 1,
    "workflow_state_field": "status",
    "states": [
        {"state": "Draft",            "doc_status": "0", "allow_edit": "Lease Manager"},
        {"state": "Pending Approval", "doc_status": "0", "allow_edit": "Property Manager"},
        {"state": "Active",           "doc_status": "1", "allow_edit": "Property Manager"},
        {"state": "Expiring",         "doc_status": "1", "allow_edit": "Property Manager"},
        {"state": "Terminated",       "doc_status": "2", "allow_edit": "System Manager"},
        {"state": "Cancelled",        "doc_status": "2", "allow_edit": "System Manager"},
    ],
    "transitions": [
        {"state": "Draft", "action": "Submit for Approval",
         "next_state": "Pending Approval", "allowed": "Lease Manager"},
        {"state": "Pending Approval", "action": "Approve",
         "next_state": "Active", "allowed": "Property Manager"},
        {"state": "Pending Approval", "action": "Return",
         "next_state": "Draft", "allowed": "Property Manager"},
        {"state": "Active", "action": "Terminate",
         "next_state": "Terminated", "allowed": "Property Manager"},
        {"state": "Draft", "action": "Cancel",
         "next_state": "Cancelled", "allowed": "Lease Manager"},
    ]
}
```

---
## API ENDPOINTS

```python
# propx/property_management/api/lease_api.py

import frappe
from frappe.utils import today, add_days


@frappe.whitelist()
def get_lease_stats():
    t = today()
    return {
        "total_active": frappe.db.count("Lease", {"status": "Active"}),
        "expiring_30": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 30)]]
        }),
        "expiring_60": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 60)]]
        }),
        "draft_count": frappe.db.count("Lease", {"status": "Draft"}),
        "critical": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 14)]],
            "renewal_status": ["in", ["Not Initiated", None, ""]]
        })
    }


@frappe.whitelist()
def get_leases(status=None, lease_category=None,
               search=None, page=1, page_size=25):
    f = {}
    if status:
        f["status"] = status
    if lease_category:
        f["lease_category"] = lease_category
    if search:
        f["tenant_name"] = ["like", f"%{search}%"]

    leases = frappe.get_all(
        "Lease", filters=f,
        fields=["name", "tenant", "tenant_name", "unit", "property",
                "lease_category", "start_date", "end_date",
                "annual_rent", "currency", "status",
                "renewal_status", "ejari_status", "is_vat_applicable",
                "number_of_cheques"],
        order_by="end_date asc",
        start=(int(page) - 1) * int(page_size),
        page_length=int(page_size)
    )
    return {"leases": leases,
            "total": frappe.db.count("Lease", f),
            "page": int(page)}


@frappe.whitelist()
def get_expiring_leases(days=60):
    cutoff = add_days(today(), int(days))
    return frappe.db.sql("""
        SELECT l.name, l.tenant, l.tenant_name, l.unit, l.property,
               l.end_date, l.annual_rent, l.renewal_status,
               DATEDIFF(l.end_date, CURDATE()) as days_remaining
        FROM `tabLease` l
        WHERE l.status IN ('Active','Expiring')
          AND l.end_date BETWEEN %(today)s AND %(cutoff)s
        ORDER BY l.end_date ASC
    """, {"today": today(), "cutoff": cutoff}, as_dict=True)


@frappe.whitelist()
def get_rera_rent_cap(current_rent, current_market_rent):
    """
    UAE RERA Rental Index cap calculator.
    Returns maximum allowed new rent.
    ref: Dubai Law No. 43 of 2013
    """
    cur = float(current_rent)
    market = float(current_market_rent)
    gap_pct = (market - cur) / cur * 100 if cur else 0

    if gap_pct < 11:
        max_increase_pct = 0
    elif gap_pct < 21:
        max_increase_pct = 5
    elif gap_pct < 31:
        max_increase_pct = 10
    elif gap_pct < 41:
        max_increase_pct = 15
    else:
        max_increase_pct = 20

    return {
        "current_rent": cur,
        "market_rent": market,
        "gap_pct": round(gap_pct, 1),
        "max_increase_pct": max_increase_pct,
        "max_allowed_new_rent": round(cur * (1 + max_increase_pct / 100), 2)
    }
```

---
## SCHEDULED TASKS (add to tasks.py)

```python
def send_lease_expiry_alerts():
    """Daily: alert on leases expiring in 60, 30, 7 days."""
    from propx.property_management.utils.notification_utils import (
        send_whatsapp_to_manager
    )
    for days, severity in [(60, "info"), (30, "warning"), (7, "critical")]:
        cutoff = frappe.utils.add_days(frappe.utils.today(), days)
        leases = frappe.get_all(
            "Lease",
            filters={
                "status": ["in", ["Active", "Expiring"]],
                "end_date": cutoff,
                "renewal_status": ["in", ["Not Initiated", None, ""]]
            },
            fields=["name", "tenant_name", "unit", "end_date"]
        )
        for lease in leases:
            frappe.publish_realtime(
                event="lease_expiry_alert",
                message={**lease, "days": days, "severity": severity}
            )


def apply_due_rent_escalations():
    """Daily: check escalation_schedule rows due today and apply."""
    today_str = frappe.utils.today()
    due = frappe.db.sql("""
        SELECT ers.name as row_name, ers.to_rent, l.name as lease_name
        FROM `tabRent Escalation Schedule` ers
        JOIN `tabLease` l ON l.name = ers.parent
        WHERE ers.escalation_date = %(today)s
          AND ers.applied = 0
          AND l.status = 'Active'
    """, {"today": today_str}, as_dict=True)

    for row in due:
        frappe.db.set_value("Lease", row.lease_name, "annual_rent", row.to_rent)
        frappe.db.set_value(
            "Rent Escalation Schedule", row.row_name,
            {"applied": 1, "applied_date": today_str}
        )
    if due:
        frappe.db.commit()
```

---
## CHECKLIST

- [ ] Create Lease DocType with all fields
- [ ] Create PDC Cheque Row child DocType
- [ ] Create Lease Inspection Link child DocType
- [ ] Create Rent Escalation Schedule child DocType
- [ ] Create Percentage Rent Entry standalone DocType
- [ ] Write lease.py controller (validate, on_submit, on_cancel, whitelist methods)
- [ ] Create Lease Approval Workflow
- [ ] Write lease_api.py (4 endpoints including RERA cap calculator)
- [ ] Add daily scheduler tasks (expiry alerts, escalation apply)
- [ ] Test: create lease → PDC schedule auto-generated for 4 cheques
- [ ] Test: submit lease → unit status changes to Occupied
- [ ] Test: RERA cap warning fires when renewal rent is too high
- [ ] Test: escalation row applied on due date → annual_rent updated
- [ ] Test: initiate_renewal creates draft lease linked to parent
