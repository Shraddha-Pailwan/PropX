"""
billing_api.py
--------------
Whitelisted API endpoints for M03 Billing & PDC management.

Consumed by the React billing dashboard and PDC management screens.
"""

import frappe
from frappe.utils import flt, getdate, nowdate, add_days


# ---------------------------------------------------------------------------
# 1. Billing KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_billing_kpis(company=None, property_name=None):
    """
    Dashboard KPIs for the billing overview card.

    Returns total invoiced, total collected, total outstanding,
    and overdue amount for the current month.
    """
    filters = {"docstatus": 1}
    if company:
        filters["company"] = company

    # Base query with optional property join
    property_filter = ""
    params = {}
    if property_name:
        property_filter = """
            AND EXISTS (
                SELECT 1 FROM `tabSales Invoice Item` sii
                 WHERE sii.parent = si.name
                   AND sii.propx_property = %(property_name)s
            )
        """
        params["property_name"] = property_name

    sql = f"""
        SELECT
            COALESCE(SUM(si.grand_total), 0)         AS total_invoiced,
            COALESCE(SUM(si.grand_total
                     - si.outstanding_amount), 0)    AS total_collected,
            COALESCE(SUM(si.outstanding_amount), 0)  AS total_outstanding,
            COALESCE(SUM(
                CASE WHEN si.due_date < CURDATE()
                          AND si.outstanding_amount > 0
                     THEN si.outstanding_amount
                     ELSE 0
                END
            ), 0) AS overdue_amount
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          {"AND si.company = %(company)s" if company else ""}
          {property_filter}
    """
    if company:
        params["company"] = company

    result = frappe.db.sql(sql, params, as_dict=True)
    row = result[0] if result else {}
    return {
        "total_invoiced": flt(row.get("total_invoiced")),
        "total_collected": flt(row.get("total_collected")),
        "total_outstanding": flt(row.get("total_outstanding")),
        "overdue_amount": flt(row.get("overdue_amount")),
    }


# ---------------------------------------------------------------------------
# 2. PDC KPIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_pdc_kpis(company=None, property_name=None):
    """
    PDC pipeline summary.

    Returns counts and totals by status for the PDC Register.
    """
    filters = {}
    if property_name:
        filters["property"] = property_name

    statuses = ["Received", "Deposited", "Cleared", "Bounced", "Replaced", "Cancelled"]
    kpis = {}

    for status in statuses:
        f = {**filters, "status": status}
        result = frappe.db.sql(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
              FROM `tabPDC Register`
             WHERE status = %(status)s
               {prop_filter}
            """.format(
                prop_filter="AND property = %(property)s" if property_name else ""
            ),
            {
                "status": status,
                **({"property": property_name} if property_name else {}),
            },
            as_dict=True,
        )
        row = result[0] if result else {}
        kpis[status.lower()] = {
            "count": int(row.get("cnt") or 0),
            "total": flt(row.get("total")),
        }

    # Bounce rate
    total_processed = (
        kpis["cleared"]["count"] + kpis["bounced"]["count"]
    )
    kpis["bounce_rate"] = round(
        kpis["bounced"]["count"] / total_processed * 100, 1
    ) if total_processed else 0.0

    return kpis


# ---------------------------------------------------------------------------
# 3. Upcoming PDCs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_upcoming_pdc(days_ahead=30, property_name=None, limit=50):
    """
    Return PDCs due for presentation within the next `days_ahead` days.
    Used by the 'PDC Calendar' view in the React dashboard.
    """
    from_date = nowdate()
    to_date = add_days(nowdate(), int(days_ahead))

    filters = {
        "status": ["in", ["Received", "Deposited"]],
        "cheque_date": ["between", [from_date, to_date]],
    }
    if property_name:
        filters["property"] = property_name

    return frappe.get_all(
        "PDC Register",
        filters=filters,
        fields=[
            "name", "cheque_number", "bank_name", "amount", "currency",
            "cheque_date", "status", "tenant", "lease", "property", "unit",
            "against_invoice", "bounce_risk", "deposit_batch",
        ],
        order_by="cheque_date asc",
        limit=int(limit),
    )


# ---------------------------------------------------------------------------
# 4. Mark PDC Deposited
# ---------------------------------------------------------------------------

@frappe.whitelist()
def mark_pdc_deposited(pdc_name):
    """
    Set a PDC's status to Deposited. Convenience wrapper around
    PDCRegister.deposit() for bulk operations from the dashboard.
    """
    doc = frappe.get_doc("PDC Register", pdc_name)
    doc.deposit()
    return {"pdc": pdc_name, "status": "Deposited"}


# ---------------------------------------------------------------------------
# 5. Mark PDC Cleared
# ---------------------------------------------------------------------------

@frappe.whitelist()
def mark_pdc_cleared(pdc_name):
    """
    Set a PDC's status to Cleared and create a Payment Entry.
    Wrapper around PDCRegister.clear().
    """
    doc = frappe.get_doc("PDC Register", pdc_name)
    pe_name = doc.clear()
    return {"pdc": pdc_name, "status": "Cleared", "payment_entry": pe_name}


# ---------------------------------------------------------------------------
# 6. Mark PDC Bounced
# ---------------------------------------------------------------------------

@frappe.whitelist()
def mark_pdc_bounced(pdc_name, reason=None):
    """
    Set a PDC's status to Bounced, create a penalty invoice (if applicable),
    and send realtime notification.
    Wrapper around PDCRegister.bounce().
    """
    doc = frappe.get_doc("PDC Register", pdc_name)
    penalty_inv = doc.bounce(reason=reason)
    return {
        "pdc": pdc_name,
        "status": "Bounced",
        "penalty_invoice": penalty_inv,
    }


# ---------------------------------------------------------------------------
# 7. Overdue Invoices
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_overdue_invoices(company=None, property_name=None, limit=100):
    """
    Return unpaid Sales Invoices whose due_date has passed.
    Used by the collections team for follow-up.
    """
    params = {"today": nowdate()}
    company_filter = "AND si.company = %(company)s" if company else ""
    property_filter = ""

    if company:
        params["company"] = company
    if property_name:
        params["property_name"] = property_name
        property_filter = """
            AND EXISTS (
                SELECT 1 FROM `tabSales Invoice Item` sii
                 WHERE sii.parent = si.name
                   AND sii.propx_property = %(property_name)s
            )
        """

    rows = frappe.db.sql(
        f"""
        SELECT
            si.name,
            si.customer,
            si.customer_name,
            si.posting_date,
            si.due_date,
            si.grand_total,
            si.outstanding_amount,
            DATEDIFF(CURDATE(), si.due_date) AS days_overdue
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < %(today)s
          {company_filter}
          {property_filter}
        ORDER BY days_overdue DESC
        LIMIT %(limit)s
        """,
        {**params, "limit": int(limit)},
        as_dict=True,
    )
    return rows
