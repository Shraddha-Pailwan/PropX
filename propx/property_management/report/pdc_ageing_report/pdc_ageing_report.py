"""
PDC Ageing Report — M11 Script Report
Shows all in-hand PDCs ordered by cheque date with days-to-due / overdue.
"""
import frappe


def get_columns():
    return [
        {
            "fieldname": "name",
            "label": "PDC Reference",
            "fieldtype": "Link",
            "options": "PDC Register",
            "width": 140,
        },
        {
            "fieldname": "cheque_number",
            "label": "Cheque No.",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "bank_name",
            "label": "Bank",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "tenant",
            "label": "Tenant",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 120,
        },
        {
            "fieldname": "customer_name",
            "label": "Tenant Name",
            "fieldtype": "Data",
            "width": 160,
        },
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
            "width": 140,
        },
        {
            "fieldname": "amount",
            "label": "Amount",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "cheque_date",
            "label": "Cheque Date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "fieldname": "days_to_due",
            "label": "Days to Due",
            "fieldtype": "Int",
            "width": 110,
            "description": "Negative = overdue",
        },
        {
            "fieldname": "bounce_risk",
            "label": "Bounce Risk",
            "fieldtype": "Check",
            "width": 100,
        },
        {
            "fieldname": "previous_bounces",
            "label": "Prev. Bounces",
            "fieldtype": "Int",
            "width": 110,
        },
    ]


def get_filters():
    return [
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
        },
        {
            "fieldname": "status",
            "label": "Status",
            "fieldtype": "Select",
            "options": "\nReceived\nDeposited",
            "default": "",
        },
        {
            "fieldname": "bounce_risk",
            "label": "Bounce Risk Only",
            "fieldtype": "Check",
            "default": 0,
        },
    ]


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_data(filters):
    conditions = ["p.status IN ('Received', 'Deposited')"]
    params = {}

    if filters.get("property"):
        conditions.append("p.property = %(property)s")
        params["property"] = filters["property"]

    if filters.get("status"):
        conditions.append("p.status = %(status)s")
        params["status"] = filters["status"]

    if filters.get("bounce_risk"):
        conditions.append("p.bounce_risk = 1")

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(
        f"""
        SELECT
            p.name,
            p.cheque_number,
            p.bank_name,
            p.tenant,
            c.customer_name,
            p.property,
            p.amount,
            p.cheque_date,
            p.status,
            DATEDIFF(p.cheque_date, CURDATE())  AS days_to_due,
            p.bounce_risk,
            p.previous_bounces
        FROM `tabPDC Register` p
        LEFT JOIN `tabCustomer` c ON c.name = p.tenant
        WHERE {where_clause}
        ORDER BY p.cheque_date ASC
        """,
        params,
        as_dict=True,
    )
