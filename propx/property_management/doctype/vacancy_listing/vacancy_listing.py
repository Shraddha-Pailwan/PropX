import frappe
from frappe.model.document import Document


class VacancyListing(Document):

    def validate(self):
        """Fetch property from unit if not already set."""
        if self.unit and not self.property:
            self.property = frappe.db.get_value(
                "Property Unit", self.unit, "property"
            )

    def on_submit(self):
        pass

    def after_insert(self):
        """Keep listing_views initialised."""
        if not self.listing_views:
            self.listing_views = 0
