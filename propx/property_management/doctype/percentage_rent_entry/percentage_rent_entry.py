import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PercentageRentEntry(Document):

    def validate(self):
        self._fetch_lease_defaults()
        self._calculate_percentage_rent()

    def _fetch_lease_defaults(self):
        if not self.lease:
            return
        lease = frappe.get_doc("Lease", self.lease)
        self.tenant = lease.tenant
        self.property = lease.property
        self.unit = lease.unit
        self.threshold = lease.percentage_rent_threshold
        self.percentage_rate = lease.percentage_rent_pct

    def _calculate_percentage_rent(self):
        overage = max(0, flt(self.gross_sales) - flt(self.threshold))
        self.overage_amount = round(overage, 2)
        self.percentage_rent_due = round(
            overage * flt(self.percentage_rate) / 100, 2
        )
