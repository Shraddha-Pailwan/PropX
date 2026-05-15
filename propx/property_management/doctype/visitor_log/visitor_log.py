import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class VisitorLog(Document):

    def validate(self):
        """Auto-fill host tenant from unit; validate checkout is after check-in."""
        if self.host_unit and not self.host_tenant:
            self.host_tenant = frappe.db.get_value(
                "Property Unit", self.host_unit, "current_tenant"
            )

        if self.check_in and self.check_out:
            if self.check_out <= self.check_in:
                frappe.throw("Check-Out time must be after Check-In time.")

    def on_update(self):
        """Auto-set status to Left when check_out is filled."""
        if self.check_out and self.status == "On Premises":
            frappe.db.set_value("Visitor Log", self.name, "status", "Left")
