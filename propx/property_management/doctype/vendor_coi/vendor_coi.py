import frappe
from frappe.model.document import Document
from frappe.utils import today, add_days, getdate


class VendorCOI(Document):

    def validate(self):
        self._update_status()

    def _update_status(self):
        if not self.valid_to:
            return
        t = getdate(today())
        exp = getdate(self.valid_to)
        if t > exp:
            self.status = "Expired"
        elif t >= getdate(add_days(self.valid_to, -30)):
            self.status = "Expiring Soon"
        else:
            self.status = "Valid"
