import frappe
from frappe.model.document import Document


class Property(Document):

    def after_insert(self):
        self._create_cost_centre()

    def _create_cost_centre(self):
        from propx.property_management.setup.create_cost_centres import (
            create_cost_centre_for_property,
        )
        create_cost_centre_for_property(self.name, self.company)
