import frappe


@frappe.whitelist()
def create_move_in_inspection(doc_or_name, method=None):
    """Auto-create Move-In inspection when lease activates.

    Callable as a doc_event hook (doc, method) or directly (lease_name string).
    """
    if isinstance(doc_or_name, str):
        lease = frappe.get_doc("Lease", doc_or_name)
    else:
        lease = doc_or_name

    insp = frappe.new_doc("Property Inspection")
    insp.inspection_type = "Move-In"
    insp.lease = lease.name
    insp.unit = lease.unit
    insp.tenant = lease.tenant
    insp.inspection_date = lease.start_date
    insp.inspector = lease.owner or frappe.session.user
    insp.status = "Draft"
    insp.insert(ignore_permissions=True)
    return insp.name


@frappe.whitelist()
def get_inspection_summary(unit_name):
    """Return last 10 inspections for a unit."""
    return frappe.get_all(
        "Property Inspection",
        filters={"unit": unit_name},
        fields=["name", "inspection_type", "inspection_date",
                "overall_condition", "overall_score", "status"],
        order_by="inspection_date desc",
        limit=10
    )
