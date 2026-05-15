"""
Property NOI Report — M11 Script Report
Net Operating Income per property for a given period.
Income = collected rent (Sales Invoice)
Expense = purchase invoices posted to property cost centre.
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
            "fieldname": "property_name",
            "label": "Property Name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "fieldname": "gross_income",
            "label": "Gross Income",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "total_expense",
            "label": "Total Expense",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "noi",
            "label": "NOI",
            "fieldtype": "Currency",
            "width": 150,
        },
        {
            "fieldname": "noi_margin",
            "label": "NOI Margin %",
            "fieldtype": "Percent",
            "width": 120,
        },
    ]


def get_filters():
    _today = today()
    return [
        {
            "fieldname": "company",
            "label": "Company",
            "fieldtype": "Link",
            "options": "Company",
        },
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
    ]


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_data(filters):
    prop_filters = {}
    if filters.get("company"):
        prop_filters["company"] = filters["company"]
    if filters.get("property"):
        prop_filters["name"] = filters["property"]

    properties = frappe.get_all(
        "Property",
        filters=prop_filters,
        fields=["name", "property_name", "cost_centre"],
    )

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    rows = []

    for prop in properties:
        # Collected income from Sales Invoices
        income_result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(grand_total - outstanding_amount), 0)
            FROM `tabSales Invoice`
            WHERE propx_property = %s
              AND docstatus = 1
              AND posting_date BETWEEN %s AND %s
            """,
            (prop.name, from_date, to_date),
        )
        gross_income = (income_result[0][0] or 0) if income_result else 0

        # Expenses from Purchase Invoices via cost centre
        expense_result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(grand_total), 0)
            FROM `tabPurchase Invoice`
            WHERE cost_center = %s
              AND docstatus = 1
              AND posting_date BETWEEN %s AND %s
            """,
            (prop.cost_centre, from_date, to_date),
        )
        total_expense = (expense_result[0][0] or 0) if expense_result else 0

        noi = gross_income - total_expense
        noi_margin = round(noi / gross_income * 100, 1) if gross_income else 0.0

        rows.append({
            "property": prop.name,
            "property_name": prop.property_name,
            "gross_income": round(gross_income, 2),
            "total_expense": round(total_expense, 2),
            "noi": round(noi, 2),
            "noi_margin": noi_margin,
        })

    rows.sort(key=lambda r: r["noi"], reverse=True)
    return rows
