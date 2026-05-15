"""
Occupancy & Vacancy Analysis — M11 Script Report
Grouped by property and usage type.
"""
import frappe


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
            "fieldname": "usage_type",
            "label": "Unit Type",
            "fieldtype": "Data",
            "width": 120,
        },
        {
            "fieldname": "total_units",
            "label": "Total Units",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "fieldname": "occupied",
            "label": "Occupied",
            "fieldtype": "Int",
            "width": 90,
        },
        {
            "fieldname": "vacant",
            "label": "Vacant",
            "fieldtype": "Int",
            "width": 80,
        },
        {
            "fieldname": "occupancy_pct",
            "label": "Occupancy %",
            "fieldtype": "Percent",
            "width": 110,
        },
        {
            "fieldname": "avg_days_vacant",
            "label": "Avg Days Vacant",
            "fieldtype": "Float",
            "width": 130,
        },
        {
            "fieldname": "monthly_revenue",
            "label": "Monthly Revenue (AED)",
            "fieldtype": "Currency",
            "width": 170,
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
            "fieldname": "usage_type",
            "label": "Unit Type",
            "fieldtype": "Select",
            "options": "\nResidential\nCommercial\nIndustrial\nShort-Term Rental",
        },
    ]


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_data(filters):
    conditions = ["pu.status != 'Decommissioned'"]
    params = {}

    if filters.get("property"):
        conditions.append("pu.property = %(property)s")
        params["property"] = filters["property"]

    if filters.get("usage_type"):
        conditions.append("pu.usage_type = %(usage_type)s")
        params["usage_type"] = filters["usage_type"]

    where_clause = " AND ".join(conditions)

    return frappe.db.sql(
        f"""
        SELECT
            pu.property,
            pu.usage_type,
            COUNT(*)                                                          AS total_units,
            SUM(pu.status = 'Occupied')                                       AS occupied,
            SUM(pu.status = 'Vacant')                                         AS vacant,
            ROUND(SUM(pu.status = 'Occupied') / COUNT(*) * 100, 1)           AS occupancy_pct,
            ROUND(AVG(CASE WHEN pu.status = 'Vacant' THEN pu.days_vacant END), 1)
                                                                              AS avg_days_vacant,
            ROUND(SUM(CASE WHEN pu.status = 'Occupied'
                      THEN COALESCE(pu.last_agreed_rent, 0) / 12
                      ELSE 0 END), 0)                                         AS monthly_revenue
        FROM `tabProperty Unit` pu
        WHERE {where_clause}
        GROUP BY pu.property, pu.usage_type
        ORDER BY pu.property, pu.usage_type
        """,
        params,
        as_dict=True,
    )
