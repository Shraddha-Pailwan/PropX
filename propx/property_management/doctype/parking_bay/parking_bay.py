import frappe
from frappe.model.document import Document


class ParkingBay(Document):

    def validate(self):
        self._check_bay_number_unique()
        self._sync_tenant_from_unit()
        self._set_status()

    def _check_bay_number_unique(self):
        duplicate = frappe.db.exists("Parking Bay", {
            "property": self.property,
            "bay_number": self.bay_number,
            "name": ["!=", self.name or ""]
        })
        if duplicate:
            frappe.throw(
                f"Bay Number <b>{self.bay_number}</b> already exists "
                f"for this property."
            )

    def _sync_tenant_from_unit(self):
        if self.allocated_to_unit:
            tenant = frappe.db.get_value(
                "Property Unit", self.allocated_to_unit, "current_tenant"
            )
            self.allocated_to_tenant = tenant

    def _set_status(self):
        # Never auto-override a manually managed status
        if self.status in ("Reserved", "Out of Service"):
            return
        if self.allocated_to_unit:
            self.status = "Allocated to Unit"
        elif self.current_parking_lease:
            self.status = "Rented Separately"
        else:
            self.status = "Available"
            self.allocated_to_tenant = None
