import frappe
from frappe.model.document import Document
from frappe.utils import today, date_diff, flt


class PropertyUnit(Document):

    def validate(self):
        self.calculate_area_sqm()
        self.calculate_days_vacant()
        self.set_vat_rule()
        self.fetch_property_category()

    def calculate_area_sqm(self):
        if self.area_sqft:
            self.area_sqm = round(flt(self.area_sqft) * 0.0929, 2)

    def calculate_days_vacant(self):
        if self.status == "Vacant" and self.vacancy_since:
            self.days_vacant = date_diff(today(), self.vacancy_since)
        elif self.status != "Vacant":
            self.days_vacant = 0

    def set_vat_rule(self):
        """UAE: Residential rent is VAT exempt. Commercial/Industrial/Storage is 5%."""
        if self.usage_type == "Residential":
            self.is_vat_applicable = 0
        elif self.usage_type in ["Commercial", "Industrial", "Storage"]:
            self.is_vat_applicable = 1

    def fetch_property_category(self):
        if self.property:
            cat = frappe.db.get_value("Property", self.property, "property_category")
            if cat:
                self.property_category = cat

    def on_update(self):
        self._refresh_property_occupancy()

    def _refresh_property_occupancy(self):
        if not self.property:
            return
        total = frappe.db.count(
            "Property Unit",
            {"property": self.property, "status": ["not in", ["Decommissioned"]]}
        )
        occupied = frappe.db.count(
            "Property Unit",
            {"property": self.property, "status": "Occupied"}
        )
        pct = round(occupied / total * 100, 1) if total else 0
        frappe.db.set_value("Property", self.property, {
            "total_units": total,
            "occupied_units": occupied,
            "occupancy_pct": pct
        })

    @frappe.whitelist()
    def get_lease_history(self):
        return frappe.get_all(
            "Lease",
            filters={"unit": self.name},
            fields=["name", "tenant", "tenant_name", "start_date",
                    "end_date", "annual_rent", "status"],
            order_by="start_date desc"
        )
