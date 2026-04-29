================================================================================
PROPX BUILD TODO — Master Checklist
Generated: 2026-03-30
================================================================================

LEGEND: [ ] = Pending  [x] = Done  [-] = In Progress

================================================================================
FOUNDATION (Prerequisites — build before any module)
================================================================================
[x] F1  Create property_management module folder structure
[x] F2  Create install.py with all 8 roles + default settings + custom fields
[x] F3  Wire after_install hook in hooks.py
[x] F4  Update modules.txt to register "Property Management" module
[x] F5  Create fixtures/ directory structure
[x] F6  Create setup/ scripts folder (accounts_setup, billing_setup, custom_fields)
[x] F7  Create utils/ folder with shared utilities
[x] F8  Create api/ folder for whitelisted endpoints
[x] F9  Create tasks.py for scheduled jobs
[x] F10 Configure scheduler_events in hooks.py (daily/monthly)
[x] F11 Configure doc_events in hooks.py (Customer, Property Unit)

================================================================================
M01 — Property & Asset Registry  (Phase 1 — Build FIRST)
================================================================================
DOCTYPES:
[x] M01-D1  Property DocType (PROP-{####} naming, all fields)
[x] M01-D2  Property Floor DocType
[x] M01-D3  Property Unit DocType ← ANCHOR DOCTYPE (build carefully)
[x] M01-D4  Unit Asset DocType
[x] M01-D5  Unit Photo child DocType (istable)
[x] M01-D6  Property Photo child DocType (istable)
[x] M01-D7  Property Document child DocType (istable)

CONTROLLERS:
[x] M01-C1  property_unit.py controller (validate, on_update, whitelist methods)
[x] M01-C2  create_cost_centres.py setup script

TASKS & API:
[x] M01-T1  tasks.py: update_vacancy_days() daily scheduler
[x] M01-A1  property_api.py: get_portfolio_summary()
[x] M01-A2  property_api.py: get_units_by_property()
[x] M01-A3  property_api.py: get_vacant_units()
[x] M01-A4  property_api.py: get_properties_list()

HOOKS:
[x] M01-H1  Add daily scheduler: update_vacancy_days to hooks.py

TESTS:
[ ] M01-X1  Create Property → Cost Centre auto-created
[ ] M01-X2  Set unit to Vacant → days_vacant increments daily
[ ] M01-X3  get_portfolio_summary returns correct occupancy %
[ ] M01-X4  Export as fixtures: bench export-fixtures --app propx

================================================================================
M14 — Inspection Management  (Phase 1 — Build after M01)
================================================================================
DOCTYPES:
[ ] M14-D1  Property Inspection DocType (INSP-{YYYY}-{#####})
[ ] M14-D2  Inspection Item child DocType
[ ] M14-D3  Inspection Deduction child DocType

CONTROLLERS:
[ ] M14-C1  property_inspection.py (validate, on_submit, deposit JE)
[ ] M14-C2  Load inspection templates for Residential + Commercial

API:
[ ] M14-A1  inspection_api.py: create_move_in_inspection()
[ ] M14-A2  inspection_api.py: get_inspection_summary()

MISC:
[ ] M14-M1  Create "Inspection Report" print format (PDF)

TESTS:
[ ] M14-X1  Activate lease → Move-In inspection auto-created
[ ] M14-X2  Complete Move-Out with deductions → JE posts correctly
[ ] M14-X3  refund_amount = deposit - tenant deductions

================================================================================
M15 — Parking Management  (Phase 2 — Build after M01)
================================================================================
DOCTYPES:
[ ] M15-D1  Parking Bay DocType (PARK-{####})
[ ] M15-D2  Parking Lease DocType (PLSE-{####})
[ ] M15-D3  Visitor Parking Log DocType

CONTROLLERS:
[ ] M15-C1  parking_bay.py (validate: auto-set status + tenant)
[ ] M15-C2  billing_utils.py addition: generate_parking_invoices()

API:
[ ] M15-A1  parking_api.py: get_parking_summary()
[ ] M15-A2  parking_api.py: get_available_bays()

MISC:
[ ] M15-M1  Create PARKING-FEE item in ERPNext

TESTS:
[ ] M15-X1  Allocate bay to unit → tenant auto-filled, status = Allocated
[ ] M15-X2  Standalone parking lease → monthly invoice auto-created
[ ] M15-X3  Bay goes Available → appears in get_available_bays

================================================================================
M02 — Leasing & Contract Management  (Phase 1 — Build after M01)
================================================================================
DOCTYPES:
[ ] M02-D1  Lease DocType (LAS-{YYYY}-{#####}) ← CORE
[ ] M02-D2  PDC Cheque Row child DocType
[ ] M02-D3  Lease Inspection Link child DocType
[ ] M02-D4  Rent Escalation Schedule child DocType
[ ] M02-D5  Percentage Rent Entry standalone DocType (PRE-{YYYY}-{MM}-{#####})

CONTROLLERS:
[ ] M02-C1  lease.py full controller (validate, on_submit, on_cancel, whitelist)
[ ] M02-C2  Lease Approval Workflow (Draft→Pending Approval→Active→Terminated)

API:
[ ] M02-A1  lease_api.py: get_lease_stats()
[ ] M02-A2  lease_api.py: get_leases() (paginated)
[ ] M02-A3  lease_api.py: get_expiring_leases()
[ ] M02-A4  lease_api.py: get_rera_rent_cap() (UAE RERA calculator)

TASKS:
[ ] M02-T1  tasks.py: send_lease_expiry_alerts() (60/30/7 days)
[ ] M02-T2  tasks.py: apply_due_rent_escalations() daily

TESTS:
[ ] M02-X1  Create lease → PDC schedule auto-generated for 4 cheques
[ ] M02-X2  Submit lease → unit status = Occupied
[ ] M02-X3  RERA cap warning fires when renewal rent too high
[ ] M02-X4  Escalation row applied on due date → annual_rent updated
[ ] M02-X5  initiate_renewal creates draft lease linked to parent

================================================================================
M03 — Billing, Revenue & PDC  (Phase 1 — Build after M02)
================================================================================
ERPNext SETUP:
[ ] M03-E1  Create 11 billing Items fixture (RENT-RES, RENT-COM, etc.)
[ ] M03-E2  Create UAE/KSA/Oman Tax Templates in ERPNext
[ ] M03-E3  Add 5 custom fields to Sales Invoice (propx_ prefix)

DOCTYPES:
[ ] M03-D1  PDC Register DocType (PDC-{YYYY}-{#####}) ← CRITICAL
[ ] M03-D2  PDC Deposit Batch DocType (DBATCH-{YYYY}{MM}-{###})
[ ] M03-D3  PDC Deposit Batch Cheque child DocType

CONTROLLERS:
[ ] M03-C1  pdc_register.py (validate, deposit, clear → Payment Entry, bounce)
[ ] M03-C2  billing_utils.py (generate_monthly_invoices, apply_late_fees, create_pdc_entries)
[ ] M03-C3  service_charge_utils.py (CAM reconciliation)

API:
[ ] M03-A1  billing_api.py: get_billing_kpis()
[ ] M03-A2  billing_api.py: get_pdc_kpis()
[ ] M03-A3  billing_api.py: get_upcoming_pdc()
[ ] M03-A4  billing_api.py: mark_pdc_deposited()
[ ] M03-A5  billing_api.py: mark_pdc_cleared()
[ ] M03-A6  billing_api.py: mark_pdc_bounced()

HOOKS:
[ ] M03-H1  Monthly scheduler: generate_monthly_invoices
[ ] M03-H2  Daily scheduler: apply_late_fees, send_pdc_due_reminders

TESTS:
[ ] M03-X1  Activate lease → PDC Register entries auto-created
[ ] M03-X2  Mark PDC cleared → Payment Entry created + SI reconciled
[ ] M03-X3  Mark PDC bounced → penalty invoice created
[ ] M03-X4  Late fee applies after grace period on unpaid invoice
[ ] M03-X5  CAM reconciliation calculates correct variance per tenant

================================================================================
M04 — Finance & GCC Compliance  (Phase 1 — Config-heavy)
================================================================================
SETUP SCRIPTS:
[ ] M04-S1  accounts_setup.py: UAE/KSA/Oman income+liability+expense accounts
[ ] M04-S2  Create 4 Tax Templates (UAE 5%, UAE Exempt, KSA 15%, Oman 5%)
[ ] M04-S3  Create trust bank account for security deposits

DOCTYPES:
[ ] M04-D1  Owner Disbursement DocType (DISB-{YYYY}{MM}-{###})
[ ] M04-D2  Owner Disbursement Property child DocType
[ ] M04-D3  PropX Settings Singleton DocType

CONTROLLERS:
[ ] M04-C1  OwnerDisbursement controller (validate: management_fee, net_disb)

API:
[ ] M04-A1  finance_api.py: get_vat_summary() (FTA/GAZT/OTA return)
[ ] M04-A2  finance_api.py: get_property_budget_vs_actual()

MISC:
[ ] M04-M1  Create "Owner Statement" print format

TESTS:
[ ] M04-X1  VAT summary matches individual invoice tax lines
[ ] M04-X2  Trust account correctly segregated from operational accounts

================================================================================
M05 — Tenant & CRM  (Phase 1)
================================================================================
CUSTOM FIELDS:
[ ] M05-CF1  Add all Customer custom fields via fixture (is_tenant, Emirates ID,
             passport, visa, trade_licence, whatsapp, kyc_documents, stats, etc.)

DOCTYPES:
[ ] M05-D1  Tenant KYC Document child DocType

CONTROLLERS:
[ ] M05-C1  hooks_on_customer.py (after_save: stats, KYC refresh, payment rating)
[ ] M05-C2  Register doc_events for Customer in hooks.py

UTILITIES:
[ ] M05-U1  notification_utils.py (WhatsApp WATI/Twilio + email)

API:
[ ] M05-A1  tenant_api.py: get_tenant_profile()
[ ] M05-A2  tenant_api.py: get_tenants_list() (paginated, filter by arrears)

TASKS:
[ ] M05-T1  Daily task: check KYC expiries, alert manager

TESTS:
[ ] M05-X1  Create tenant → add KYC docs → expiry flag updates
[ ] M05-X2  2 bounced PDCs → payment_rating = Poor

================================================================================
M06 — Maintenance & Facilities Management  (Phase 1)
================================================================================
DOCTYPES:
[ ] M06-D1  Maintenance Job Card DocType (WO-{YYYY}-{#####})
[ ] M06-D2  Maintenance Photo child DocType (istable)
[ ] M06-D3  PPM Schedule DocType (PPM-{####})
[ ] M06-D4  Vendor COI DocType (COI-{####})
[ ] M06-D5  COI Property Scope child DocType

ERPNext SETUP:
[ ] M06-E1  Create item "MAINT-SERVICE" in ERPNext for PO line

CONTROLLERS:
[ ] M06-C1  maintenance_job_card.py (SLA, cost approval, vendor COI, auto PO, notify)

TASKS:
[ ] M06-T1  tasks.py: generate_ppm_work_orders() daily
[ ] M06-T2  tasks.py: update_coi_statuses() daily

API:
[ ] M06-A1  maintenance_api.py: get_maintenance_kpis()
[ ] M06-A2  maintenance_api.py: get_kanban()
[ ] M06-A3  maintenance_api.py: submit_tenant_request() (portal)

HOOKS:
[ ] M06-H1  Hourly scheduler: SLA breach check
[ ] M06-H2  Daily scheduler: PPM generation + COI refresh

TESTS:
[ ] M06-X1  Emergency ticket → SLA = 2h, breach fires after 2h
[ ] M06-X2  Vendor assigned + cost approved → PO auto-created
[ ] M06-X3  Tenant submits via portal → WO created, tenant can see it
[ ] M06-X4  PPM due date passes → WO auto-generated, next date advanced

================================================================================
M07 — Utility & Meter Management  (Phase 2)
================================================================================
DOCTYPES:
[ ] M07-D1  Utility Meter DocType (MTR-{####})
[ ] M07-D2  Meter Reading DocType (MRD-{YYYY}{MM}-{####})

CONTROLLERS:
[ ] M07-C1  meter_reading.py (validate: consumption calc, on_submit: invoice)

API:
[ ] M07-A1  utility_api.py: get_utility_summary()

TESTS:
[ ] M07-X1  Submit reading → consumption invoice created for tenant

================================================================================
M08 — Security & Access Management  (Phase 2)
================================================================================
DOCTYPES:
[ ] M08-D1  Guard Shift DocType
[ ] M08-D2  Guard Shift Assignment child DocType
[ ] M08-D3  Visitor Log DocType (VIS-{YYYYMMDD}-{###})
[ ] M08-D4  Security Incident DocType (INC-{YYYY}-{###})
[ ] M08-D5  Key Register DocType

API:
[ ] M08-A1  security_api.py: get_security_kpis()
[ ] M08-A2  security_api.py: log_visitor_in()
[ ] M08-A3  security_api.py: log_visitor_out()

TESTS:
[ ] M08-X1  Log visitor in → on_premises count increments
[ ] M08-X2  Log visitor out → status = Left, check_out set

================================================================================
M09 — Tenant Self-Service Portal  (Phase 2 — React + React Native)
================================================================================
BACKEND:
[ ] M09-B1  tenant_portal_api.py: get_tenant_dashboard()

REACT WEB (Vite + React 18 + TanStack Query):
[ ] M09-W1  /login screen
[ ] M09-W2  /dashboard (lease summary, outstanding, PDC, tickets)
[ ] M09-W3  /lease/:id detail screen
[ ] M09-W4  /invoices list + PDF download
[ ] M09-W5  /maintenance list + new request
[ ] M09-W6  /maintenance/:id ticket status
[ ] M09-W7  /documents download screen
[ ] M09-W8  /profile + KYC + language preference
[ ] M09-W9  Arabic RTL toggle (react-i18next)

REACT NATIVE (Expo SDK 51):
[ ] M09-M1  Tab 1: Home dashboard
[ ] M09-M2  Tab 2: Maintenance + camera
[ ] M09-M3  Tab 3: Payments / invoice history
[ ] M09-M4  Tab 4: Documents
[ ] M09-M5  Tab 5: Profile + language toggle

TESTS:
[ ] M09-X1  Tenant logs in → sees their lease and balance
[ ] M09-X2  Submit maintenance request → WO appears in M06 kanban

================================================================================
M10 — Owner & Investor Portal  (Phase 2 — React)
================================================================================
BACKEND:
[ ] M10-B1  owner_api.py: get_owner_dashboard()
[ ] M10-B2  owner_api.py: get_property_performance()
[ ] M10-B3  owner_api.py: get_owner_statements()

REACT WEB:
[ ] M10-W1  /owner/login + route guard (Property Owner role)
[ ] M10-W2  /owner/dashboard portfolio KPIs
[ ] M10-W3  /owner/properties per-property table
[ ] M10-W4  /owner/statements list
[ ] M10-W5  /owner/statement/:id detail

TESTS:
[ ] M10-X1  Owner logs in → only sees their properties
[ ] M10-X2  Statement detail shows correct income/expense breakdown

================================================================================
M11 — Reporting & Analytics  (Phase 2)
================================================================================
SCRIPT REPORTS:
[ ] M11-R1  Occupancy & Vacancy Analysis report
[ ] M11-R2  Rent Collection Summary report
[ ] M11-R3  PDC Ageing Report
[ ] M11-R4  Lease Expiry Register
[ ] M11-R5  Property P&L / NOI Report

AI:
[ ] M11-AI1  ai_pricing.py: get_rent_recommendation()
[ ] M11-AI2  lease_abstraction.py: abstract_lease_pdf() via Claude API
[ ] M11-AI3  Add claude_api_key to PropX Settings

MISC:
[ ] M11-M1  Create PropX Dashboard (Frappe Dashboard DocType)

TESTS:
[ ] M11-X1  All 5 reports render with test data
[ ] M11-X2  Rent recommendation returns value with ≥3 comps
[ ] M11-X3  Lease abstraction extracts dates + amounts from sample PDF

================================================================================
M12 — Listings & Vacancy  (Phase 3)
================================================================================
DOCTYPES:
[ ] M12-D1  Vacancy Listing DocType
[ ] M12-D2  Listing Feature child DocType
[ ] M12-D3  Vacancy Inquiry child DocType
[ ] M12-D4  Lease Application standalone DocType

API:
[ ] M12-A1  listing_api.py: get_active_vacancies()
[ ] M12-A2  listing_api.py: submit_inquiry()
[ ] M12-A3  listing_api.py: auto_create_listing() (hook when unit → Vacant)

MISC:
[ ] M12-M1  React pipeline board for vacancies

TESTS:
[ ] M12-X1  Unit goes Vacant → Vacancy Listing auto-created
[ ] M12-X2  Submit inquiry → appears in listing inquiries

================================================================================
M13 — Platform Administration  (All phases)
================================================================================
DOCTYPES:
[ ] M13-D1  PropX Client DocType (SaaS registry)

INSTALL:
[ ] M13-I1  install.py: after_install() → roles, settings, custom fields, items
[ ] M13-I2  8 roles created: PropX Admin, Property Manager, Lease Manager,
            Maintenance Technician, Security Guard, Property Owner, Tenant, Accountant

AUDIT:
[ ] M13-A1  Set track_changes=1 on: Lease, PDC Register, Owner Disbursement,
            Property Unit, Maintenance Job Card (Sales Invoice + Payment Entry auto)

API:
[ ] M13-API1  admin_api.py: generate_api_key()

TESTS:
[ ] M13-X1  Fresh bench install → roles created, settings defaulted
[ ] M13-X2  Two companies on same site → user only sees own company data

================================================================================
SUMMARY COUNTS
================================================================================
Foundation steps:            11 tasks
M01 Property Registry:       15 tasks
M02 Leasing:                 14 tasks
M03 Billing & PDC:           16 tasks
M04 Finance & GCC:           11 tasks
M05 Tenant & CRM:            10 tasks
M06 Maintenance:             14 tasks
M07 Utility:                  4 tasks
M08 Security:                 8 tasks
M09 Tenant Portal:           17 tasks
M10 Owner Portal:             8 tasks
M11 Reporting & AI:          10 tasks
M12 Listings:                 7 tasks
M13 Platform Admin:           9 tasks
M14 Inspection:              10 tasks
M15 Parking:                  9 tasks
--------------------------------------------------------------------------------
TOTAL:                      173 tasks
ALL STATUS:                  26 completed / 147 pending
================================================================================

BUILD ORDER (respect dependencies):
F → M01 → M14 → M15 → M02 → M03 → M04 → M05 → M06 →
    M07 → M08 → M09 → M10 → M11 → M12 → M13
================================================================================
