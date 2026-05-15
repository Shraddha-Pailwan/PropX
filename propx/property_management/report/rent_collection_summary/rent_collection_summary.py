"""
Rent Collection Summary — M11 Script Report
Grouped by property for a given date range.
"""
import frappe
from frappe.utils import get_first_day, get_last_day, today


def get_columns():
    return [
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
            "width": 180,
        },
        {
            "fieldname": "tenants",
            "label": "Tenants",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "fieldname": "invoiced",
            "label": "Invoiced",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "collected",
            "label": "Collected",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "outstanding",
            "label": "Outstanding",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "overdue",
            "label": "Overdue",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "collection_rate",
            "label": "Collection Rate %",
            "fieldtype": "Percent",
            "width": 130,
        },
    ]


def get_filters():
    _today = today()
    return [
        {
            "fieldname": "from_date",
            "label": "From Date",
            "fieldtype": "Date",
            "default": str(get_first_day(_today)),
            "reqd": 1,
        },
        {
            "fieldname": "to_date",
            "label": "To Date",
            "fieldtype": "Date",
            "default": str(get_last_day(_today)),
            "reqd": 1,
        },
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
        },
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
        },
    ]


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_data(filters):
    conditions = [
        "si.docstatus = 1",
        "si.propx_lease IS NOT NULL",
        "si.posting_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("property"):
        conditions.append("si.propx_property = %(property)s")
        params["property"] = filters["property"]

    if filters.get("company"):
        conditions.append("si.company = %(company)s")
        params["company"] = filters["company"]

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(
        f"""
        SELECT
            si.propx_property                              AS property,
            COUNT(DISTINCT si.customer)                    AS tenants,
            ROUND(SUM(si.grand_total), 2)                  AS invoiced,
            ROUND(SUM(si.grand_total - si.outstanding_amount), 2) AS collected,
            ROUND(SUM(si.outstanding_amount), 2)           AS outstanding,
            ROUND(SUM(CASE WHEN si.due_date < CURDATE()
                           AND si.outstanding_amount > 0
                      THEN si.outstanding_amount ELSE 0 END), 2) AS overdue,
            ROUND(
                SUM(si.grand_total - si.outstanding_amount)
                / NULLIF(SUM(si.grand_total), 0) * 100,
                1
            )                                              AS collection_rate
        FROM `tabSales Invoice` si
        WHERE {where_clause}
        GROUP BY si.propx_property
        ORDER BY si.propx_property
        """,
        params,
        as_dict=True,
    )
