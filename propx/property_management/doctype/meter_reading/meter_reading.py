"""
meter_reading.py — M07 Utility & Meter Management
Controller for Meter Reading DocType.

On validate  : auto-fill previous reading, compute consumption + amount due.
On submit    : update last reading on the meter; create utility Sales Invoice.
On cancel    : reverse the meter's last_reading back to previous value.
"""
import frappe
from frappe.model.document import Document
from frappe.utils import flt, today


# Maps utility type → billing item code
UTIL_ITEM_MAP = {
    "Electricity":       "UTIL-ELEC",
    "Water":             "UTIL-WATER",
    "Gas":               "SVC-CHARGE",
    "District Cooling":  "SVC-CHARGE",
    "Internet":          "SVC-CHARGE",
}


class MeterReading(Document):

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(self):
        self._fetch_previous_reading()
        self._calculate_consumption()
        self._validate_current_reading()

    def _fetch_previous_reading(self):
        """Pull the most recent submitted reading for this meter."""
        if self.previous_reading:
            return  # already set (e.g. manually overridden)

        last = frappe.get_all(
            "Meter Reading",
            filters={
                "meter": self.meter,
                "docstatus": 1,
                "name": ["!=", self.name or "__new__"],
            },
            fields=["current_reading"],
            order_by="reading_date desc, creation desc",
            limit=1,
        )
        self.previous_reading = flt(last[0].current_reading) if last else 0.0

    def _calculate_consumption(self):
        meter = frappe.get_doc("Utility Meter", self.meter)
        self.unit_of_measure = meter.utility_type
        self.property = meter.property
        self.unit = meter.unit

        self.consumption = max(
            0.0,
            flt(self.current_reading) - flt(self.previous_reading),
        )
        self.amount_due = round(
            self.consumption * flt(meter.tariff_per_unit), 2
        )

    def _validate_current_reading(self):
        if flt(self.current_reading) < flt(self.previous_reading):
            frappe.msgprint(
                f"Current reading ({self.current_reading}) is less than "
                f"previous reading ({self.previous_reading}). "
                "This may indicate a meter replacement or reversal.",
                indicator="orange",
                alert=True,
            )

    # ------------------------------------------------------------------
    # On Submit
    # ------------------------------------------------------------------

    def on_submit(self):
        self._update_meter_last_reading()
        if flt(self.amount_due) > 0:
            inv_name = self._create_utility_invoice()
            if inv_name:
                frappe.db.set_value("Meter Reading", self.name, "invoice", inv_name)

    def _update_meter_last_reading(self):
        frappe.db.set_value("Utility Meter", self.meter, {
            "last_reading": self.current_reading,
            "last_reading_date": self.reading_date,
        })

    def _create_utility_invoice(self):
        """Create a Sales Invoice for the tenant if billing_mode = Charge to Tenant."""
        meter = frappe.get_doc("Utility Meter", self.meter)
        if meter.billing_mode != "Charge to Tenant":
            return None

        if not self.unit:
            return None

        tenant = frappe.db.get_value("Property Unit", self.unit, "current_tenant")
        if not tenant:
            frappe.log_error(
                title="Meter Reading: no tenant",
                message=f"No current_tenant on unit {self.unit} for reading {self.name}",
            )
            return None

        # Resolve company from property
        company = frappe.db.get_value("Property", self.property, "company") or \
                  frappe.defaults.get_global_default("company")

        item_code = UTIL_ITEM_MAP.get(meter.utility_type, "SVC-CHARGE")

        si = frappe.new_doc("Sales Invoice")
        si.customer = tenant
        si.company = company
        si.posting_date = self.reading_date or today()
        si.due_date = today()
        si.propx_unit = self.unit
        si.propx_property = self.property
        si.propx_invoice_type = "Utility"
        si.append("items", {
            "item_code": item_code,
            "qty": self.consumption,
            "rate": flt(meter.tariff_per_unit),
            "description": (
                f"{meter.utility_type} — Meter {meter.meter_number} | "
                f"Reading: {self.reading_date} | "
                f"Units: {self.consumption}"
            ),
        })
        si.insert(ignore_permissions=True)
        return si.name

    # ------------------------------------------------------------------
    # On Cancel
    # ------------------------------------------------------------------

    def on_cancel(self):
        """Restore the meter's last_reading to the previous value."""
        frappe.db.set_value("Utility Meter", self.meter, {
            "last_reading": self.previous_reading,
            "last_reading_date": None,
        })
        # Cancel linked invoice if it was not yet paid
        if self.invoice:
            inv = frappe.get_doc("Sales Invoice", self.invoice)
            if inv.docstatus == 1 and flt(inv.outstanding_amount) == flt(inv.grand_total):
                inv.cancel()
