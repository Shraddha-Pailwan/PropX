import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PropertyInspection(Document):

    def validate(self):
        self._fetch_lease_defaults()
        self._calculate_overall_score()
        self._calculate_deposit_refund()

    def _fetch_lease_defaults(self):
        if not self.unit:
            return
        unit = frappe.get_doc("Property Unit", self.unit)
        self.property = unit.property
        if not self.tenant:
            self.tenant = unit.current_tenant
        if not self.lease:
            self.lease = unit.current_lease

    def _calculate_overall_score(self):
        if not self.inspection_items:
            return
        condition_map = {"Excellent": 100, "Good": 80, "Fair": 50, "Poor": 20, "N/A": None}
        scores = []
        for item in self.inspection_items:
            cond = (item.condition_move_out
                    if self.inspection_type == "Move-Out"
                    else item.condition_move_in)
            s = condition_map.get(cond)
            if s is not None:
                scores.append(s)
        if scores:
            avg = sum(scores) / len(scores)
            self.overall_score = round(avg, 1)
            if avg >= 90:
                self.overall_condition = "Excellent"
            elif avg >= 70:
                self.overall_condition = "Good"
            elif avg >= 50:
                self.overall_condition = "Fair"
            elif avg >= 30:
                self.overall_condition = "Poor"
            else:
                self.overall_condition = "Unacceptable"

    def _calculate_deposit_refund(self):
        if self.inspection_type != "Move-Out":
            return
        if not self.lease:
            return
        deposit = frappe.db.get_value("Lease", self.lease, "security_deposit")
        self.deposit_held = flt(deposit)
        total_ded = sum(
            flt(d.amount)
            for d in self.deductions
            if d.responsibility == "Tenant"
        )
        self.total_deductions = total_ded
        self.refund_amount = max(0, self.deposit_held - total_ded)

    def on_submit(self):
        if self.inspection_type == "Move-Out" and self.refund_approved:
            self._post_deposit_refund()

    def _post_deposit_refund(self):
        """Post Journal Entry: debit Deposits Payable, credit bank for tenant refund."""
        if not self.refund_amount:
            return
        company = frappe.db.get_value("Lease", self.lease, "company")
        je = frappe.new_doc("Journal Entry")
        je.company = company
        je.posting_date = frappe.utils.today()
        je.user_remark = (
            f"Security deposit refund: {self.tenant} | "
            f"Inspection: {self.name}"
        )
        je.append("accounts", {
            "account": "Security Deposits Payable",
            "debit_in_account_currency": self.refund_amount,
            "party_type": "Customer",
            "party": self.tenant
        })
        je.append("accounts", {
            "account": frappe.db.get_value(
                "Company", company, "default_bank_account"
            ),
            "credit_in_account_currency": self.refund_amount
        })
        je.insert(ignore_permissions=True)
        je.submit()
        self.db_set("refund_journal_entry", je.name)
        deposit_status = "Partially Refunded" if self.total_deductions > 0 else "Refunded"
        frappe.db.set_value("Lease", self.lease, {
            "deposit_status": deposit_status,
            "deposit_refund_amount": self.refund_amount
        })
