import frappe


PROPX_ROLES = [
    "PropX Admin",
    "Property Manager",
    "Lease Manager",
    "Maintenance Technician",
    "Security Guard",
    "Property Owner",
    "Tenant",
    "Accountant",
]


def after_install():
    _create_roles()
    _add_custom_fields()
    _create_billing_items()
    _create_default_settings()
    _setup_accounts()
    frappe.db.commit()
    frappe.logger().info("PropX installed successfully.")


def _create_roles():
    for role in PROPX_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert(
                ignore_permissions=True
            )
    frappe.db.commit()


def _create_default_settings():
    if not frappe.db.exists("DocType", "PropX Settings"):
        return
    settings = frappe.get_single("PropX Settings")
    if not settings.late_payment_grace_days:
        settings.late_payment_grace_days = 5
        settings.late_fee_rate = 5
        settings.bounce_penalty_amount = 500
        settings.default_security_deposit_months = 2
        settings.default_notice_period_days = 90
        settings.invoice_generation_day = 1
        settings.save(ignore_permissions=True)


def _add_custom_fields():
    from propx.property_management.setup.custom_fields import apply_all
    apply_all()


def _create_billing_items():
    from propx.property_management.setup.billing_setup import create_items
    create_items()


def _setup_accounts():
    from propx.property_management.setup.accounts_setup import setup_for_company
    for company in frappe.get_all("Company", pluck="name"):
        setup_for_company(company)
