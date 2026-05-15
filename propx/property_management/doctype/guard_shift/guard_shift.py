import frappe
from frappe.model.document import Document
from frappe.utils import get_time


class GuardShift(Document):

    def validate(self):
        self._validate_shift_times()
        self._check_duplicate_shift()

    def _validate_shift_times(self):
        if self.shift_start and self.shift_end and self.shift_type != "24hr":
            if get_time(self.shift_end) <= get_time(self.shift_start):
                frappe.msgprint(
                    "Shift end time is before or equal to start time. "
                    "This is valid only for overnight shifts.",
                    indicator="orange",
                    alert=True,
                )

    def _check_duplicate_shift(self):
        """Warn if a shift of same type already exists for this property+date."""
        exists = frappe.db.exists("Guard Shift", {
            "property": self.property,
            "shift_date": self.shift_date,
            "shift_type": self.shift_type,
            "name": ["!=", self.name or "__new__"],
        })
        if exists:
            frappe.msgprint(
                f"A {self.shift_type} shift already exists for {self.property} "
                f"on {self.shift_date}.",
                indicator="orange",
                alert=True,
            )
