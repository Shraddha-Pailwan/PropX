import frappe
from frappe.model.document import Document
from frappe.utils import getdate, today


class PropXClient(Document):

    def validate(self):
        self._check_subscription_dates()
        self._check_unit_limit()

    def _check_subscription_dates(self):
        if (self.subscription_start and self.subscription_end
                and getdate(self.subscription_end) < getdate(self.subscription_start)):
            frappe.throw("Subscription End date cannot be before Start date.")

        # Auto-deactivate expired subscriptions
        if self.subscription_end and getdate(self.subscription_end) < getdate(today()):
            if self.is_active:
                self.is_active = 0
                frappe.msgprint(
                    f"Client '{self.client_name}' subscription expired. "
                    "Marked as inactive.",
                    alert=True,
                )

    def _check_unit_limit(self):
        if not self.max_units or not self.company:
            return
        # Property Unit doesn't have company directly; count via Property
        actual = frappe.db.sql(
            """
            SELECT COUNT(*) FROM `tabProperty Unit` pu
            JOIN `tabProperty` p ON p.name = pu.property
            WHERE p.company = %s
            """,
            self.company,
        )[0][0] or 0
        if actual > self.max_units:
            frappe.msgprint(
                f"Warning: this company has {actual} units, "
                f"which exceeds the plan limit of {self.max_units}.",
                indicator="orange",
                alert=True,
            )
