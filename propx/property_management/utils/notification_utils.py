"""
notification_utils.py
---------------------
Unified notification utilities: WhatsApp (WATI / Twilio) + email fallback.

Usage:
    from propx.property_management.utils.notification_utils import notify_tenant
    notify_tenant("CUST-0001", "Rent Due", "Your rent of AED 5,000 is due on 1 Apr.")
"""

import frappe


def send_whatsapp(to_number, message, template_name=None, params=None):
    """
    Send a WhatsApp message using the configured provider.
    Silently no-ops if provider is 'none' or settings are missing.
    """
    if not to_number:
        return
    try:
        settings = frappe.get_single("PropX Settings")
    except Exception:
        return

    provider = getattr(settings, "whatsapp_provider", "none")
    if provider == "wati":
        _send_wati(to_number, message, template_name, params, settings)
    elif provider == "twilio":
        _send_twilio(to_number, message, settings)


def _send_wati(to, message, template_name, params, settings):
    import requests

    api_url = settings.wati_api_url
    token = settings.get_password("wati_api_token") if settings.wati_api_token else None
    if not api_url or not token:
        return

    number = to.replace("+", "").replace(" ", "")
    try:
        requests.post(
            f"{api_url.rstrip('/')}/api/v1/sendSessionMessage/{number}",
            headers={"Authorization": f"Bearer {token}"},
            json={"messageText": message},
            timeout=10,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "WATI WhatsApp Error")


def _send_twilio(to, message, settings):
    try:
        from twilio.rest import Client
    except ImportError:
        frappe.log_error("Twilio library not installed", "Twilio WhatsApp Error")
        return

    sid = settings.twilio_account_sid
    token = settings.get_password("twilio_auth_token") if settings.twilio_auth_token else None
    from_number = settings.twilio_whatsapp_from
    if not (sid and token and from_number):
        return

    try:
        Client(sid, token).messages.create(
            body=message,
            from_=f"whatsapp:{from_number}",
            to=f"whatsapp:{to}",
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Twilio WhatsApp Error")


def notify_tenant(tenant_name, subject, body):
    """
    Unified notification: WhatsApp + email based on tenant preference.
    Fails gracefully — a notification failure never breaks the caller.
    """
    try:
        tenant = frappe.get_doc("Customer", tenant_name)
    except Exception:
        return

    # WhatsApp
    if getattr(tenant, "whatsapp_number", None):
        send_whatsapp(tenant.whatsapp_number, body)

    # Email
    email = getattr(tenant, "email_id", None)
    if email:
        try:
            frappe.sendmail(
                recipients=[email],
                subject=subject,
                message=body,
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Tenant Email Notification Error")
