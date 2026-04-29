"""
finance_api.py
--------------
Whitelisted API endpoints for M04 Finance & GCC Compliance.

VAT return summaries, budget vs actual per property,
and owner disbursement helpers.
"""

import frappe
from frappe.utils import flt, today, get_first_day, get_last_day


# ---------------------------------------------------------------------------
# 1. VAT summary (FTA / GAZT / OTA filing)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_vat_summary(company, from_date, to_date):
    """
    VAT return summary for a given period.

    Returns taxable sales grouped by rate, plus exempt income total.
    """
    taxable = frappe.db.sql(
        """
        SELECT
            stc.rate,
            SUM(stc.base_tax_amount)     AS tax_amount,
            SUM(stc.base_taxable_amount) AS taxable_amount,
            COUNT(DISTINCT si.name)      AS invoice_count
        FROM `tabSales Invoice` si
        JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        WHERE si.docstatus = 1
          AND si.company  = %(company)s
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY stc.rate
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    exempt = frappe.db.sql(
        """
        SELECT COALESCE(SUM(grand_total), 0)
          FROM `tabSales Invoice`
         WHERE docstatus = 1
           AND company   = %(company)s
           AND (taxes_and_charges IS NULL OR taxes_and_charges = '')
           AND posting_date BETWEEN %(from_date)s AND %(to_date)s
           AND propx_lease IS NOT NULL
        """,
        {"company": company, "from_date": from_date, "to_date": to_date},
    )[0][0] or 0

    return {
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "taxable_sales": taxable,
        "exempt_income": flt(exempt),
    }


# ---------------------------------------------------------------------------
# 2. Property budget vs actual
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_property_budget_vs_actual(property_name, year):
    """
    Income and expense actuals for a property's cost centre for a given year.
    Uses GL Entry for actuals (no ERPNext Budget DocType required).
    """
    cc = frappe.db.get_value("Property", property_name, "cost_centre")
    if not cc:
        return {"error": f"No cost centre configured for property {property_name}"}

    income_actual = frappe.db.sql(
        """
        SELECT COALESCE(SUM(credit - debit), 0)
          FROM `tabGL Entry`
         WHERE cost_center = %s
           AND YEAR(posting_date) = %s
           AND account IN (
               SELECT name FROM `tabAccount`
                WHERE account_type = 'Income Account'
           )
           AND is_cancelled = 0
        """,
        (cc, year),
    )[0][0] or 0

    expense_actual = frappe.db.sql(
        """
        SELECT COALESCE(SUM(debit - credit), 0)
          FROM `tabGL Entry`
         WHERE cost_center = %s
           AND YEAR(posting_date) = %s
           AND account IN (
               SELECT name FROM `tabAccount`
                WHERE account_type = 'Expense Account'
           )
           AND is_cancelled = 0
        """,
        (cc, year),
    )[0][0] or 0

    return {
        "property": property_name,
        "cost_centre": cc,
        "year": int(year),
        "income_actual": flt(income_actual),
        "expense_actual": flt(expense_actual),
        "noi_actual": flt(income_actual) - flt(expense_actual),
    }


# ---------------------------------------------------------------------------
# 3. Owner disbursement preview
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_owner_disbursement_preview(owner, from_date, to_date):
    """
    Calculate a disbursement preview for an owner across all their properties.
    Returns per-property rent collected + totals.
    """
    # Find properties owned by this customer
    properties = frappe.get_all(
        "Property",
        filters={"owner": owner},
        fields=["name", "property_name", "cost_centre"],
    )

    rows = []
    total_gross = 0.0

    for prop in properties:
        # Rent collected for this property in the period
        result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(si.grand_total - si.outstanding_amount), 0) AS collected
              FROM `tabSales Invoice` si
             WHERE si.docstatus = 1
               AND si.propx_property = %(prop)s
               AND si.propx_invoice_type = 'Rent'
               AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
            """,
            {"prop": prop.name, "from_date": from_date, "to_date": to_date},
            as_dict=True,
        )
        collected = flt(result[0].collected) if result else 0.0

        # Occupancy: active leases / total units
        total_units = frappe.db.count("Property Unit", {"property": prop.name})
        active_units = frappe.db.count(
            "Property Unit", {"property": prop.name, "status": "Occupied"}
        )
        occupancy = round(active_units / total_units * 100, 1) if total_units else 0.0

        rows.append({
            "property": prop.name,
            "property_name": prop.property_name,
            "gross_rent_collected": collected,
            "occupancy_rate": occupancy,
        })
        total_gross += collected

    settings = frappe.get_single("PropX Settings")
    mgmt_pct = flt(settings.management_fee_pct if hasattr(settings, "management_fee_pct") else 5)
    mgmt_fee = round(total_gross * mgmt_pct / 100, 2)

    return {
        "owner": owner,
        "from_date": from_date,
        "to_date": to_date,
        "properties": rows,
        "gross_rent": total_gross,
        "management_fee_pct": mgmt_pct,
        "management_fee": mgmt_fee,
        "net_disbursement": round(total_gross - mgmt_fee, 2),
    }
