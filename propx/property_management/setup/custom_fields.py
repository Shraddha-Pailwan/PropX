import frappe


SALES_INVOICE_CUSTOM_FIELDS = [
    {
        "fieldname": "propx_lease",
        "label": "Lease",
        "fieldtype": "Link",
        "options": "Lease",
        "insert_after": "customer",
    },
    {
        "fieldname": "propx_unit",
        "label": "Property Unit",
        "fieldtype": "Link",
        "options": "Property Unit",
        "insert_after": "propx_lease",
    },
    {
        "fieldname": "propx_property",
        "label": "Property",
        "fieldtype": "Link",
        "options": "Property",
        "insert_after": "propx_unit",
    },
    {
        "fieldname": "propx_billing_month",
        "label": "Billing Month",
        "fieldtype": "Date",
        "insert_after": "propx_property",
    },
    {
        "fieldname": "propx_invoice_type",
        "label": "Invoice Type",
        "fieldtype": "Select",
        "options": "Rent\nService Charge\nUtility\nLate Fee\nBounce Penalty\nDeposit\nParking",
        "insert_after": "propx_billing_month",
    },
]

CUSTOMER_CUSTOM_FIELDS = [
    {"fieldname": "is_tenant",            "label": "Is Tenant",             "fieldtype": "Check",    "default": "0",       "insert_after": "customer_type"},
    {"fieldname": "tenant_type",          "label": "Tenant Type",           "fieldtype": "Select",   "options": "Individual\nCorporate", "insert_after": "is_tenant"},
    {"fieldname": "emirates_id",          "label": "Emirates ID No.",        "fieldtype": "Data",     "insert_after": "tenant_type"},
    {"fieldname": "emirates_id_expiry",   "label": "Emirates ID Expiry",     "fieldtype": "Date",     "insert_after": "emirates_id"},
    {"fieldname": "passport_number",      "label": "Passport No.",           "fieldtype": "Data",     "insert_after": "emirates_id_expiry"},
    {"fieldname": "passport_expiry",      "label": "Passport Expiry",        "fieldtype": "Date",     "insert_after": "passport_number"},
    {"fieldname": "visa_number",          "label": "Visa/Residency No.",     "fieldtype": "Data",     "insert_after": "passport_expiry"},
    {"fieldname": "visa_expiry",          "label": "Visa Expiry",            "fieldtype": "Date",     "insert_after": "visa_number"},
    {"fieldname": "nationality",          "label": "Nationality",            "fieldtype": "Link",     "options": "Country", "insert_after": "visa_expiry"},
    {"fieldname": "trade_licence_no",     "label": "Trade Licence No.",      "fieldtype": "Data",     "insert_after": "nationality"},
    {"fieldname": "trade_licence_expiry", "label": "Trade Licence Expiry",   "fieldtype": "Date",     "insert_after": "trade_licence_no"},
    {"fieldname": "company_reg_no",       "label": "Company Reg. No.",       "fieldtype": "Data",     "insert_after": "trade_licence_expiry"},
    {"fieldname": "authorised_signatory", "label": "Authorised Signatory",   "fieldtype": "Data",     "insert_after": "company_reg_no"},
    {"fieldname": "whatsapp_number",      "label": "WhatsApp No.",           "fieldtype": "Data",     "insert_after": "mobile_no"},
    {"fieldname": "preferred_language",   "label": "Preferred Language",     "fieldtype": "Select",   "options": "English\nArabic", "default": "English", "insert_after": "whatsapp_number"},
    {"fieldname": "kyc_documents",        "label": "KYC Documents",          "fieldtype": "Table",    "options": "Tenant KYC Document", "insert_after": "preferred_language"},
    {"fieldname": "active_leases_count",  "label": "Active Leases",          "fieldtype": "Int",      "read_only": 1, "insert_after": "kyc_documents"},
    {"fieldname": "total_arrears",        "label": "Total Arrears",          "fieldtype": "Currency", "read_only": 1, "insert_after": "active_leases_count"},
    {"fieldname": "tenancy_since",        "label": "Tenant Since",           "fieldtype": "Date",     "read_only": 1, "insert_after": "total_arrears"},
    {"fieldname": "payment_rating",       "label": "Payment Rating",         "fieldtype": "Select",   "options": "Excellent\nGood\nFair\nPoor\nNew", "read_only": 1, "insert_after": "tenancy_since"},
    {"fieldname": "credit_score",         "label": "Credit Bureau Score",    "fieldtype": "Int",      "read_only": 1, "insert_after": "payment_rating"},
    {"fieldname": "credit_checked_on",    "label": "Last Credit Check",      "fieldtype": "Date",     "read_only": 1, "insert_after": "credit_score"},
]


LINK_TYPES = ("Link", "Table", "Table MultiSelect")


def _target_doctype_exists(field):
    """Return True if the field's options DocType exists (or field is not a link type)."""
    if field.get("fieldtype") not in LINK_TYPES:
        return True
    target = field.get("options")
    if not target:
        return True
    return bool(frappe.db.exists("DocType", target))


def _create_custom_field(doctype, field):
    if frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field["fieldname"]}):
        return
    cf = frappe.new_doc("Custom Field")
    cf.dt = doctype
    for k, v in field.items():
        cf.set(k, v)
    cf.insert(ignore_permissions=True)


def apply_all():
    """
    Create custom fields. Link/Table fields whose target DocType does not yet
    exist are silently skipped — they must be re-applied once that module is built.
    Call this function again (e.g. from a patch or module setup) after building M01/M02/M05.
    """
    for field in SALES_INVOICE_CUSTOM_FIELDS:
        if not _target_doctype_exists(field):
            continue
        _create_custom_field("Sales Invoice", field)

    for field in CUSTOMER_CUSTOM_FIELDS:
        if not _target_doctype_exists(field):
            continue
        _create_custom_field("Customer", field)

    frappe.db.commit()
