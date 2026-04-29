import frappe


@frappe.whitelist()
def get_parking_summary(property_name):
    """Bay counts by status + EV count for a property."""
    return {
        "total_bays": frappe.db.count("Parking Bay", {"property": property_name}),
        "available": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Available"}),
        "allocated": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Allocated to Unit"}),
        "standalone": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Rented Separately"}),
        "ev_bays": frappe.db.count("Parking Bay",
            {"property": property_name, "has_ev_charger": 1}),
    }


@frappe.whitelist()
def get_available_bays(property_name, bay_type=None):
    """Available bays for leasing, optionally filtered by type."""
    filters = {"property": property_name, "status": "Available"}
    if bay_type:
        filters["bay_type"] = bay_type
    return frappe.get_all(
        "Parking Bay",
        filters=filters,
        fields=["name", "bay_number", "bay_label", "level",
                "bay_type", "has_ev_charger", "monthly_charge"]
    )
