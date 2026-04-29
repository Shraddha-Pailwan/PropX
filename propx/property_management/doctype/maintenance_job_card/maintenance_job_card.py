import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date, time_diff_in_hours, flt, get_datetime


SLA_HOURS = {"Emergency": 2, "High": 8, "Medium": 24, "Low": 72}
APPROVAL_THRESHOLD_AED = 5000


class MaintenanceJobCard(Document):

    def before_insert(self):
        self.opened_at = now_datetime()
        self._set_sla_deadline()

    def validate(self):
        self._update_sla_status()
        self._check_cost_approval()
        self._check_vendor_coi()

    def on_update(self):
        self._track_timestamps()
        self._calculate_resolution_time()
        self._auto_create_po()
        self._notify_tenant_on_completion()

    # ------------------------------------------------------------------
    # SLA
    # ------------------------------------------------------------------

    def _set_sla_deadline(self):
        hours = SLA_HOURS.get(self.priority, 24)
        self.sla_hours = hours
        self.sla_deadline = add_to_date(
            self.opened_at, hours=hours, as_datetime=True
        )

    def _update_sla_status(self):
        if not self.sla_deadline:
            return
        now = now_datetime()
        deadline = get_datetime(self.sla_deadline)

        if self.ticket_status in ("Completed", "Closed"):
            if self.completed_at:
                self.sla_status = (
                    "On Time"
                    if get_datetime(self.completed_at) <= deadline
                    else "Breached"
                )
            return

        if now > deadline:
            self.sla_status = "Breached"
            if not self.breached_at:
                self.breached_at = deadline
        elif time_diff_in_hours(deadline, now) <= 2:
            self.sla_status = "At Risk"
        else:
            self.sla_status = "On Time"

    # ------------------------------------------------------------------
    # Cost approval
    # ------------------------------------------------------------------

    def _check_cost_approval(self):
        threshold = flt(
            frappe.db.get_single_value(
                "PropX Settings", "maintenance_cost_approval_threshold"
            ) or APPROVAL_THRESHOLD_AED
        )
        self.cost_approval_required = bool(
            self.estimated_cost and flt(self.estimated_cost) > threshold
        )

    # ------------------------------------------------------------------
    # Vendor COI validation
    # ------------------------------------------------------------------

    def _check_vendor_coi(self):
        if not self.vendor:
            self.vendor_coi_valid = 0
            return
        valid = frappe.db.exists("Vendor COI", {
            "vendor": self.vendor,
            "status": "Valid",
        })
        self.vendor_coi_valid = 1 if valid else 0
        if self.vendor and not self.vendor_coi_valid:
            frappe.msgprint(
                f"Vendor {self.vendor} has no valid Certificate of Insurance. "
                "Please obtain COI before assigning work.",
                indicator="orange",
            )

    # ------------------------------------------------------------------
    # Timestamps
    # ------------------------------------------------------------------

    def _track_timestamps(self):
        if self.ticket_status == "Assigned" and not self.assigned_at:
            frappe.db.set_value(
                "Maintenance Job Card", self.name, "assigned_at", now_datetime()
            )
        elif self.ticket_status in ("Completed", "Closed") and not self.completed_at:
            frappe.db.set_value(
                "Maintenance Job Card", self.name, "completed_at", now_datetime()
            )

    def _calculate_resolution_time(self):
        if self.completed_at and self.opened_at:
            hours = round(
                time_diff_in_hours(self.completed_at, self.opened_at), 1
            )
            frappe.db.set_value(
                "Maintenance Job Card", self.name, "resolution_hours", hours
            )

    # ------------------------------------------------------------------
    # Auto Purchase Order
    # ------------------------------------------------------------------

    def _auto_create_po(self):
        if not (self.vendor and self.cost_approved
                and self.estimated_cost and not self.purchase_order):
            return
        po = frappe.new_doc("Purchase Order")
        po.supplier = self.vendor
        po.schedule_date = frappe.utils.add_days(frappe.utils.today(), 3)
        po.append("items", {
            "item_code": "MAINT-SERVICE",
            "qty": 1,
            "rate": flt(self.estimated_cost),
            "description": f"Maintenance: {self.subject} | {self.name}",
        })
        po.insert(ignore_permissions=True)
        frappe.db.set_value(
            "Maintenance Job Card", self.name, "purchase_order", po.name
        )

    # ------------------------------------------------------------------
    # Tenant notification on completion
    # ------------------------------------------------------------------

    def _notify_tenant_on_completion(self):
        if not (self.ticket_status == "Completed"
                and self.reported_by_tenant
                and not self.tenant_notified
                and self.unit):
            return
        tenant = frappe.db.get_value("Property Unit", self.unit, "current_tenant")
        if not tenant:
            return
        try:
            from propx.property_management.utils.notification_utils import notify_tenant
            notify_tenant(
                tenant,
                f"Maintenance request #{self.name} completed",
                f"Your maintenance request ({self.subject}) has been completed. "
                f"Please rate your satisfaction (1–5) in the tenant portal.",
            )
            frappe.db.set_value(
                "Maintenance Job Card", self.name, "tenant_notified", 1
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Maintenance Completion Notification")
