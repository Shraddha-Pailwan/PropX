"""
esign_utils.py — e-Signature integration (DocuSign / SignNow / local).

send_esign_request is enqueued from Lease.send_esign_request().
Configure the provider and credentials in PropX Settings.
"""
import frappe


def send_esign_request(lease):
    """
    Send e-signature request for a lease contract.

    Called via frappe.enqueue — receives lease name as string.
    Provider selection is driven by PropX Settings.esign_provider.
    """
    lease_doc = frappe.get_doc("Lease", lease)

    if not frappe.db.exists("DocType", "PropX Settings"):
        frappe.logger().warning("PropX Settings not found — esign skipped.")
        return

    settings = frappe.get_single("PropX Settings")
    provider = getattr(settings, "esign_provider", None)

    if provider == "DocuSign":
        _send_docusign(lease_doc, settings)
    elif provider == "SignNow":
        _send_signnow(lease_doc, settings)
    else:
        # Log and mark as Sent without external call (manual/offline mode)
        frappe.logger().info(
            f"No esign provider configured. Lease {lease} marked Sent (manual)."
        )

    frappe.db.set_value("Lease", lease, "esign_status", "Sent")
    frappe.db.commit()


def _send_docusign(lease_doc, settings):
    """Placeholder for DocuSign API integration."""
    frappe.logger().info(
        f"DocuSign: would send envelope for lease {lease_doc.name}"
    )


def _send_signnow(lease_doc, settings):
    """Placeholder for SignNow API integration."""
    frappe.logger().info(
        f"SignNow: would send request for lease {lease_doc.name}"
    )
