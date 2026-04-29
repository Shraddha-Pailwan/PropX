import frappe
from frappe.utils import today, add_days


@frappe.whitelist()
def get_lease_stats():
    """Dashboard KPIs: active count, expiring in 30/60 days, critical."""
    t = today()
    return {
        "total_active": frappe.db.count("Lease", {"status": "Active"}),
        "expiring_30": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 30)]]
        }),
        "expiring_60": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 60)]]
        }),
        "draft_count": frappe.db.count("Lease", {"status": "Draft"}),
        "critical": frappe.db.count("Lease", {
            "status": ["in", ["Active", "Expiring"]],
            "end_date": ["between", [t, add_days(t, 14)]],
            "renewal_status": ["in", ["Not Initiated", None, ""]]
        })
    }


@frappe.whitelist()
def get_leases(status=None, lease_category=None,
               search=None, page=1, page_size=25):
    """Paginated lease list with optional filters."""
    filters = {}
    if status:
        filters["status"] = status
    if lease_category:
        filters["lease_category"] = lease_category
    if search:
        filters["tenant_name"] = ["like", f"%{search}%"]

    leases = frappe.get_all(
        "Lease",
        filters=filters,
        fields=["name", "tenant", "tenant_name", "unit", "property",
                "lease_category", "start_date", "end_date",
                "annual_rent", "currency", "status",
                "renewal_status", "ejari_status", "is_vat_applicable",
                "number_of_cheques"],
        order_by="end_date asc",
        start=(int(page) - 1) * int(page_size),
        page_length=int(page_size)
    )
    return {
        "leases": leases,
        "total": frappe.db.count("Lease", filters),
        "page": int(page)
    }


@frappe.whitelist()
def get_expiring_leases(days=60):
    """Return leases expiring within N days with days_remaining."""
    cutoff = add_days(today(), int(days))
    return frappe.db.sql("""
        SELECT l.name, l.tenant, l.tenant_name, l.unit, l.property,
               l.end_date, l.annual_rent, l.renewal_status,
               DATEDIFF(l.end_date, CURDATE()) AS days_remaining
        FROM `tabLease` l
        WHERE l.status IN ('Active', 'Expiring')
          AND l.end_date BETWEEN %(today)s AND %(cutoff)s
        ORDER BY l.end_date ASC
    """, {"today": today(), "cutoff": cutoff}, as_dict=True)


@frappe.whitelist()
def get_rera_rent_cap(current_rent, current_market_rent):
    """
    UAE RERA Rental Index cap calculator.
    Returns max allowed new rent per Dubai Law No. 43 of 2013.
    """
    cur = float(current_rent)
    market = float(current_market_rent)
    gap_pct = (market - cur) / cur * 100 if cur else 0

    if gap_pct < 11:
        max_increase_pct = 0
    elif gap_pct < 21:
        max_increase_pct = 5
    elif gap_pct < 31:
        max_increase_pct = 10
    elif gap_pct < 41:
        max_increase_pct = 15
    else:
        max_increase_pct = 20

    return {
        "current_rent": cur,
        "market_rent": market,
        "gap_pct": round(gap_pct, 1),
        "max_increase_pct": max_increase_pct,
        "max_allowed_new_rent": round(cur * (1 + max_increase_pct / 100), 2)
    }
