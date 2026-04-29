import frappe
from frappe.model.document import Document


class ParkingLease(Document):

    def validate(self):
        if self.start_date and self.end_date:
            if self.start_date > self.end_date:
                frappe.throw("End Date must be after Start Date.")

    def on_submit(self):
        frappe.db.set_value("Parking Bay", self.bay, {
            "current_parking_lease": self.name,
            "status": "Rented Separately"
        })

    def on_cancel(self):
        frappe.db.set_value("Parking Bay", self.bay, {
            "current_parking_lease": None,
            "status": "Available"
        })
