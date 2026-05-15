"""
create_sample_data.py
=====================
Creates realistic sample data across all PropX modules for testing.

Run via:
    bench --site propx.quantcloud.in execute \
        propx.property_management.utils.create_sample_data.run

Order of creation (respects FK dependencies):
  M05 Tenants (Customer) → M01 Property → M01 Units → M02 Lease →
  M03 PDC → M06 Maintenance → M07 Utility → M08 Security →
  M14 Inspection → M15 Parking → M12 Listing
"""

import frappe
from frappe.utils import today, add_days, add_months, now_datetime, flt

COMPANY = "Quantbit"
LOG = []


def log(msg):
    LOG.append(msg)
    print(msg)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _exists_or_create(doctype, filters, data):
    """Return existing doc name or insert a new one."""
    name = frappe.db.exists(doctype, filters)
    if name:
        log(f"  [skip] {doctype} already exists: {name}")
        return name
    doc = frappe.get_doc({"doctype": doctype, **data})
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"  [ok]   {doctype} created: {doc.name}")
    return doc.name


# ─────────────────────────────────────────────────────────────────────────────
# M05 — TENANTS (Customer)
# ─────────────────────────────────────────────────────────────────────────────

def create_tenants():
    log("\n── M05: Tenants ──")

    # Individual tenant
    t1 = _exists_or_create(
        "Customer",
        {"customer_name": "Ahmed Al Mansouri"},
        {
            "customer_name":    "Ahmed Al Mansouri",
            "customer_type":    "Individual",
            "customer_group":   frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial",
            "territory":        frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories",
            "is_tenant":        1,
            "tenant_type":      "Individual",
            "emirates_id":      "784-1990-1234567-1",
            "whatsapp_number":  "+971501234567",
            "preferred_language": "Arabic",
        },
    )

    # Corporate tenant
    t2 = _exists_or_create(
        "Customer",
        {"customer_name": "TechVentures FZCO"},
        {
            "customer_name":     "TechVentures FZCO",
            "customer_type":     "Company",
            "customer_group":    frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial",
            "territory":         frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories",
            "is_tenant":         1,
            "tenant_type":       "Corporate",
            "trade_licence_no":  "DMCC-2021-12345",
            "whatsapp_number":   "+971504567890",
            "preferred_language": "English",
        },
    )

    return t1, t2


# ─────────────────────────────────────────────────────────────────────────────
# M01 — PROPERTY + UNITS
# ─────────────────────────────────────────────────────────────────────────────

def _get_or_create_owner_customer():
    """Get or create a Customer record for the property owner."""
    name = frappe.db.get_value("Customer", {"customer_name": "Marina Heights LLC"}, "name")
    if name:
        return name
    cg = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Commercial"
    terr = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "All Territories"
    doc = frappe.get_doc({
        "doctype": "Customer",
        "customer_name": "Marina Heights LLC",
        "customer_type": "Company",
        "customer_group": cg,
        "territory": terr,
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"  [ok]   Owner Customer: {doc.name}")
    return doc.name


def create_property():
    log("\n── M01: Property ──")

    owner = _get_or_create_owner_customer()
    cost_centre = frappe.db.get_value(
        "Cost Center", {"company": COMPANY, "is_group": 0}, "name"
    ) or "Main - Q"

    prop = _exists_or_create(
        "Property",
        {"property_name": "Marina Heights"},
        {
            "property_name":     "Marina Heights",
            "property_category": "Mixed-Use",
            "address_line_1":    "Plot 12, Dubai Marina",
            "city":              "Dubai",
            "country":           "United Arab Emirates",
            "company":           COMPANY,
            "property_owner":    owner,
            "cost_centre":       cost_centre,
            "total_floors":      20,
            "year_built":        2018,
        },
    )

    # Floors
    for floor_no, floor_name in [(1, "Ground Floor"), (5, "Floor 5"), (10, "Floor 10")]:
        _exists_or_create(
            "Property Floor",
            {"property": prop, "floor_number": floor_no},
            {
                "property":     prop,
                "floor_number": floor_no,
                "floor_name":   floor_name,
            },
        )

    return prop


def create_units(prop, tenant1, tenant2):
    log("\n── M01: Property Units ──")

    # Residential unit — Occupied
    u1 = _exists_or_create(
        "Property Unit",
        {"property": prop, "unit_number": "101"},
        {
            "property":          prop,
            "unit_number":       "101",
            "unit_name":         "Apartment 101",
            "usage_type":        "Residential",
            "floor_number":      1,
            "bedrooms":          2,
            "bathrooms":         2,
            "area_sqft":         1200,
            "status":            "Occupied",
            "current_tenant":    tenant1,
            "asking_rent_annual": 85000,
            "last_agreed_rent":  80000,
        },
    )

    # Commercial unit — Occupied
    u2 = _exists_or_create(
        "Property Unit",
        {"property": prop, "unit_number": "G01"},
        {
            "property":          prop,
            "unit_number":       "G01",
            "unit_name":         "Ground Floor Office G01",
            "usage_type":        "Commercial",
            "floor_number":      1,
            "area_sqft":         2500,
            "status":            "Occupied",
            "current_tenant":    tenant2,
            "asking_rent_annual": 220000,
            "last_agreed_rent":  200000,
        },
    )

    # Vacant residential unit
    u3 = _exists_or_create(
        "Property Unit",
        {"property": prop, "unit_number": "502"},
        {
            "property":          prop,
            "unit_number":       "502",
            "unit_name":         "Apartment 502",
            "usage_type":        "Residential",
            "floor_number":      5,
            "bedrooms":          1,
            "bathrooms":         1,
            "area_sqft":         750,
            "status":            "Vacant",
            "asking_rent_annual": 60000,
            "market_rent_benchmark": 62000,
        },
    )

    return u1, u2, u3


# ─────────────────────────────────────────────────────────────────────────────
# M02 — LEASES
# ─────────────────────────────────────────────────────────────────────────────

def create_leases(prop, u1, u2, tenant1, tenant2):
    log("\n── M02: Leases ──")

    start1 = add_months(today(), -6)   # started 6 months ago
    end1   = add_months(today(), 6)    # ending in 6 months

    lease1 = _exists_or_create(
        "Lease",
        {"unit": u1, "tenant": tenant1, "status": ["!=", "Cancelled"]},
        {
            "unit":                 u1,
            "property":             prop,
            "tenant":               tenant1,
            "tenant_name":          "Ahmed Al Mansouri",
            "company":              COMPANY,
            "lease_category":       "Residential",
            "start_date":           start1,
            "end_date":             end1,
            "annual_rent":          80000,
            "monthly_rent":         flt(80000 / 12, 2),
            "currency":             "AED",
            "security_deposit":     13333,
            "number_of_cheques":    4,
            "notice_period_days":   90,
            "is_vat_applicable":    0,
            "status":               "Active",
            "renewal_status":       "Not Initiated",
        },
    )

    start2 = add_months(today(), -3)
    end2   = add_months(today(), 9)

    lease2 = _exists_or_create(
        "Lease",
        {"unit": u2, "tenant": tenant2, "status": ["!=", "Cancelled"]},
        {
            "unit":                 u2,
            "property":             prop,
            "tenant":               tenant2,
            "tenant_name":          "TechVentures FZCO",
            "company":              COMPANY,
            "lease_category":       "Commercial",
            "start_date":           start2,
            "end_date":             end2,
            "annual_rent":          200000,
            "monthly_rent":         flt(200000 / 12, 2),
            "currency":             "AED",
            "security_deposit":     33333,
            "number_of_cheques":    6,
            "notice_period_days":   90,
            "is_vat_applicable":    1,
            "vat_rate":             5,
            "service_charge_monthly": 2500,
            "status":               "Active",
            "renewal_status":       "Not Initiated",
        },
    )

    return lease1, lease2


# ─────────────────────────────────────────────────────────────────────────────
# M03 — PDC REGISTER
# ─────────────────────────────────────────────────────────────────────────────

def create_pdcs(lease1, lease2, tenant1, tenant2, prop, u1, u2):
    log("\n── M03: PDC Register ──")

    pdcs = [
        {
            "cheque_number":  "CHQ-0011001",
            "bank_name":      "Emirates NBD",
            "account_number": "1011234567",
            "amount":         20000,
            "cheque_date":    add_days(today(), 15),
            "received_date":  add_days(today(), -60),
            "tenant":         tenant1,
            "lease":          lease1,
            "property":       prop,
            "unit":           u1,
            "status":         "Received",
            "currency":       "AED",
        },
        {
            "cheque_number":  "CHQ-0011002",
            "bank_name":      "Emirates NBD",
            "account_number": "1011234567",
            "amount":         20000,
            "cheque_date":    add_days(today(), 105),
            "received_date":  add_days(today(), -60),
            "tenant":         tenant1,
            "lease":          lease1,
            "property":       prop,
            "unit":           u1,
            "status":         "Received",
            "currency":       "AED",
        },
        {
            "cheque_number":  "CHQ-0022001",
            "bank_name":      "Abu Dhabi Commercial Bank",
            "account_number": "2021234567",
            "amount":         33333,
            "cheque_date":    add_days(today(), 30),
            "received_date":  add_days(today(), -45),
            "tenant":         tenant2,
            "lease":          lease2,
            "property":       prop,
            "unit":           u2,
            "status":         "Deposited",
            "deposited_date": add_days(today(), -10),
            "currency":       "AED",
        },
        {
            "cheque_number":  "CHQ-0033001",
            "bank_name":      "Mashreq Bank",
            "account_number": "3031234567",
            "amount":         15000,
            "cheque_date":    add_days(today(), -30),
            "received_date":  add_days(today(), -90),
            "tenant":         tenant1,
            "lease":          lease1,
            "property":       prop,
            "unit":           u1,
            "status":         "Cleared",
            "deposited_date": add_days(today(), -35),
            "cleared_date":   add_days(today(), -30),
            "currency":       "AED",
        },
    ]

    created = []
    for pdc in pdcs:
        name = frappe.db.exists("PDC Register", {"cheque_number": pdc["cheque_number"]})
        if name:
            log(f"  [skip] PDC Register already exists: {name}")
            created.append(name)
            continue
        doc = frappe.get_doc({"doctype": "PDC Register", **pdc})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   PDC Register created: {doc.name} ({pdc['cheque_number']})")
        created.append(doc.name)

    return created


# ─────────────────────────────────────────────────────────────────────────────
# M06 — MAINTENANCE JOB CARDS
# ─────────────────────────────────────────────────────────────────────────────

def create_maintenance(prop, u1, u2, tenant1):
    log("\n── M06: Maintenance Job Cards ──")

    jobs = [
        {
            "subject":            "AC not cooling — Apartment 101",
            "property":           prop,
            "unit":               u1,
            "category":           "HVAC",
            "priority":           "High",
            "ticket_status":      "In Progress",
            "reported_by_tenant": 1,
            "tenant_reference":   tenant1,
            "description":        "Tenant reports AC in bedroom is not cooling. "
                                  "Temperature not dropping below 28°C.",
            "estimated_cost":     800,
        },
        {
            "subject":            "Water leak under kitchen sink — G01",
            "property":           prop,
            "unit":               u2,
            "category":           "Plumbing",
            "priority":           "Emergency",
            "ticket_status":      "Assigned",
            "reported_by_tenant": 1,
            "description":        "Slow drip under the kitchen sink. Water pooling.",
            "estimated_cost":     350,
        },
        {
            "subject":            "Lobby light replacement — Ground Floor",
            "property":           prop,
            "category":           "Electrical",
            "priority":           "Low",
            "ticket_status":      "Completed",
            "reported_by_tenant": 0,
            "description":        "3 lobby ceiling lights have failed. Replace with LED.",
            "estimated_cost":     1200,
            "actual_cost":        1050,
        },
    ]

    created = []
    for job in jobs:
        name = frappe.db.exists("Maintenance Job Card", {"subject": job["subject"], "property": prop})
        if name:
            log(f"  [skip] Maintenance Job Card exists: {name}")
            created.append(name)
            continue
        doc = frappe.get_doc({"doctype": "Maintenance Job Card", **job})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Maintenance Job Card: {doc.name}")
        created.append(doc.name)

    return created


# ─────────────────────────────────────────────────────────────────────────────
# M07 — UTILITY METERS + READINGS
# ─────────────────────────────────────────────────────────────────────────────

def create_utility(prop, u1, u2):
    log("\n── M07: Utility Meters & Readings ──")

    meters = [
        {
            "meter_number":   "DEWA-101-ELEC",
            "property":       prop,
            "unit":           u1,
            "utility_type":   "Electricity",
            "authority":      "DEWA",
            "authority_account": "ACC-101-E",
            "tariff_per_unit": 0.38,
            "billing_mode":   "Charge to Tenant",
            "status":         "Active",
        },
        {
            "meter_number":   "DEWA-101-WATER",
            "property":       prop,
            "unit":           u1,
            "utility_type":   "Water",
            "authority":      "DEWA",
            "authority_account": "ACC-101-W",
            "tariff_per_unit": 0.012,
            "billing_mode":   "Charge to Tenant",
            "status":         "Active",
        },
        {
            "meter_number":   "DEWA-G01-ELEC",
            "property":       prop,
            "unit":           u2,
            "utility_type":   "Electricity",
            "authority":      "DEWA",
            "authority_account": "ACC-G01-E",
            "tariff_per_unit": 0.44,
            "billing_mode":   "Charge to Tenant",
            "status":         "Active",
        },
    ]

    meter_names = []
    for m in meters:
        name = frappe.db.exists("Utility Meter", {"meter_number": m["meter_number"]})
        if name:
            log(f"  [skip] Utility Meter exists: {name}")
            meter_names.append(name)
            continue
        doc = frappe.get_doc({"doctype": "Utility Meter", **m})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Utility Meter: {doc.name}")
        meter_names.append(doc.name)

    # Meter Readings (saved, not submitted — to avoid auto-invoicing on test data)
    readings = [
        {"meter": meter_names[0], "reading_date": add_days(today(), -30),
         "previous_reading": 1000, "current_reading": 1850, "reading_type": "Manual"},
        {"meter": meter_names[0], "reading_date": today(),
         "current_reading": 2720, "reading_type": "Manual"},
        {"meter": meter_names[1], "reading_date": today(),
         "current_reading": 4500, "reading_type": "Manual"},
    ]

    for r in readings:
        exists = frappe.db.exists("Meter Reading", {
            "meter": r["meter"], "reading_date": r["reading_date"]
        })
        if exists:
            log(f"  [skip] Meter Reading exists: {exists}")
            continue
        doc = frappe.get_doc({"doctype": "Meter Reading", **r})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Meter Reading: {doc.name} (consumption={doc.consumption})")

    return meter_names


# ─────────────────────────────────────────────────────────────────────────────
# M08 — SECURITY: Guard Shift, Visitor Log, Security Incident, Key Register
# ─────────────────────────────────────────────────────────────────────────────

def create_security(prop, u1, tenant1):
    log("\n── M08: Security & Access ──")

    # Guard Shift
    shift_exists = frappe.db.exists("Guard Shift", {
        "property": prop, "shift_date": today(), "shift_type": "Morning"
    })
    if not shift_exists:
        shift = frappe.get_doc({
            "doctype":    "Guard Shift",
            "property":   prop,
            "shift_date": today(),
            "shift_type": "Morning",
            "shift_start": "06:00:00",
            "shift_end":   "14:00:00",
            "handover_notes": "All clear from night shift. Lobby camera 3 offline — reported to IT.",
            "guards": [
                {"employee": _get_or_create_employee("Mohammed Raza", "Security Guard"),
                 "post": "Main Gate", "status": "On Duty"},
                {"employee": _get_or_create_employee("Sanjay Kumar", "Security Guard"),
                 "post": "Lobby", "status": "On Duty"},
            ],
        })
        shift.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Guard Shift: {shift.name}")
    else:
        log(f"  [skip] Guard Shift exists: {shift_exists}")

    # Visitor Log
    vl_exists = frappe.db.exists("Visitor Log", {
        "property": prop, "visitor_name": "John Smith"
    })
    if not vl_exists:
        vl = frappe.get_doc({
            "doctype":       "Visitor Log",
            "property":      prop,
            "visitor_name":  "John Smith",
            "host_unit":     u1,
            "host_tenant":   tenant1,
            "id_type":       "Passport",
            "id_number":     "GB123456789",
            "visit_purpose": "Personal Guest",
            "vehicle_plate": "DXB-A-12345",
            "check_in":      now_datetime(),
            "status":        "On Premises",
            "pre_approved":  1,
        })
        vl.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Visitor Log: {vl.name}")
    else:
        log(f"  [skip] Visitor Log exists: {vl_exists}")

    # Security Incident
    inc_exists = frappe.db.exists("Security Incident", {"property": prop, "incident_type": "Noise Complaint"})
    if not inc_exists:
        inc = frappe.get_doc({
            "doctype":            "Security Incident",
            "property":           prop,
            "incident_type":      "Noise Complaint",
            "incident_datetime":  now_datetime(),
            "location_detail":    "Floor 5, Apartment 502",
            "description":        "Resident from unit 502 reported loud music from unit 501 "
                                  "after midnight. Guard dispatched, music stopped by 01:15.",
            "status":             "Resolved",
            "resolution":         "Verbal warning issued to unit 501 occupant. "
                                  "No further action required.",
        })
        inc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Security Incident: {inc.name}")
    else:
        log(f"  [skip] Security Incident exists: {inc_exists}")

    # Key Register
    key_exists = frappe.db.exists("Key Register", {"property": prop, "key_number": "MH-101-A"})
    if not key_exists:
        key = frappe.get_doc({
            "doctype":        "Key Register",
            "property":       prop,
            "unit":           u1,
            "key_type":       "Unit Key",
            "key_number":     "MH-101-A",
            "total_copies":   2,
            "status":         "Issued",
            "current_holder": tenant1,
            "issued_date":    add_days(today(), -180),
        })
        key.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Key Register: {key.name}")
    else:
        log(f"  [skip] Key Register exists: {key_exists}")

    master_key_exists = frappe.db.exists("Key Register", {"property": prop, "key_number": "MH-MASTER-01"})
    if not master_key_exists:
        key2 = frappe.get_doc({
            "doctype":        "Key Register",
            "property":       prop,
            "key_type":       "Master Key",
            "key_number":     "MH-MASTER-01",
            "total_copies":   1,
            "status":         "Available",
            "notes":          "Kept in property manager safe.",
        })
        key2.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Key Register (master): {key2.name}")
    else:
        log(f"  [skip] Master Key exists: {master_key_exists}")


def _get_or_create_designation(designation_name):
    """Ensure a Designation record exists."""
    if not frappe.db.exists("Designation", {"designation_name": designation_name}):
        des = frappe.get_doc({
            "doctype": "Designation",
            "designation_name": designation_name,
        })
        des.insert(ignore_permissions=True)
        frappe.db.commit()
    return designation_name


def _get_or_create_employee(employee_name, designation):
    """Get or create a minimal Employee record for guard shift."""
    name = frappe.db.get_value("Employee", {"employee_name": employee_name}, "name")
    if name:
        return name
    _get_or_create_designation(designation)
    emp = frappe.get_doc({
        "doctype":        "Employee",
        "employee_name":  employee_name,
        "first_name":     employee_name.split()[0],
        "gender":         "Male",
        "date_of_birth":  "1990-01-01",
        "date_of_joining": add_days(today(), -365),
        "company":        COMPANY,
        "designation":    designation,
        "status":         "Active",
    })
    emp.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"  [ok]   Employee: {emp.name}")
    return emp.name


# ─────────────────────────────────────────────────────────────────────────────
# M14 — PROPERTY INSPECTION
# ─────────────────────────────────────────────────────────────────────────────

def create_inspection(prop, u1, u2, lease1, tenant1):
    log("\n── M14: Property Inspection ──")

    insp_exists = frappe.db.exists("Property Inspection", {
        "unit": u1, "inspection_type": "Move-In"
    })
    if insp_exists:
        log(f"  [skip] Inspection exists: {insp_exists}")
        return insp_exists

    insp = frappe.get_doc({
        "doctype":          "Property Inspection",
        "inspection_type":  "Move-In",
        "lease":            lease1,
        "unit":             u1,
        "property":         prop,
        "tenant":           tenant1,
        "inspection_date":  add_days(today(), -180),
        "inspector":        frappe.session.user,
        "status":           "Completed",
        "tenant_agreed":    1,
        "notes":            "Unit in good condition. Minor scuff on bedroom wall noted. "
                            "All appliances operational.",
        "inspection_items": [
            {"area": "Living Room",   "item_description": "Walls",    "condition_move_in": "Good"},
            {"area": "Living Room",   "item_description": "Floor",    "condition_move_in": "Excellent"},
            {"area": "Living Room",   "item_description": "AC Unit",  "condition_move_in": "Good"},
            {"area": "Bedroom 1",     "item_description": "Walls",    "condition_move_in": "Fair",
             "notes": "Minor scuff mark on south wall"},
            {"area": "Bedroom 1",     "item_description": "Floor",    "condition_move_in": "Good"},
            {"area": "Kitchen",       "item_description": "Cabinets", "condition_move_in": "Good"},
            {"area": "Kitchen",       "item_description": "Sink",     "condition_move_in": "Excellent"},
            {"area": "Bathroom",      "item_description": "Tiles",    "condition_move_in": "Good"},
            {"area": "Bathroom",      "item_description": "Fixtures", "condition_move_in": "Excellent"},
        ],
    })
    insp.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"  [ok]   Inspection: {insp.name} (score={insp.overall_score})")
    return insp.name


# ─────────────────────────────────────────────────────────────────────────────
# M15 — PARKING BAYS
# ─────────────────────────────────────────────────────────────────────────────

def create_parking(prop, u1, tenant1):
    log("\n── M15: Parking ──")

    # Allocated bay
    _exists_or_create(
        "Parking Bay",
        {"property": prop, "bay_number": "B1-001"},
        {
            "property":           prop,
            "bay_number":         "B1-001",
            "bay_label":          "Basement 1, Bay 001",
            "level":              "Basement 1",
            "bay_type":           "Covered",
            "allocated_to_unit":  u1,
            "allocated_to_tenant": tenant1,
            "monthly_charge":     0,
            "status":             "Allocated to Unit",
        },
    )

    # EV charging bay — available
    _exists_or_create(
        "Parking Bay",
        {"property": prop, "bay_number": "B1-020"},
        {
            "property":      prop,
            "bay_number":    "B1-020",
            "bay_label":     "Basement 1, EV Bay 020",
            "level":         "Basement 1",
            "bay_type":      "EV Charging",
            "has_ev_charger": 1,
            "ev_charger_type": "Type 2",
            "monthly_charge": 500,
            "status":         "Available",
        },
    )

    # Visitor bay
    _exists_or_create(
        "Parking Bay",
        {"property": prop, "bay_number": "G-VIS-01"},
        {
            "property":      prop,
            "bay_number":    "G-VIS-01",
            "bay_label":     "Ground Level, Visitor Bay 01",
            "level":         "Ground",
            "bay_type":      "Uncovered",
            "monthly_charge": 0,
            "status":         "Available",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# M12 — VACANCY LISTING (for the vacant unit)
# ─────────────────────────────────────────────────────────────────────────────

def create_listing(prop, u3):
    log("\n── M12: Vacancy Listing ──")

    listing_exists = frappe.db.exists("Vacancy Listing", {"unit": u3})
    if listing_exists:
        log(f"  [skip] Vacancy Listing exists: {listing_exists}")
        return listing_exists

    listing = frappe.get_doc({
        "doctype":         "Vacancy Listing",
        "unit":            u3,
        "property":        prop,
        "listing_status":  "Active",
        "asking_rent":     60000,
        "available_from":  today(),
        "description":     "<p>Beautiful 1BR apartment on Floor 5 of Marina Heights. "
                           "Stunning marina views. Fully fitted kitchen. "
                           "Gym and pool access included.</p>",
        "features": [
            {"feature": "Marina View"},
            {"feature": "Gym Access"},
            {"feature": "Swimming Pool"},
            {"feature": "Covered Parking"},
            {"feature": "24hr Security"},
        ],
        "inquiries": [
            {
                "inquiry_date":    today(),
                "prospect_name":   "Sarah Johnson",
                "phone":           "+971509876543",
                "email":           "sarah.j@example.com",
                "source":          "PropertyFinder",
                "status":          "Viewing Scheduled",
                "next_action_date": add_days(today(), 2),
                "notes":           "Interested in 1-year lease. Flexible on start date.",
            },
        ],
    })
    listing.insert(ignore_permissions=True)
    frappe.db.commit()
    log(f"  [ok]   Vacancy Listing: {listing.name}")
    return listing.name


# ─────────────────────────────────────────────────────────────────────────────
# M13 — PROPX CLIENT
# ─────────────────────────────────────────────────────────────────────────────

def create_client():
    log("\n── M13: PropX Client ──")
    _exists_or_create(
        "PropX Client",
        {"company": COMPANY},
        {
            "client_name":        "Quantbit Demo Client",
            "company":            COMPANY,
            "plan":               "Growth",
            "max_units":          500,
            "api_rate_limit":     2000,
            "subscription_start": add_months(today(), -3),
            "subscription_end":   add_months(today(), 9),
            "is_active":          1,
            "primary_color":      "#c9a84c",
            "whatsapp_configured": 0,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# PPM SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

def create_ppm(prop):
    log("\n── M06: PPM Schedule ──")
    ppms = [
        {
            "title":             "Monthly Fire Alarm Test",
            "property":          prop,
            "category":          "Safety",
            "frequency":         "Monthly",
            "next_due_date":     add_days(today(), 5),
            "description":       "Monthly fire alarm and emergency lighting test. "
                                 "Log all zones tested.",
            "estimated_duration_hours": 2,
            "estimated_cost":    0,
            "is_active":         1,
        },
        {
            "title":             "Quarterly AC Filter Replacement",
            "property":          prop,
            "category":          "HVAC",
            "frequency":         "Quarterly",
            "next_due_date":     add_days(today(), 22),
            "description":       "Replace AC filters in all common areas and check refrigerant levels.",
            "estimated_duration_hours": 4,
            "estimated_cost":    1800,
            "is_active":         1,
        },
    ]
    for ppm in ppms:
        name = frappe.db.exists("PPM Schedule", {"title": ppm["title"], "property": prop})
        if name:
            log(f"  [skip] PPM Schedule exists: {name}")
            continue
        doc = frappe.get_doc({"doctype": "PPM Schedule", **ppm})
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   PPM Schedule: {doc.name}")


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR COI
# ─────────────────────────────────────────────────────────────────────────────

def create_vendor_coi(prop):
    log("\n── M06: Vendor COI ──")

    # Get or create a supplier
    supplier_name = frappe.db.get_value("Supplier", {"supplier_name": "Al Futtaim Facilities"}, "name")
    if not supplier_name:
        s = frappe.get_doc({
            "doctype":        "Supplier",
            "supplier_name":  "Al Futtaim Facilities",
            "supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}, "name") or "All Supplier Groups",
            "supplier_type":  "Company",
        })
        s.insert(ignore_permissions=True)
        frappe.db.commit()
        supplier_name = s.name
        log(f"  [ok]   Supplier: {supplier_name}")
    else:
        log(f"  [skip] Supplier exists: {supplier_name}")

    coi_exists = frappe.db.exists("Vendor COI", {"vendor": supplier_name})
    if not coi_exists:
        coi = frappe.get_doc({
            "doctype":           "Vendor COI",
            "vendor":            supplier_name,
            "insurance_company": "AXA Gulf",
            "policy_number":     "AXA-2024-PLI-99123",
            "coverage_type":     "Public Liability",
            "coverage_amount":   5000000,
            "valid_from":        add_months(today(), -6),
            "valid_to":          add_months(today(), 6),
            "status":            "Valid",
            "property_scope": [{"property": prop}],
        })
        coi.insert(ignore_permissions=True)
        frappe.db.commit()
        log(f"  [ok]   Vendor COI: {coi.name}")
    else:
        log(f"  [skip] Vendor COI exists: {coi_exists}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def run():
    log("=" * 60)
    log("PropX Sample Data Generator")
    log("=" * 60)

    try:
        # M05 — Tenants
        tenant1, tenant2 = create_tenants()

        # M01 — Property + Units
        prop = create_property()
        u1, u2, u3 = create_units(prop, tenant1, tenant2)

        # M02 — Leases
        lease1, lease2 = create_leases(prop, u1, u2, tenant1, tenant2)

        # M03 — PDC Register
        create_pdcs(lease1, lease2, tenant1, tenant2, prop, u1, u2)

        # M06 — Maintenance + PPM + Vendor COI
        create_maintenance(prop, u1, u2, tenant1)
        create_ppm(prop)
        create_vendor_coi(prop)

        # M07 — Utility Meters + Readings
        create_utility(prop, u1, u2)

        # M08 — Security
        create_security(prop, u1, tenant1)

        # M14 — Property Inspection
        create_inspection(prop, u1, u2, lease1, tenant1)

        # M15 — Parking
        create_parking(prop, u1, tenant1)

        # M12 — Vacancy Listing
        create_listing(prop, u3)

        # M13 — PropX Client
        create_client()

        log("\n" + "=" * 60)
        log("✅  Sample data creation COMPLETE")
        log("=" * 60)
        log("\nSummary of test data:")
        log(f"  Property   : Marina Heights ({prop})")
        log(f"  Units      : {u1}, {u2} (occupied) | {u3} (vacant)")
        log(f"  Tenants    : Ahmed Al Mansouri ({tenant1}), TechVentures FZCO ({tenant2})")
        log(f"  Leases     : {lease1} (residential), {lease2} (commercial)")
        log("  PDCs       : 4 entries (Received × 2, Deposited × 1, Cleared × 1)")
        log("  Maintenance: 3 job cards (In Progress, Assigned, Completed)")
        log("  PPM        : 2 schedules (Fire Alarm, AC Filter)")
        log("  Utility    : 3 meters, 3 readings")
        log("  Security   : Guard shift, Visitor log, Incident, Key register × 2")
        log("  Inspection : Move-in inspection for Apartment 101")
        log("  Parking    : 3 bays (allocated, EV, visitor)")
        log("  Listing    : 1 active vacancy with 1 inquiry")
        log("  PropX Client: Quantbit Demo (Growth plan)")

    except Exception as e:
        frappe.db.rollback()
        log(f"\n❌  ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
