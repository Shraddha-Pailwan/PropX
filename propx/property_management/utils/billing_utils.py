"""
Billing utilities: monthly rent invoicing, late fees, PDC entry creation,
parking invoices. Full implementations filled in during M03 build.
"""
import frappe
from frappe.utils import today, getdate, get_first_day, flt, add_days
from datetime import date


def generate_monthly_invoices():
    """
    Run on 1st of each month via scheduler.
    Creates Sales Invoices for all active leases due for billing.
    """
    active_leases = frappe.get_all(
        "Lease",
        filters={"status": ["in", ["Active", "Expiring"]]},
        fields=["name", "tenant", "unit", "property", "annual_rent",
                "monthly_rent", "currency", "is_vat_applicable",
                "vat_rate", "service_charge_monthly",
                "start_date", "end_date", "company"]
    )
    created = []
    for lease in active_leases:
        if _is_within_term(lease):
            inv = _create_rent_invoice(lease)
            if inv:
                created.append(inv)
    return created


def _is_within_term(lease):
    t = getdate(today())
    return getdate(lease.start_date) <= t <= getdate(lease.end_date)


def _create_rent_invoice(lease):
    t = getdate(today())
    month_start = date(t.year, t.month, 1)

    existing = frappe.db.exists("Sales Invoice", {
        "propx_lease": lease.name,
        "propx_billing_month": str(month_start),
        "docstatus": ["!=", 2]
    })
    if existing:
        return None

    unit_type = frappe.db.get_value("Property Unit", lease.unit, "usage_type")
    item_map = {
        "Residential":       "RENT-RES",
        "Commercial":        "RENT-COM",
        "Industrial":        "RENT-IND",
        "Short-Term Rental": "RENT-STR",
    }
    item_code = item_map.get(unit_type, "RENT-COM")

    cost_centre = frappe.db.get_value("Property", lease.property, "cost_centre")
    si = frappe.new_doc("Sales Invoice")
    si.customer = lease.tenant
    si.company = lease.company
    si.currency = lease.currency or "AED"
    si.due_date = str(month_start)
    si.cost_center = cost_centre
    si.propx_lease = lease.name
    si.propx_unit = lease.unit
    si.propx_property = lease.property
    si.propx_billing_month = str(month_start)
    si.propx_invoice_type = "Rent"

    si.append("items", {
        "item_code": item_code,
        "qty": 1,
        "rate": flt(lease.monthly_rent),
        "description": f"Rent: {lease.unit} | {month_start.strftime('%B %Y')}"
    })

    if flt(lease.service_charge_monthly) > 0:
        si.append("items", {
            "item_code": "SVC-CHARGE",
            "qty": 1,
            "rate": flt(lease.service_charge_monthly),
            "description": f"Service charge: {month_start.strftime('%B %Y')}"
        })

    if lease.is_vat_applicable and flt(lease.vat_rate) > 0:
        vat_account = _get_vat_account(lease.company, lease.property)
        si.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": vat_account,
            "description": f"VAT @ {lease.vat_rate}%",
            "rate": flt(lease.vat_rate)
        })

    si.insert(ignore_permissions=True)
    return si.name


def _get_vat_account(company, property_name):
    country = frappe.db.get_value("Property", property_name, "country")
    account_map = {
        "United Arab Emirates": "VAT Payable - FTA",
        "Saudi Arabia":         "VAT Payable - GAZT",
        "Oman":                 "VAT Payable - OTA",
    }
    abbr = frappe.db.get_value("Company", company, "abbr")
    base = account_map.get(country, "VAT Payable - FTA")
    return f"{base} - {abbr}"


def apply_late_fees():
    """
    Daily: charge late payment fee on unpaid invoices past grace period.
    """
    if not frappe.db.exists("DocType", "PropX Settings"):
        return
    settings = frappe.get_single("PropX Settings")
    grace_days = int(settings.late_payment_grace_days or 5)
    cutoff = add_days(today(), -grace_days)

    overdue = frappe.db.sql("""
        SELECT si.name, si.customer, si.propx_lease,
               si.propx_unit, si.propx_property, si.outstanding_amount,
               si.company
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < %(cutoff)s
          AND si.propx_invoice_type = 'Rent'
          AND si.propx_lease IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM `tabSales Invoice` lf
              WHERE lf.propx_lease = si.propx_lease
                AND lf.propx_invoice_type = 'Late Fee'
                AND lf.propx_billing_month = si.propx_billing_month
                AND lf.docstatus != 2
          )
    """, {"cutoff": cutoff}, as_dict=True)

    for inv in overdue:
        fee_rate = flt(settings.late_fee_rate or 0.05)
        fee_amount = round(flt(inv.outstanding_amount) * fee_rate, 2)
        if fee_amount < 50:
            continue
        lf = frappe.new_doc("Sales Invoice")
        lf.customer = inv.customer
        lf.company = inv.company
        lf.propx_lease = inv.propx_lease
        lf.propx_unit = inv.propx_unit
        lf.propx_property = inv.propx_property
        lf.propx_invoice_type = "Late Fee"
        lf.due_date = today()
        lf.append("items", {
            "item_code": "LATE-FEE",
            "qty": 1,
            "rate": fee_amount,
            "description": f"Late payment penalty — Invoice {inv.name}"
        })
        lf.insert(ignore_permissions=True)


def create_pdc_entries(lease):
    """
    Called via enqueue from Lease.on_submit.
    Creates PDC Register records from lease.pdc_schedule.
    """
    if not frappe.db.exists("DocType", "PDC Register"):
        return
    lease_doc = frappe.get_doc("Lease", lease)
    for row in lease_doc.pdc_schedule:
        if row.cheque_status == "Pending" and not row.pdc_register_ref:
            pdc = frappe.new_doc("PDC Register")
            pdc.tenant = lease_doc.tenant
            pdc.lease = lease_doc.name
            pdc.property = lease_doc.property
            pdc.unit = lease_doc.unit
            pdc.amount = row.amount
            pdc.cheque_date = row.due_date
            pdc.period_from = row.period_from
            pdc.period_to = row.period_to
            pdc.status = "Received"
            pdc.insert(ignore_permissions=True)
            frappe.db.set_value(
                "PDC Cheque Row", row.name,
                "pdc_register_ref", pdc.name
            )
    frappe.db.commit()


def generate_parking_invoices():
    """Monthly: invoice standalone parking leases."""
    if not frappe.db.exists("DocType", "Parking Lease"):
        return
    active = frappe.get_all(
        "Parking Lease",
        {"status": "Active"},
        fields=["name", "bay", "tenant", "monthly_charge", "currency", "company"]
    )
    for pl in active:
        si = frappe.new_doc("Sales Invoice")
        si.customer = pl.tenant
        si.company = pl.company
        si.propx_invoice_type = "Parking"
        si.due_date = today()
        si.append("items", {
            "item_code": "PARKING-FEE",
            "qty": 1,
            "rate": pl.monthly_charge,
            "description": f"Parking bay — {pl.bay}"
        })
        si.insert(ignore_permissions=True)
