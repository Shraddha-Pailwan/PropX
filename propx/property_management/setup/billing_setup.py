import frappe


BILLING_ITEMS = [
    ("RENT-RES",    "Residential Rent",       "Rental Income - Residential", False),
    ("RENT-COM",    "Commercial Rent",         "Rental Income - Commercial",  True),
    ("RENT-IND",    "Industrial Rent",         "Rental Income - Industrial",  True),
    ("RENT-STR",    "Short-Term Rent",         "Rental Income - Short-Term",  True),
    ("SVC-CHARGE",  "Service Charge",          "Service Charge Income",       True),
    ("PARKING-FEE", "Parking Fee",             "Parking Income",              True),
    ("LATE-FEE",    "Late Payment Penalty",    "Other Income",                False),
    ("BOUNCE-FEE",  "Cheque Bounce Penalty",   "Other Income",                False),
    ("SEC-DEPOSIT", "Security Deposit",        "Security Deposits Payable",   False),
    ("UTIL-ELEC",   "Electricity Charge",      "Utility Recovery Income",     True),
    ("UTIL-WATER",  "Water Charge",            "Utility Recovery Income",     True),
    ("MAINT-SERVICE", "Maintenance Service",   "Property Maintenance Expense", False),
]


def _get_item_group():
    """Return 'Services' if it exists, else fall back to 'All Item Groups'."""
    if frappe.db.exists("Item Group", "Services"):
        return "Services"
    root = frappe.db.get_value("Item Group", {"is_group": 1, "parent_item_group": ""}, "name")
    return root or "All Item Groups"


def create_items():
    item_group = _get_item_group()
    for item_code, item_name, _, _ in BILLING_ITEMS:
        if frappe.db.exists("Item", item_code):
            continue
        item = frappe.new_doc("Item")
        item.item_code = item_code
        item.item_name = item_name
        item.item_group = item_group
        item.is_stock_item = 0
        item.is_sales_item = 1
        item.is_purchase_item = 1
        item.insert(ignore_permissions=True)
    frappe.db.commit()
