import frappe
from frappe.model.document import Document
from frappe.utils import time_diff_in_hours, get_datetime


class VisitorParkingLog(Document):

    def validate(self):
        if self.check_out and self.check_in:
            diff = time_diff_in_hours(
                get_datetime(self.check_out),
                get_datetime(self.check_in)
            )
            self.duration_hours = round(diff, 2) if diff > 0 else 0
