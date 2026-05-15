"""
admin_api.py — M13 Platform Administration API
Whitelisted endpoints for SaaS management, API key generation,
user provisioning, and platform health checks.
"""
import frappe
from frappe.utils import now_datetime, getdate, today


# ---------------------------------------------------------------------------
# 1. Generate API Key for a user
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_api_key(user):
    """
    Generate a fresh Frappe API key + secret for a user.
    Only System Manager can call this.

    Returns: { api_key, api_secret }
    """
    frappe.only_for("System Manager")

    if not frappe.db.exists("User", user):
        frappe.throw(f"User '{user}' not found.")

    key = frappe.generate_hash(length=15)
    secret = frappe.generate_hash(length=15)

    frappe.db.set_value("User", user, {
        "api_key": key,
        "api_secret": secret,
    })
    frappe.db.commit()

    return {"user": user, "api_key": key, "api_secret": secret}


# ---------------------------------------------------------------------------
# 2. List all PropX Clients
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_clients(active_only=True):
    """Return all PropX Client registrations (SaaS registry)."""
    frappe.only_for(["System Manager", "PropX Admin"])

    filters = {}
    if frappe.utils.cint(active_only):
        filters["is_active"] = 1

    return frappe.get_all(
        "PropX Client",
        filters=filters,
        fields=[
            "name", "client_name", "company", "plan",
            "max_units", "is_active", "subscription_start",
            "subscription_end", "custom_domain", "api_rate_limit",
        ],
        order_by="client_name asc",
    )


# ---------------------------------------------------------------------------
# 3. Platform Health Check
# ---------------------------------------------------------------------------

@frappe.whitelist()
def health_check():
    """
    Quick platform health summary.
    Returns counts of key entities and any obvious anomalies.
    """
    frappe.only_for(["System Manager", "PropX Admin"])

    result = {
        "timestamp": str(now_datetime()),
        "properties": frappe.db.count("Property"),
        "units": frappe.db.count("Property Unit"),
        "active_leases": frappe.db.count("Lease", {"status": ["in", ["Active", "Expiring"]]}),
        "pdc_in_hand": frappe.db.count("PDC Register", {"status": ["in", ["Received", "Deposited"]]}),
        "pdc_overdue": frappe.db.count("PDC Register", {
            "status": ["in", ["Received", "Deposited"]],
            "cheque_date": ["<", today()],
        }),
        "open_maintenance": frappe.db.count("Maintenance Job Card", {
            "status": ["in", ["Open", "In Progress"]],
        }),
        "expiring_leases_30d": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [today(), frappe.utils.add_days(today(), 30)]],
        }),
    }

    # Outstanding invoices
    outstanding = frappe.db.sql(
        """
        SELECT COALESCE(SUM(outstanding_amount), 0)
        FROM `tabSales Invoice`
        WHERE docstatus = 1 AND outstanding_amount > 0
        """,
    )
    result["total_outstanding_amount"] = float(outstanding[0][0] or 0)

    return result


# ---------------------------------------------------------------------------
# 4. Provision PropX Roles for a new user
# ---------------------------------------------------------------------------

@frappe.whitelist()
def assign_propx_role(user, role):
    """
    Assign one of the PropX roles to a user.
    Only System Manager can call this.
    """
    frappe.only_for("System Manager")

    VALID_ROLES = [
        "PropX Admin", "Property Manager", "Lease Manager",
        "Maintenance Technician", "Security Guard",
        "Property Owner", "Tenant", "Accountant",
    ]

    if role not in VALID_ROLES:
        frappe.throw(
            f"Invalid role '{role}'. Valid PropX roles: {', '.join(VALID_ROLES)}"
        )

    if not frappe.db.exists("User", user):
        frappe.throw(f"User '{user}' not found.")

    user_doc = frappe.get_doc("User", user)
    existing_roles = [r.role for r in user_doc.roles]

    if role in existing_roles:
        return {"status": "already_assigned", "user": user, "role": role}

    user_doc.append("roles", {"role": role})
    user_doc.save(ignore_permissions=True)

    return {"status": "assigned", "user": user, "role": role}


# ---------------------------------------------------------------------------
# 5. Get audit trail for a document
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_document_audit_trail(doctype, docname, limit=20):
    """
    Return the version history (audit trail) for any PropX document.
    Uses ERPNext's built-in Version DocType.
    """
    frappe.only_for(["System Manager", "PropX Admin", "Property Manager"])

    versions = frappe.get_all(
        "Version",
        filters={
            "ref_doctype": doctype,
            "docname": docname,
        },
        fields=["name", "owner", "creation", "data"],
        order_by="creation desc",
        limit=int(limit),
    )

    # Parse data JSON for each version
    import json
    for v in versions:
        try:
            v["changes"] = json.loads(v.get("data") or "{}")
        except Exception:
            v["changes"] = {}

    return versions


# ---------------------------------------------------------------------------
# 6. Deactivate a PropX Client
# ---------------------------------------------------------------------------

@frappe.whitelist()
def deactivate_client(client_name):
    """Set a PropX Client as inactive (subscription ended / non-payment)."""
    frappe.only_for("System Manager")

    if not frappe.db.exists("PropX Client", client_name):
        frappe.throw(f"PropX Client '{client_name}' not found.")

    frappe.db.set_value("PropX Client", client_name, "is_active", 0)
    frappe.db.commit()

    return {"status": "deactivated", "client": client_name}
