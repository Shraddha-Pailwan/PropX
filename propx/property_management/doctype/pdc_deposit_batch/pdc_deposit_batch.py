import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PDCDepositBatch(Document):

    def validate(self):
        self._calculate_totals()
        self._stamp_deposit_batch_on_pdcs()

    def _calculate_totals(self):
        self.total_cheques = len(self.cheques)
        self.total_amount = sum(flt(row.amount) for row in self.cheques)

    def _stamp_deposit_batch_on_pdcs(self):
        """Link each PDC Register row back to this batch."""
        for row in self.cheques:
            if row.pdc_register:
                frappe.db.set_value(
                    "PDC Register", row.pdc_register,
                    "deposit_batch", self.name
                )
