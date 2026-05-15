import frappe
from frappe.model.document import Document


class LeaseApplication(Document):

    def validate(self):
        """Update listing inquiry status when application is approved/rejected."""
        pass

    def on_update(self):
        """When approved, mark listing as Under Offer."""
        if self.application_status == "Approved" and self.vacancy_listing:
            frappe.db.set_value(
                "Vacancy Listing",
                self.vacancy_listing,
                "listing_status",
                "Under Offer",
            )
