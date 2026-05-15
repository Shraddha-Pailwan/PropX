import frappe
from frappe.model.document import Document


class UtilityMeter(Document):

    def validate(self):
        """Ensure unit belongs to the selected property."""
        if self.unit and self.property:
            unit_prop = frappe.db.get_value("Property Unit", self.unit, "property")
            if unit_prop and unit_prop != self.property:
                frappe.throw(
                    f"Unit {self.unit} does not belong to Property {self.property}."
                )

    def on_trash(self):
        """Prevent deletion if readings exist."""
        if frappe.db.exists("Meter Reading", {"meter": self.name, "docstatus": 1}):
            frappe.throw(
                "Cannot delete a Utility Meter that has submitted readings. "
                "Set status to 'Replaced' instead."
            )
