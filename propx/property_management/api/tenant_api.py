"""
tenant_api.py
-------------
Whitelisted API endpoints for M05 Tenant & CRM management.

Consumed by the React tenant dashboard and listing screens.
"""

import frappe
from frappe.utils import flt


# ---------------------------------------------------------------------------
# 1. Single tenant profile
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_tenant_profile(tenant):
    """
    Full tenant profile: KYC, leases, recent invoices, recent PDCs.
    """
    doc = frappe.get_doc("Customer", tenant)

    leases = frappe.get_all(
        "Lease",
        filters={"tenant": tenant},
        fields=["name", "unit", "property", "status",
                "start_date", "end_date", "annual_rent", "monthly_rent"],
        order_by="start_date desc",
    )

    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"customer": tenant, "docstatus": 1},
        fields=["name", "posting_date", "grand_total",
                "status", "outstanding_amount", "propx_invoice_type"],
        order_by="posting_date desc",
        limit=10,
    )

    pdcs = frappe.get_all(
        "PDC Register",
        filters={"tenant": tenant},
        fields=["name", "cheque_number", "bank_name",
                "amount", "cheque_date", "status"],
        order_by="cheque_date desc",
        limit=12,
    )

    kyc_alerts = [
        {
            "document_type": k.document_type,
            "document_number": k.document_number,
            "expiry_date": k.expiry_date,
            "kyc_status": k.kyc_status,
        }
        for k in doc.get("kyc_documents", [])
        if k.kyc_status in ("Expiring Soon", "Expired")
    ]

    return {
        "profile": {
            "name": doc.name,
            "customer_name": doc.customer_name,
            "tenant_type": getattr(doc, "tenant_type", None),
            "mobile_no": doc.mobile_no,
            "whatsapp_number": getattr(doc, "whatsapp_number", None),
            "email_id": doc.email_id,
            "preferred_language": getattr(doc, "preferred_language", "English"),
            "payment_rating": getattr(doc, "payment_rating", None),
            "active_leases_count": getattr(doc, "active_leases_count", 0),
            "total_arrears": flt(getattr(doc, "total_arrears", 0)),
            "tenancy_since": getattr(doc, "tenancy_since", None),
        },
        "leases": leases,
        "recent_invoices": invoices,
        "recent_pdcs": pdcs,
        "kyc_alerts": kyc_alerts,
    }


# ---------------------------------------------------------------------------
# 2. Tenant list with filters
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_tenants_list(search=None, tenant_type=None, has_arrears=None,
                     payment_rating=None, page=1, page_size=25):
    """
    Paginated list of tenants with optional filters.
    """
    filters = {"is_tenant": 1}
    if tenant_type:
        filters["tenant_type"] = tenant_type
    if payment_rating:
        filters["payment_rating"] = payment_rating
    if search:
        filters["customer_name"] = ["like", f"%{search}%"]

    tenants = frappe.get_all(
        "Customer",
        filters=filters,
        fields=[
            "name", "customer_name", "tenant_type", "mobile_no",
            "whatsapp_number", "active_leases_count",
            "total_arrears", "payment_rating", "tenancy_since",
        ],
        start=(int(page) - 1) * int(page_size),
        page_length=int(page_size),
        order_by="customer_name asc",
    )

    if has_arrears == "1":
        tenants = [t for t in tenants if flt(t.total_arrears) > 0]

    total = frappe.db.count("Customer", filters)
    return {"tenants": tenants, "total": total}


# ---------------------------------------------------------------------------
# 3. KYC expiry summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_kyc_expiry_alerts(days_ahead=30):
    """
    Returns tenants with KYC documents expiring within days_ahead days.
    Used by the property manager dashboard alert strip.
    """
    from frappe.utils import add_days, today

    cutoff = add_days(today(), int(days_ahead))

    rows = frappe.db.sql(
        """
        SELECT
            k.parent          AS tenant,
            c.customer_name   AS tenant_name,
            k.document_type,
            k.document_number,
            k.expiry_date,
            k.kyc_status
        FROM `tabTenant KYC Document` k
        JOIN `tabCustomer` c ON c.name = k.parent
        WHERE k.expiry_date IS NOT NULL
          AND k.expiry_date <= %(cutoff)s
          AND k.kyc_status NOT IN ('Expired', 'Rejected')
          AND c.is_tenant = 1
        ORDER BY k.expiry_date ASC
        """,
        {"cutoff": cutoff},
        as_dict=True,
    )
    return rows


# ---------------------------------------------------------------------------
# 4. Update tenant payment rating (manual trigger)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def refresh_tenant_stats(tenant):
    """Force-refresh computed stats (arrears, rating, lease count) for a tenant."""
    doc = frappe.get_doc("Customer", tenant)
    if not getattr(doc, "is_tenant", False):
        frappe.throw("Customer is not a tenant.")
    # Trigger the after_save hook logic manually
    from propx.property_management.hooks_on_customer import after_save
    after_save(doc, method=None)
    return {"tenant": tenant, "status": "refreshed"}
