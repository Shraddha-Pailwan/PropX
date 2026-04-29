import frappe


@frappe.whitelist()
def get_portfolio_summary(company=None):
    """Dashboard KPIs. Called on React dashboard load."""
    f = {}
    if company:
        f["company"] = company

    total = frappe.db.count(
        "Property Unit",
        {**f, "status": ["!=", "Decommissioned"]}
    )
    occupied = frappe.db.count(
        "Property Unit", {**f, "status": "Occupied"}
    )
    vacant = frappe.db.count(
        "Property Unit", {**f, "status": "Vacant"}
    )
    return {
        "total_units": total,
        "occupied": occupied,
        "vacant": vacant,
        "occupancy_pct": round(occupied / total * 100, 1) if total else 0,
    }


@frappe.whitelist()
def get_units_by_property(property_name, status=None):
    """Unit grid for React property view."""
    f = {"property": property_name}
    if status:
        f["status"] = status
    return frappe.get_all(
        "Property Unit", filters=f,
        fields=["name", "unit_number", "floor", "usage_type", "sub_type",
                "area_sqft", "status", "current_tenant", "current_lease",
                "asking_rent_annual", "last_agreed_rent", "days_vacant",
                "is_vat_applicable", "furnished_status"]
    )


@frappe.whitelist()
def get_vacant_units(property_name=None, usage_type=None):
    """Leasing module: find available units."""
    f = {"status": "Vacant"}
    if property_name:
        f["property"] = property_name
    if usage_type:
        f["usage_type"] = usage_type
    return frappe.get_all(
        "Property Unit", filters=f,
        fields=["name", "unit_number", "property", "floor", "usage_type",
                "sub_type", "area_sqft", "asking_rent_annual",
                "days_vacant", "is_vat_applicable", "furnished_status"]
    )


@frappe.whitelist()
def get_properties_list(company=None):
    """Properties table for React portfolio view."""
    f = {}
    if company:
        f["company"] = company
    return frappe.get_all(
        "Property", filters=f,
        fields=["name", "property_name", "property_category",
                "city", "emirate_region", "total_units",
                "occupied_units", "occupancy_pct", "cost_centre",
                "owner", "currency"]
    )
