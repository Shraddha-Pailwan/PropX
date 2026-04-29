"""
service_charge_utils.py
-----------------------
Annual service charge (CAM) reconciliation utilities.

Flow:
  1. Each lease has a `service_charge_annual` estimate billed monthly/quarterly
     via billing_utils.generate_rent_invoices.
  2. At year-end (or on demand), the property manager runs reconciliation.
  3. This module calculates total billed vs actual cost centre expenditure,
     then raises a top-up Sales Invoice or a Credit Note for the difference.

Usage (whitelisted endpoint in billing_api.py):
    frappe.call("propx.property_management.utils.service_charge_utils.reconcile_service_charges",
                property=..., year=...)
"""

import frappe
from frappe.utils import flt, getdate, get_first_day, get_last_day, nowdate
from datetime import date


# ---------------------------------------------------------------------------
# Main reconciliation entry point
# ---------------------------------------------------------------------------

@frappe.whitelist()
def reconcile_service_charges(property_name, year=None):
    """
    Reconcile service charges for all active leases on a property for a
    given year.

    Returns a list of dicts describing the action taken per lease.
    """
    year = int(year) if year else getdate(nowdate()).year
    period_start = date(year, 1, 1)
    period_end = date(year, 12, 31)

    # Fetch all leases that overlap the year for this property
    leases = frappe.db.sql(
        """
        SELECT name, tenant, company,
               service_charge_annual,
               start_date, end_date
          FROM `tabLease`
         WHERE property = %(property)s
           AND status NOT IN ('Draft', 'Cancelled')
           AND start_date <= %(period_end)s
           AND (end_date IS NULL OR end_date >= %(period_start)s)
        """,
        {
            "property": property_name,
            "period_start": period_start,
            "period_end": period_end,
        },
        as_dict=True,
    )

    results = []
    for lease in leases:
        result = _reconcile_lease(lease, period_start, period_end, year)
        results.append(result)

    return results


# ---------------------------------------------------------------------------
# Per-lease reconciliation
# ---------------------------------------------------------------------------

def _reconcile_lease(lease, period_start, period_end, year):
    """Compare billed service charges to actual costs, raise adjustment doc."""
    billed = _get_billed_service_charges(lease.name, period_start, period_end)
    actual = _get_actual_service_charge_cost(lease, period_start, period_end)
    diff = flt(actual) - flt(billed)

    result = {
        "lease": lease.name,
        "tenant": lease.tenant,
        "billed": billed,
        "actual": actual,
        "difference": diff,
        "action": None,
        "document": None,
    }

    if abs(diff) < 1:
        # Immaterial — no adjustment needed
        result["action"] = "no_adjustment"
        return result

    if diff > 0:
        # Tenant underpaid — raise top-up Sales Invoice
        doc_name = _raise_topup_invoice(lease, diff, year)
        result["action"] = "topup_invoice"
        result["document"] = doc_name
    else:
        # Tenant overpaid — raise Credit Note
        doc_name = _raise_credit_note(lease, abs(diff), year)
        result["action"] = "credit_note"
        result["document"] = doc_name

    return result


# ---------------------------------------------------------------------------
# Helpers: calculate billed and actual amounts
# ---------------------------------------------------------------------------

def _get_billed_service_charges(lease_name, period_start, period_end):
    """
    Sum all service-charge line items on submitted Sales Invoices for this
    lease within the period.
    """
    result = frappe.db.sql(
        """
        SELECT COALESCE(SUM(sii.amount), 0) AS total
          FROM `tabSales Invoice Item` sii
          JOIN `tabSales Invoice` si ON si.name = sii.parent
         WHERE si.docstatus = 1
           AND sii.propx_lease = %(lease)s
           AND sii.propx_charge_type = 'Service Charge'
           AND si.posting_date BETWEEN %(start)s AND %(end)s
        """,
        {"lease": lease_name, "start": period_start, "end": period_end},
    )
    return flt(result[0][0]) if result else 0.0


def _get_actual_service_charge_cost(lease, period_start, period_end):
    """
    Approximate actual cost as: lease.service_charge_annual prorated for
    the months the lease was active within the period.

    A real implementation would query the property's cost centre GL entries
    for maintenance/management expense accounts, then apportion by unit area.
    We use the estimate here so this function can be overridden per deployment.
    """
    lease_start = getdate(lease.start_date)
    lease_end = getdate(lease.end_date) if lease.end_date else getdate(period_end)

    effective_start = max(lease_start, getdate(period_start))
    effective_end = min(lease_end, getdate(period_end))

    if effective_end < effective_start:
        return 0.0

    # Count active months (approximate)
    months_active = _months_between(effective_start, effective_end)
    annual = flt(lease.service_charge_annual)
    return round(annual * months_active / 12, 2)


def _months_between(d1, d2):
    """Return fractional months between two dates."""
    days = (d2 - d1).days + 1
    return round(days / 30.44, 4)


# ---------------------------------------------------------------------------
# Document creation helpers
# ---------------------------------------------------------------------------

def _raise_topup_invoice(lease, amount, year):
    company = lease.company
    income_account = frappe.db.get_value(
        "Company", company, "default_income_account"
    )
    inv = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": lease.tenant,
        "company": company,
        "posting_date": nowdate(),
        "due_date": nowdate(),
        "remarks": (
            f"Service charge reconciliation top-up for lease {lease.name} "
            f"– Year {year}"
        ),
        "items": [{
            "item_name": "Service Charge Reconciliation",
            "description": (
                f"Annual service charge reconciliation ({year}) – "
                f"actual exceeded estimate by AED {amount:,.2f}"
            ),
            "qty": 1,
            "rate": amount,
            "income_account": income_account,
            "propx_lease": lease.name,
            "propx_charge_type": "Service Charge",
        }],
    })
    inv.insert(ignore_permissions=True)
    inv.submit()
    return inv.name


def _raise_credit_note(lease, amount, year):
    company = lease.company
    income_account = frappe.db.get_value(
        "Company", company, "default_income_account"
    )
    # Find any submitted invoice for this lease to return against
    return_against = frappe.db.get_value(
        "Sales Invoice",
        {"customer": lease.tenant, "company": company, "docstatus": 1},
        "name",
        order_by="posting_date desc",
    )

    cn = frappe.get_doc({
        "doctype": "Sales Invoice",
        "customer": lease.tenant,
        "company": company,
        "posting_date": nowdate(),
        "due_date": nowdate(),
        "is_return": 1,
        "return_against": return_against,
        "remarks": (
            f"Service charge reconciliation credit for lease {lease.name} "
            f"– Year {year}"
        ),
        "items": [{
            "item_name": "Service Charge Reconciliation",
            "description": (
                f"Annual service charge reconciliation ({year}) – "
                f"estimate exceeded actual by AED {amount:,.2f}"
            ),
            "qty": -1,
            "rate": amount,
            "income_account": income_account,
            "propx_lease": lease.name,
            "propx_charge_type": "Service Charge",
        }],
    })
    cn.insert(ignore_permissions=True)
    cn.submit()
    return cn.name
