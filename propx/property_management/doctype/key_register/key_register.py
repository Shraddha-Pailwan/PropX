import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class KeyRegister(Document):

    def validate(self):
        self._sync_status()
        self._validate_dates()

    def _sync_status(self):
        """Auto-derive status from holder / returned_date."""
        if self.returned_date:
            self.status = "Available"
            self.current_holder = None
        elif self.current_holder and self.issued_date:
            self.status = "Issued"

    def _validate_dates(self):
        if (self.issued_date and self.returned_date
                and getdate(self.returned_date) < getdate(self.issued_date)):
            frappe.throw("Returned Date cannot be before Issued Date.")

    def on_update(self):
        """Alert if a master key is marked Lost."""
        if self.key_type == "Master Key" and self.status == "Lost":
            frappe.publish_realtime(
                event="master_key_lost",
                message={
                    "key": self.name,
                    "key_number": self.key_number,
                    "property": self.property,
                },
            )
