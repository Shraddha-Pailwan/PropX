import frappe
from frappe.utils import today, date_diff, add_days, now_datetime


def update_vacancy_days():
    """Daily: refresh days_vacant on all vacant units."""
    units = frappe.db.sql("""
        SELECT name, vacancy_since
        FROM `tabProperty Unit`
        WHERE status = 'Vacant'
          AND vacancy_since IS NOT NULL
    """, as_dict=True)
    for u in units:
        days = date_diff(today(), u.vacancy_since)
        frappe.db.set_value("Property Unit", u.name, "days_vacant", days)
    frappe.db.commit()


def send_lease_expiry_alerts():
    """Daily: alert on leases expiring in 60, 30, 7 days."""
    if not frappe.db.exists("DocType", "Lease"):
        return
    for days, severity in [(60, "info"), (30, "warning"), (7, "critical")]:
        cutoff = add_days(today(), days)
        leases = frappe.get_all(
            "Lease",
            filters={
                "status": ["in", ["Active", "Expiring"]],
                "end_date": cutoff,
            },
            fields=["name", "tenant_name", "unit", "end_date", "renewal_status"]
        )
        # Filter in Python to handle NULL/empty renewal_status correctly
        leases = [l for l in leases if not l.renewal_status or l.renewal_status == "Not Initiated"]
        for lease in leases:
            frappe.publish_realtime(
                event="lease_expiry_alert",
                message={**lease, "days": days, "severity": severity}
            )


def apply_due_rent_escalations():
    """Daily: check escalation_schedule rows due today and apply."""
    if not frappe.db.exists("DocType", "Lease"):
        return
    today_str = today()
    due = frappe.db.sql("""
        SELECT ers.name as row_name, ers.to_rent, l.name as lease_name
        FROM `tabRent Escalation Schedule` ers
        JOIN `tabLease` l ON l.name = ers.parent
        WHERE ers.escalation_date = %(today)s
          AND ers.applied = 0
          AND l.status = 'Active'
    """, {"today": today_str}, as_dict=True)

    for row in due:
        frappe.db.set_value("Lease", row.lease_name, "annual_rent", row.to_rent)
        frappe.db.set_value(
            "Rent Escalation Schedule", row.row_name,
            {"applied": 1, "applied_date": today_str}
        )
    if due:
        frappe.db.commit()


def send_pdc_due_reminders():
    """Daily: notify property managers of PDC cheques due within 7 days."""
    if not frappe.db.exists("DocType", "PDC Register"):
        return
    in7 = add_days(today(), 7)
    due_pdcs = frappe.get_all(
        "PDC Register",
        filters={
            "status": "Received",
            "cheque_date": ["between", [today(), in7]]
        },
        fields=["name", "cheque_number", "bank_name", "amount",
                "cheque_date", "tenant", "lease"]
    )
    if due_pdcs:
        frappe.publish_realtime("pdc_due_reminder", {"pdcs": due_pdcs})


def generate_ppm_work_orders():
    """Daily: create WOs for PPM schedules due today or overdue."""
    if not frappe.db.exists("DocType", "PPM Schedule") or not frappe.db.exists("DocType", "Maintenance Job Card"):
        return
    today_str = today()
    due = frappe.get_all("PPM Schedule", filters={
        "is_active": 1,
        "next_due_date": ["<=", today_str]
    }, fields=["name", "title", "property", "unit", "category",
               "assigned_to", "vendor", "estimated_cost"])

    for ppm in due:
        wo = frappe.new_doc("Maintenance Job Card")
        wo.subject = f"PPM: {ppm.title}"
        wo.property = ppm.property
        wo.unit = ppm.unit
        wo.category = ppm.category
        wo.priority = "Low"
        wo.is_ppm = 1
        wo.ppm_schedule = ppm.name
        wo.assigned_technician = ppm.assigned_to
        wo.vendor = ppm.vendor
        wo.estimated_cost = ppm.estimated_cost
        wo.insert(ignore_permissions=True)

        freq_map = {
            "Daily": 1, "Weekly": 7, "Monthly": 30,
            "Quarterly": 90, "Semi-Annual": 180, "Annual": 365
        }
        ppm_doc = frappe.get_doc("PPM Schedule", ppm.name)
        days = freq_map.get(ppm_doc.frequency, 30)
        ppm_doc.next_due_date = add_days(today_str, days)
        ppm_doc.last_done_date = today_str
        ppm_doc.save(ignore_permissions=True)
    frappe.db.commit()


def update_coi_statuses():
    """Daily: mark COIs as Expiring Soon or Expired."""
    if not frappe.db.exists("DocType", "Vendor COI"):
        return
    today_str = today()
    warn_date = add_days(today_str, 30)
    frappe.db.sql("""
        UPDATE `tabVendor COI` SET status='Expired'
        WHERE valid_to < %(today)s
    """, {"today": today_str})
    frappe.db.sql("""
        UPDATE `tabVendor COI` SET status='Expiring Soon'
        WHERE valid_to BETWEEN %(today)s AND %(warn)s
          AND status != 'Expired'
    """, {"today": today_str, "warn": warn_date})
    frappe.db.commit()


def check_sla_breaches():
    """Hourly: mark Maintenance Job Cards whose SLA deadline has passed."""
    if not frappe.db.exists("DocType", "Maintenance Job Card"):
        return
    now = now_datetime()
    # Find open tickets whose deadline has passed and aren't already Breached
    breached = frappe.db.sql(
        """
        SELECT name, sla_deadline
          FROM `tabMaintenance Job Card`
         WHERE sla_deadline IS NOT NULL
           AND sla_deadline < %(now)s
           AND sla_status != 'Breached'
           AND ticket_status NOT IN ('Completed', 'Closed', 'Cancelled')
        """,
        {"now": now},
        as_dict=True,
    )
    for row in breached:
        frappe.db.set_value(
            "Maintenance Job Card",
            row.name,
            {"sla_status": "Breached", "breached_at": row.sla_deadline},
        )
    if breached:
        frappe.db.commit()
