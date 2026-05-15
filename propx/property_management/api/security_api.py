"""
security_api.py — M08 Security & Access Management API
Whitelisted endpoints for guard management, visitor control,
incident reporting, and key tracking.
Designed for the mobile guard app and the security desk UI.
"""
import frappe
from frappe.utils import today, now_datetime, get_datetime


# ---------------------------------------------------------------------------
# 1. Security KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_security_kpis(property_name=None):
    """
    Live security dashboard KPIs.
    Returns guard headcount, visitor counts, and open incidents.
    """
    prop_filter = {"property": property_name} if property_name else {}

    # Guards currently on duty (checked in, not checked out)
    guards_on_duty = frappe.db.sql(
        """
        SELECT COUNT(*) FROM `tabGuard Shift Assignment` gsa
        JOIN `tabGuard Shift` gs ON gs.name = gsa.parent
        WHERE gsa.status = 'On Duty'
          AND gs.shift_date = %(today)s
          {prop}
        """.format(prop="AND gs.property = %(property)s" if property_name else ""),
        {"today": today(), "property": property_name},
    )[0][0] or 0

    visitors_today = frappe.db.count(
        "Visitor Log",
        {**prop_filter, "check_in": [">=", today() + " 00:00:00"]},
    )

    on_premises = frappe.db.count(
        "Visitor Log",
        {**prop_filter, "status": "On Premises"},
    )

    open_incidents = frappe.db.count(
        "Security Incident",
        {**prop_filter, "status": ["in", ["Open", "Under Investigation"]]},
    )

    keys_issued = frappe.db.count(
        "Key Register",
        {**prop_filter, "status": "Issued"},
    )

    keys_lost = frappe.db.count(
        "Key Register",
        {**prop_filter, "status": "Lost"},
    )

    return {
        "guards_on_duty": int(guards_on_duty),
        "visitors_today": visitors_today,
        "on_premises": on_premises,
        "open_incidents": open_incidents,
        "keys_issued": keys_issued,
        "keys_lost": keys_lost,
    }


# ---------------------------------------------------------------------------
# 2. Log visitor in
# ---------------------------------------------------------------------------

@frappe.whitelist()
def log_visitor_in(
    property_name,
    visitor_name,
    host_unit=None,
    id_type=None,
    id_number=None,
    vehicle_plate=None,
    purpose=None,
    pre_approved=0,
    guard_employee=None,
):
    """
    Create a Visitor Log entry on arrival.
    Called from guard tablet / mobile app.
    Returns the new Visitor Log name.
    """
    doc = frappe.new_doc("Visitor Log")
    doc.property = property_name
    doc.visitor_name = visitor_name
    doc.host_unit = host_unit
    doc.id_type = id_type
    doc.id_number = id_number
    doc.vehicle_plate = vehicle_plate
    doc.visit_purpose = purpose
    doc.pre_approved = frappe.utils.cint(pre_approved)
    doc.guard_on_duty = guard_employee
    doc.check_in = now_datetime()
    doc.status = "On Premises"
    doc.insert(ignore_permissions=True)
    return {"visitor_log": doc.name, "check_in": str(doc.check_in)}


# ---------------------------------------------------------------------------
# 3. Log visitor out
# ---------------------------------------------------------------------------

@frappe.whitelist()
def log_visitor_out(visitor_log_name):
    """
    Set check_out time and update status to Left.
    Called from guard tablet when visitor exits.
    """
    if not frappe.db.exists("Visitor Log", visitor_log_name):
        frappe.throw(f"Visitor Log '{visitor_log_name}' not found.")

    checkout_time = now_datetime()
    frappe.db.set_value("Visitor Log", visitor_log_name, {
        "check_out": checkout_time,
        "status": "Left",
    })

    return {"visitor_log": visitor_log_name, "check_out": str(checkout_time)}


# ---------------------------------------------------------------------------
# 4. Visitors currently on premises
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_visitors_on_premises(property_name=None):
    """
    Return all visitors currently on premises (status = On Premises).
    """
    filters = {"status": "On Premises"}
    if property_name:
        filters["property"] = property_name

    return frappe.get_all(
        "Visitor Log",
        filters=filters,
        fields=[
            "name", "visitor_name", "host_unit", "host_tenant",
            "visit_purpose", "vehicle_plate", "check_in",
            "pre_approved", "guard_on_duty",
        ],
        order_by="check_in desc",
    )


# ---------------------------------------------------------------------------
# 5. Report a security incident
# ---------------------------------------------------------------------------

@frappe.whitelist()
def report_incident(
    property_name,
    incident_type,
    description,
    location_detail=None,
    reported_by=None,
    incident_datetime=None,
):
    """
    Create a Security Incident. High-priority types trigger a real-time alert.
    Returns the new incident name.
    """
    doc = frappe.new_doc("Security Incident")
    doc.property = property_name
    doc.incident_type = incident_type
    doc.description = description
    doc.location_detail = location_detail
    doc.reported_by = reported_by
    doc.incident_datetime = incident_datetime or now_datetime()
    doc.status = "Open"
    doc.insert(ignore_permissions=True)
    return {"incident": doc.name, "status": doc.status}


# ---------------------------------------------------------------------------
# 6. Issue / return a key
# ---------------------------------------------------------------------------

@frappe.whitelist()
def issue_key(key_name, tenant, issued_date=None):
    """Issue a key to a tenant."""
    if not frappe.db.exists("Key Register", key_name):
        frappe.throw(f"Key '{key_name}' not found.")

    current_status = frappe.db.get_value("Key Register", key_name, "status")
    if current_status != "Available":
        frappe.throw(
            f"Key '{key_name}' is currently '{current_status}'. "
            "Only Available keys can be issued."
        )

    frappe.db.set_value("Key Register", key_name, {
        "current_holder": tenant,
        "issued_date": issued_date or today(),
        "returned_date": None,
        "status": "Issued",
    })
    return {"key": key_name, "status": "Issued", "holder": tenant}


@frappe.whitelist()
def return_key(key_name, returned_date=None):
    """Mark a key as returned and available."""
    if not frappe.db.exists("Key Register", key_name):
        frappe.throw(f"Key '{key_name}' not found.")

    frappe.db.set_value("Key Register", key_name, {
        "returned_date": returned_date or today(),
        "current_holder": None,
        "status": "Available",
    })
    return {"key": key_name, "status": "Available"}


# ---------------------------------------------------------------------------
# 7. Today's shift roster
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_todays_shifts(property_name=None):
    """Return all guard shifts scheduled for today."""
    filters = {"shift_date": today()}
    if property_name:
        filters["property"] = property_name

    shifts = frappe.get_all(
        "Guard Shift",
        filters=filters,
        fields=[
            "name", "property", "shift_type",
            "shift_start", "shift_end",
        ],
        order_by="shift_start asc",
    )

    # Attach guard assignments to each shift
    for shift in shifts:
        shift["guards"] = frappe.get_all(
            "Guard Shift Assignment",
            filters={"parent": shift["name"]},
            fields=["employee", "post", "status", "check_in_time", "check_out_time"],
        )

    return shifts
