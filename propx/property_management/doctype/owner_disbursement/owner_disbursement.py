import frappe
from frappe.model.document import Document
from frappe.utils import flt


class OwnerDisbursement(Document):

    def validate(self):
        self._calc_gross_from_properties()
        self._calc_financials()

    def _calc_gross_from_properties(self):
        """Sum gross_rent_collected from property rows if not manually set."""
        if self.properties:
            total = sum(flt(row.gross_rent_collected) for row in self.properties)
            if total:
                self.gross_rent = total

    def _calc_financials(self):
        gross = flt(self.gross_rent)
        if gross:
            self.management_fee = round(
                gross * flt(self.management_fee_pct) / 100, 2
            )
        self.net_disbursement = round(
            gross
            - flt(self.management_fee)
            - flt(self.maintenance_deductions)
            - flt(self.municipality_fees)
            - flt(self.other_deductions),
            2,
        )
