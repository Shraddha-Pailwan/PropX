import frappe
from frappe.model.document import Document


class SecurityIncident(Document):

    def after_insert(self):
        """Alert Property Manager in real-time on high-priority incidents."""
        HIGH_PRIORITY = {"Fire", "Theft", "Medical", "Trespass"}
        if self.incident_type in HIGH_PRIORITY:
            frappe.publish_realtime(
                event="security_incident_alert",
                message={
                    "incident": self.name,
                    "type": self.incident_type,
                    "property": self.property,
                    "location": self.location_detail,
                    "datetime": str(self.incident_datetime),
                },
            )

    def validate(self):
        """Auto-set status to Resolved when resolution is filled."""
        if self.resolution and self.status == "Under Investigation":
            pass  # let the user explicitly change status
