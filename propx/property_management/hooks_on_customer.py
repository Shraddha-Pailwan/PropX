"""
Document event hooks fired on Customer save.
Handles tenant stats refresh, KYC status updates, and payment rating.
Registered via doc_events in hooks.py — M05 implementation.
"""
import frappe
from frappe.utils import today, date_diff, flt


def after_save(doc, method):
    if not doc.is_tenant:
        return
    _update_tenant_stats(doc)
    _refresh_kyc_statuses(doc)
    _set_payment_rating(doc)


def _update_tenant_stats(doc):
    active = frappe.db.count("Lease", {
        "tenant": doc.name,
        "status": ["in", ["Active", "Expiring"]]
    }) if frappe.db.exists("DocType", "Lease") else 0

    arrears = frappe.db.sql("""
        SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
        WHERE customer=%s AND docstatus=1 AND outstanding_amount>0
    """, doc.name)[0][0] or 0

    frappe.db.set_value("Customer", doc.name, {
        "active_leases_count": active,
        "total_arrears": arrears
    })


def _refresh_kyc_statuses(doc):
    kyc_docs = doc.get("kyc_documents")
    if not kyc_docs:
        return
    for kyc in kyc_docs:
        if not kyc.expiry_date:
            continue
        days = date_diff(kyc.expiry_date, today())
        if days < 0:
            new_status = "Expired"
        elif days <= 30:
            new_status = "Expiring Soon"
        else:
            new_status = "Valid"
        if kyc.kyc_status != new_status:
            frappe.db.set_value(
                "Tenant KYC Document", kyc.name, "kyc_status", new_status
            )


def _set_payment_rating(doc):
    bounces = frappe.db.count(
        "PDC Register", {"tenant": doc.name, "status": "Bounced"}
    ) if frappe.db.exists("DocType", "PDC Register") else 0

    overdue = frappe.db.count(
        "Sales Invoice",
        {"customer": doc.name, "status": "Overdue", "docstatus": 1}
    )

    if bounces == 0 and overdue == 0:
        rating = "Excellent"
    elif bounces == 0 and overdue <= 1:
        rating = "Good"
    elif bounces <= 1 and overdue <= 2:
        rating = "Fair"
    else:
        rating = "Poor"

    frappe.db.set_value("Customer", doc.name, "payment_rating", rating)
