"""
Lease Expiry Register — M11 Script Report
Shows active/expiring leases within a date range, sorted by expiry date.
"""
import frappe
from frappe.utils import add_days, today


def get_columns():
    return [
        {
            "fieldname": "name",
            "label": "Lease",
            "fieldtype": "Link",
            "options": "Lease",
            "width": 140,
        },
        {
            "fieldname": "tenant_name",
            "label": "Tenant",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "fieldname": "unit",
            "label": "Unit",
            "fieldtype": "Link",
            "options": "Property Unit",
            "width": 120,
        },
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
            "width": 150,
        },
        {
            "fieldname": "lease_category",
            "label": "Category",
            "fieldtype": "Data",
            "width": 110,
        },
        {
            "fieldname": "start_date",
            "label": "Start Date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "end_date",
            "label": "End Date",
            "fieldtype": "Date",
            "width": 100,
        },
        {
            "fieldname": "annual_rent",
            "label": "Annual Rent",
            "fieldtype": "Currency",
            "width": 130,
        },
        {
            "fieldname": "renewal_status",
            "label": "Renewal Status",
            "fieldtype": "Data",
            "width": 130,
        },
        {
            "fieldname": "days_remaining",
            "label": "Days Remaining",
            "fieldtype": "Int",
            "width": 120,
        },
    ]


def get_filters():
    _today = today()
    return [
        {
            "fieldname": "from_date",
            "label": "Expiry From",
            "fieldtype": "Date",
            "default": _today,
            "reqd": 1,
        },
        {
            "fieldname": "to_date",
            "label": "Expiry To",
            "fieldtype": "Date",
            "default": str(add_days(_today, 90)),
            "reqd": 1,
        },
        {
            "fieldname": "property",
            "label": "Property",
            "fieldtype": "Link",
            "options": "Property",
        },
        {
            "fieldname": "lease_category",
            "label": "Category",
            "fieldtype": "Select",
            "options": "\nResidential\nCommercial\nIndustrial\nShort-Term",
        },
    ]


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_data(filters):
    conditions = [
        "l.status IN ('Active', 'Expiring')",
        "l.end_date BETWEEN %(from_date)s AND %(to_date)s",
    ]
    params = {
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }

    if filters.get("property"):
        conditions.append("l.property = %(property)s")
        params["property"] = filters["property"]

    if filters.get("lease_category"):
        conditions.append("l.lease_category = %(lease_category)s")
        params["lease_category"] = filters["lease_category"]

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(
        f"""
        SELECT
            l.name,
            l.tenant_name,
            l.unit,
            l.property,
            l.lease_category,
            l.start_date,
            l.end_date,
            l.annual_rent,
            l.renewal_status,
            DATEDIFF(l.end_date, CURDATE()) AS days_remaining
        FROM `tabLease` l
        WHERE {where_clause}
        ORDER BY l.end_date ASC
        """,
        params,
        as_dict=True,
    )
