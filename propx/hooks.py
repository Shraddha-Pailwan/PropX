app_name = "propx"

fixtures = [
    {
        "doctype": "Workflow",
        "filters": [["name", "=", "Lease Approval Workflow"]]
    }
]
app_title = "PropX"
app_publisher = "Quantbit Technologies"
app_description = "Property Management Platform"
app_email = "contact@quantbit.io"
app_license = "agpl-3.0"

# Installation
after_install = "propx.install.after_install"

# After every bench migrate: re-apply custom fields so deferred Link fields
# (propx_lease, propx_unit, propx_property) get created once those DocTypes exist.
after_migrate = ["propx.property_management.setup.custom_fields.apply_all"]

# Scheduled Tasks
scheduler_events = {
    "hourly": [
        "propx.property_management.tasks.check_sla_breaches",
    ],
    "daily": [
        "propx.property_management.tasks.update_vacancy_days",
        "propx.property_management.tasks.send_lease_expiry_alerts",
        "propx.property_management.tasks.apply_due_rent_escalations",
        "propx.property_management.tasks.send_pdc_due_reminders",
        "propx.property_management.tasks.generate_ppm_work_orders",
        "propx.property_management.tasks.update_coi_statuses",
        "propx.property_management.utils.billing_utils.apply_late_fees",
    ],
    "monthly": [
        "propx.property_management.utils.billing_utils.generate_monthly_invoices",
        "propx.property_management.utils.billing_utils.generate_parking_invoices",
    ],
}

# Document Events
doc_events = {
    "Customer": {
        "after_save": "propx.property_management.hooks_on_customer.after_save"
    },
    "Property Unit": {
        "on_update": "propx.property_management.api.listing_api.auto_create_listing"
    },
    "Company": {
        "after_insert": "propx.property_management.setup.accounts_setup.on_company_insert"
    },
    "Lease": {
        "on_submit": "propx.property_management.api.inspection_api.create_move_in_inspection"
    },
}
