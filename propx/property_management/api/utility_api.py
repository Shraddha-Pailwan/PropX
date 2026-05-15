"""
utility_api.py — M07 Utility & Meter Management API
Whitelisted endpoints for meter management and utility billing.
"""
import frappe
from frappe.utils import flt, today


# ---------------------------------------------------------------------------
# 1. Utility consumption summary for a property
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_utility_summary(property_name, from_date, to_date):
    """
    Consumption and billing summary per meter for a property in a date range.
    Grouped by meter (utility type + unit).
    """
    return frappe.db.sql(
        """
        SELECT
            m.name                          AS meter,
            m.meter_number,
            m.utility_type,
            m.authority,
            m.unit,
            m.billing_mode,
            m.tariff_per_unit,
            COALESCE(SUM(mr.consumption), 0)  AS total_consumption,
            COALESCE(SUM(mr.amount_due), 0)   AS total_billed,
            COUNT(mr.name)                    AS reading_count
        FROM `tabUtility Meter` m
        LEFT JOIN `tabMeter Reading` mr
            ON mr.meter = m.name
            AND mr.docstatus = 1
            AND mr.reading_date BETWEEN %(from_date)s AND %(to_date)s
        WHERE m.property = %(property_name)s
          AND m.status = 'Active'
        GROUP BY m.name
        ORDER BY m.utility_type, m.unit
        """,
        {
            "property_name": property_name,
            "from_date": from_date,
            "to_date": to_date,
        },
        as_dict=True,
    )


# ---------------------------------------------------------------------------
# 2. All meters for a property / unit
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_meters(property_name=None, unit_name=None, status="Active"):
    """Return utility meters filtered by property and/or unit."""
    filters = {}
    if property_name:
        filters["property"] = property_name
    if unit_name:
        filters["unit"] = unit_name
    if status:
        filters["status"] = status

    return frappe.get_all(
        "Utility Meter",
        filters=filters,
        fields=[
            "name", "meter_number", "utility_type", "authority",
            "authority_account", "unit", "property",
            "tariff_per_unit", "currency", "billing_mode",
            "is_smart_meter", "last_reading", "last_reading_date", "status",
        ],
        order_by="utility_type asc, meter_number asc",
    )


# ---------------------------------------------------------------------------
# 3. Recent readings for a meter
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_meter_readings(meter_name, limit=12):
    """Return the last N submitted readings for a meter (for trend charts)."""
    return frappe.get_all(
        "Meter Reading",
        filters={"meter": meter_name, "docstatus": 1},
        fields=[
            "name", "reading_date", "previous_reading",
            "current_reading", "consumption", "amount_due",
            "reading_type", "invoice",
        ],
        order_by="reading_date desc",
        limit=int(limit),
    )


# ---------------------------------------------------------------------------
# 4. Submit a meter reading (convenience wrapper)
# ---------------------------------------------------------------------------

@frappe.whitelist()
def submit_reading(meter_name, current_reading, reading_date=None,
                   reading_type="Manual", reading_image=None):
    """
    Create and submit a Meter Reading in one call.
    Triggers consumption calc + invoice creation automatically.
    """
    doc = frappe.new_doc("Meter Reading")
    doc.meter = meter_name
    doc.current_reading = flt(current_reading)
    doc.reading_date = reading_date or today()
    doc.reading_type = reading_type or "Manual"
    if reading_image:
        doc.reading_image = reading_image

    doc.insert(ignore_permissions=True)
    doc.submit()

    return {
        "name": doc.name,
        "consumption": doc.consumption,
        "amount_due": doc.amount_due,
        "invoice": doc.invoice,
    }


# ---------------------------------------------------------------------------
# 5. Utility KPIs for a property
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_utility_kpis(property_name):
    """
    Quick stats: active meters, total billed this month, unread meters.
    """
    from frappe.utils import get_first_day, get_last_day

    month_start = str(get_first_day(today()))
    month_end = str(get_last_day(today()))

    total_meters = frappe.db.count(
        "Utility Meter", {"property": property_name, "status": "Active"}
    )

    # Meters with at least one reading this month
    read_this_month = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT mr.meter)
        FROM `tabMeter Reading` mr
        JOIN `tabUtility Meter` m ON m.name = mr.meter
        WHERE m.property = %s
          AND mr.docstatus = 1
          AND mr.reading_date BETWEEN %s AND %s
        """,
        (property_name, month_start, month_end),
    )[0][0] or 0

    total_billed = frappe.db.sql(
        """
        SELECT COALESCE(SUM(mr.amount_due), 0)
        FROM `tabMeter Reading` mr
        JOIN `tabUtility Meter` m ON m.name = mr.meter
        WHERE m.property = %s
          AND mr.docstatus = 1
          AND mr.reading_date BETWEEN %s AND %s
        """,
        (property_name, month_start, month_end),
    )[0][0] or 0

    return {
        "total_meters": total_meters,
        "read_this_month": int(read_this_month),
        "unread_this_month": total_meters - int(read_this_month),
        "total_billed_month": flt(total_billed),
    }
