import frappe


# Maps item_code → income/expense account name (without company abbr suffix)
ITEM_ACCOUNT_MAP = {
    "RENT-RES":      "Rental Income - Residential",
    "RENT-COM":      "Rental Income - Commercial",
    "RENT-IND":      "Rental Income - Industrial",
    "RENT-STR":      "Rental Income - Short-Term",
    "SVC-CHARGE":    "Service Charge Income",
    "PARKING-FEE":   "Parking Income",
    "LATE-FEE":      "Late Payment Income",
    "BOUNCE-FEE":    "Bounce Penalty Income",
    "SEC-DEPOSIT":   "Security Deposits Payable",
    "UTIL-ELEC":     "Utility Recovery Income",
    "UTIL-WATER":    "Utility Recovery Income",
    "MAINT-SERVICE": "Property Maintenance Expense",
}

UAE_INCOME_ACCOUNTS = [
    ("Rental Income - Residential", "Income Account"),
    ("Rental Income - Commercial",  "Income Account"),
    ("Rental Income - Industrial",  "Income Account"),
    ("Rental Income - Short-Term",  "Income Account"),
    ("Service Charge Income",       "Income Account"),
    ("Parking Income",              "Income Account"),
    ("Utility Recovery Income",     "Income Account"),
    ("Late Payment Income",         "Income Account"),
    ("Bounce Penalty Income",       "Income Account"),
    ("Other Property Income",       "Income Account"),
]

UAE_LIABILITY_ACCOUNTS = [
    ("Security Deposits Payable", "Current Liabilities"),
    ("VAT Payable - FTA",         "Current Liabilities"),
    ("Advance Rent Received",     "Current Liabilities"),
]

UAE_EXPENSE_ACCOUNTS = [
    ("Property Maintenance Expense",  "Expense Account"),
    ("Management Fee Expense",        "Expense Account"),
    ("Municipality Fee Expense",      "Expense Account"),
    ("Insurance Expense - Property",  "Expense Account"),
    ("DEWA Utility Expense",          "Expense Account"),
    ("SEWA Utility Expense",          "Expense Account"),
    ("Security Services Expense",     "Expense Account"),
]

KSA_ACCOUNTS = [
    ("VAT Payable - GAZT", "Current Liabilities"),
]

OMAN_ACCOUNTS = [
    ("VAT Payable - OTA", "Current Liabilities"),
]

TAX_TEMPLATES = [
    {
        "title": "UAE VAT 5% - Commercial",
        "taxes": [{"account_head": "VAT Payable - FTA", "rate": 5}]
    },
    {
        "title": "UAE VAT Exempt - Residential",
        "taxes": []
    },
    {
        "title": "KSA VAT 15%",
        "taxes": [{"account_head": "VAT Payable - GAZT", "rate": 15}]
    },
    {
        "title": "Oman VAT 5%",
        "taxes": [{"account_head": "VAT Payable - OTA", "rate": 5}]
    },
]


def _create_account(account_name, account_type, company, parent_account=None):
    abbr = frappe.db.get_value("Company", company, "abbr")
    full_name = f"{account_name} - {abbr}"
    if frappe.db.exists("Account", full_name):
        return full_name

    if not parent_account:
        if "Income" in account_type:
            parent_account = frappe.db.get_value(
                "Account", {"root_type": "Income", "is_group": 1, "company": company}, "name"
            )
        elif "Liabilities" in account_type:
            parent_account = frappe.db.get_value(
                "Account", {"root_type": "Liability", "is_group": 1, "company": company}, "name"
            )
        elif "Expense" in account_type:
            parent_account = frappe.db.get_value(
                "Account", {"root_type": "Expense", "is_group": 1, "company": company}, "name"
            )

    acc = frappe.new_doc("Account")
    acc.account_name = account_name
    acc.parent_account = parent_account
    acc.company = company
    acc.account_type = account_type
    acc.is_group = 0
    acc.insert(ignore_permissions=True)
    return full_name


def _apply_item_defaults(company):
    """Link each billing item to its designated GL account for this company."""
    abbr = frappe.db.get_value("Company", company, "abbr")
    for item_code, account_name in ITEM_ACCOUNT_MAP.items():
        if not frappe.db.exists("Item", item_code):
            continue
        account_full = f"{account_name} - {abbr}"
        if not frappe.db.exists("Account", account_full):
            continue
        already_set = frappe.db.exists(
            "Item Default", {"parent": item_code, "company": company}
        )
        if already_set:
            continue
        item = frappe.get_doc("Item", item_code)
        item.append("item_defaults", {"company": company, "income_account": account_full})
        item.save(ignore_permissions=True)


def _create_tax_templates(company):
    """Create Sales Taxes and Charges Templates for GCC VAT rates."""
    abbr = frappe.db.get_value("Company", company, "abbr")
    for tmpl in TAX_TEMPLATES:
        if frappe.db.exists("Sales Taxes and Charges Template",
                            {"title": tmpl["title"], "company": company}):
            continue
        doc = frappe.new_doc("Sales Taxes and Charges Template")
        doc.title = tmpl["title"]
        doc.company = company
        for tax in tmpl["taxes"]:
            account_full = f"{tax['account_head']} - {abbr}"
            if not frappe.db.exists("Account", account_full):
                continue
            doc.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": account_full,
                "description": tmpl["title"],
                "rate": tax["rate"],
            })
        doc.insert(ignore_permissions=True)


def setup_for_company(company):
    for name, atype in UAE_INCOME_ACCOUNTS:
        _create_account(name, atype, company)
    for name, atype in UAE_LIABILITY_ACCOUNTS:
        _create_account(name, atype, company)
    for name, atype in UAE_EXPENSE_ACCOUNTS:
        _create_account(name, atype, company)
    _create_tax_templates(company)
    _apply_item_defaults(company)
    frappe.db.commit()


def on_company_insert(doc, method):
    """Auto-run account + item setup whenever a new Company is created."""
    setup_for_company(doc.name)
