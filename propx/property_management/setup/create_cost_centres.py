import frappe


def create_cost_centre_for_property(property_name, company):
    """
    Called from Property.after_insert.
    Creates an ERPNext Cost Centre matching the property name and links it back.
    """
    abbr = frappe.db.get_value("Company", company, "abbr")
    cc_name = f"{property_name} - {abbr}"

    if frappe.db.exists("Cost Center", cc_name):
        frappe.db.set_value("Property", property_name, "cost_centre", cc_name)
        return cc_name

    parent = frappe.db.get_value(
        "Cost Center",
        {"is_group": 1, "company": company},
        "name"
    )
    if not parent:
        frappe.log_error(
            f"Cannot create Cost Centre for Property {property_name}: "
            f"no parent Cost Centre found for company {company}",
            "PropX Cost Centre Setup"
        )
        return None

    cc = frappe.get_doc({
        "doctype": "Cost Center",
        "cost_center_name": property_name,
        "parent_cost_center": parent,
        "company": company,
        "is_group": 0
    })
    cc.insert(ignore_permissions=True)
    frappe.db.set_value("Property", property_name, "cost_centre", cc.name)
    return cc.name
