"""
Listing & Vacancy API — M12 implementation.
auto_create_listing is registered as a doc_event on Property Unit.
"""
import frappe


def auto_create_listing(doc, method):
    """
    Fires on Property Unit on_update.
    Auto-creates an active Vacancy Listing when a unit goes Vacant.
    Skips if Vacancy Listing DocType not yet installed (M12).
    """
    if not frappe.db.exists("DocType", "Vacancy Listing"):
        return
    if doc.status != "Vacant":
        return
    if frappe.db.exists("Vacancy Listing", {"unit": doc.name, "listing_status": "Active"}):
        return

    vl = frappe.new_doc("Vacancy Listing")
    vl.unit = doc.name
    vl.property = doc.property
    vl.asking_rent = doc.asking_rent_annual
    vl.available_from = frappe.utils.today()
    vl.insert(ignore_permissions=True)


@frappe.whitelist()
def get_active_vacancies(property_name=None, usage_type=None):
    f = {"listing_status": "Active"}
    if property_name:
        f["property"] = property_name
    return frappe.get_all(
        "Vacancy Listing",
        filters=f,
        fields=["name", "unit", "property", "asking_rent",
                "available_from", "listing_views"]
    )


@frappe.whitelist()
def submit_inquiry(listing_name, name, phone, email, source=None):
    doc = frappe.get_doc("Vacancy Listing", listing_name)
    doc.append("inquiries", {
        "prospect_name": name,
        "phone": phone,
        "email": email,
        "source": source or "Website",
        "status": "New"
    })
    doc.listing_views = (doc.listing_views or 0) + 1
    doc.save(ignore_permissions=True)
    return {"status": "submitted"}
