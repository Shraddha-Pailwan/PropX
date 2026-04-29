"""
maintenance_api.py
------------------
Whitelisted API endpoints for M06 Maintenance & Facilities Management.

Consumed by the React maintenance kanban board and mobile technician app.
"""

import frappe
from frappe.utils import today, add_days, get_first_day, flt


# ---------------------------------------------------------------------------
# 1. Maintenance KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_maintenance_kpis(property_name=None):
    """
    Dashboard KPIs: open tickets, SLA breaches, pending approvals,
    completions this month, and average resolution time (last 30 days).
    """
    prop_filter = {"property": property_name} if property_name else {}

    open_tickets = frappe.db.count(
        "Maintenance Job Card",
        {**prop_filter, "ticket_status": ["in", ["New", "Assigned", "In Progress"]]},
    )
    sla_breaches = frappe.db.count(
        "Maintenance Job Card",
        {**prop_filter,
         "sla_status": "Breached",
         "ticket_status": ["not in", ["Closed", "Cancelled"]]},
    )
    pending_approval = frappe.db.count(
        "Maintenance Job Card",
        {**prop_filter, "ticket_status": "Pending Approval"},
    )
    completed_month = frappe.db.count(
        "Maintenance Job Card",
        {**prop_filter,
         "ticket_status": ["in", ["Completed", "Closed"]],
         "completed_at": [">=", get_first_day(today())]},
    )

    cutoff = add_days(today(), -30)
    avg_res = frappe.db.sql(
        """
        SELECT AVG(resolution_hours)
          FROM `tabMaintenance Job Card`
         WHERE resolution_hours > 0
           AND completed_at >= %s
           {prop}
        """.format(prop="AND property = %s" if property_name else ""),
        (cutoff, property_name) if property_name else (cutoff,),
    )[0][0] or 0

    return {
        "open_tickets": open_tickets,
        "sla_breaches": sla_breaches,
        "pending_approval": pending_approval,
        "completed_month": completed_month,
        "avg_resolution_hours": round(flt(avg_res), 1),
    }


# ---------------------------------------------------------------------------
# 2. Kanban view
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_kanban(property_name=None):
    """
    Return open tickets grouped by ticket_status for the kanban board.
    """
    filters = {"ticket_status": ["not in", ["Closed", "Cancelled"]]}
    if property_name:
        filters["property"] = property_name

    tickets = frappe.get_all(
        "Maintenance Job Card",
        filters=filters,
        fields=[
            "name", "subject", "unit", "property", "category",
            "priority", "ticket_status", "sla_status",
            "assigned_technician", "vendor", "estimated_cost",
            "actual_cost", "sla_deadline", "reported_by_tenant",
            "opened_at",
        ],
        order_by="priority desc, modified desc",
    )

    grouped = {}
    for ticket in tickets:
        status = ticket.ticket_status
        grouped.setdefault(status, []).append(ticket)
    return grouped


# ---------------------------------------------------------------------------
# 3. Tenant request submission
# ---------------------------------------------------------------------------

@frappe.whitelist()
def submit_tenant_request(unit, subject, category, description=None):
    """
    Called from the tenant portal (M09).
    Creates a Maintenance Job Card reported by the tenant.
    """
    # Verify caller is the current tenant for this unit
    tenant = frappe.db.get_value("Property Unit", unit, "current_tenant")
    if not tenant:
        frappe.throw("No active tenant for this unit.")

    caller_customer = frappe.db.get_value(
        "Customer", {"email_id": frappe.session.user}, "name"
    )
    if caller_customer != tenant:
        frappe.throw("You can only raise maintenance requests for your own unit.")

    prop = frappe.db.get_value("Property Unit", unit, "property")

    wo = frappe.new_doc("Maintenance Job Card")
    wo.subject = subject
    wo.unit = unit
    wo.property = prop
    wo.category = category
    wo.description = description or ""
    wo.priority = "Medium"
    wo.reported_by_tenant = 1
    wo.tenant_reference = tenant
    wo.ticket_status = "New"
    wo.insert(ignore_permissions=True)

    return {"ticket": wo.name, "status": "New"}


# ---------------------------------------------------------------------------
# 4. Update ticket status
# ---------------------------------------------------------------------------

@frappe.whitelist()
def update_ticket_status(ticket_name, new_status, notes=None):
    """
    Move a ticket to a new status. Validates allowed transitions.
    """
    allowed = {
        "New": ["Assigned", "Cancelled"],
        "Assigned": ["In Progress", "Cancelled"],
        "In Progress": ["Pending Parts", "Pending Approval", "Completed", "Cancelled"],
        "Pending Parts": ["In Progress", "Cancelled"],
        "Pending Approval": ["In Progress", "Cancelled"],
        "Completed": ["Closed"],
        "Closed": [],
        "Cancelled": [],
    }
    doc = frappe.get_doc("Maintenance Job Card", ticket_name)
    if new_status not in allowed.get(doc.ticket_status, []):
        frappe.throw(
            f"Cannot move ticket from '{doc.ticket_status}' to '{new_status}'."
        )
    doc.ticket_status = new_status
    if notes:
        doc.resolution_notes = (doc.resolution_notes or "") + f"\n\n{notes}"
    doc.save()
    return {"ticket": ticket_name, "status": new_status}


# ---------------------------------------------------------------------------
# 5. Vendor COI status summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_vendor_coi_summary():
    """
    Returns COI status per vendor: Valid / Expiring Soon / Expired / Missing.
    Used by the property manager vendor compliance view.
    """
    all_vendors = frappe.get_all("Supplier", fields=["name", "supplier_name"])
    result = []
    for v in all_vendors:
        coi = frappe.db.get_value(
            "Vendor COI",
            {"vendor": v.name},
            ["name", "status", "valid_to", "insurance_company"],
            as_dict=True,
            order_by="valid_to desc",
        )
        result.append({
            "vendor": v.name,
            "vendor_name": v.supplier_name,
            "coi": coi or None,
            "coi_status": coi.status if coi else "Missing",
        })
    return result
