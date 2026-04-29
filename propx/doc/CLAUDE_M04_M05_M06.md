# CLAUDE.md — M04: Finance & GCC Compliance
# propx/docs/CLAUDE_M04.md

## PURPOSE
Configuration layer over ERPNext finance. Sets up GCC-specific accounts,
VAT tax templates, trust accounting for deposits, budgets per property,
owner disbursements, and VAT return summaries.
Almost entirely configuration — minimal new code.

## WHAT TO CONFIGURE IN ERPNext (no new DocTypes needed)

### 1. Chart of Accounts (per company)

Run once via setup script `propx/setup/accounts_setup.py`:

```python
UAE_INCOME_ACCOUNTS = [
    "Rental Income - Residential",    # VAT exempt
    "Rental Income - Commercial",     # 5% VAT
    "Rental Income - Industrial",     # 5% VAT
    "Service Charge Income",          # 5% VAT
    "Parking Income",                 # 5% VAT
    "Utility Recovery Income",        # 5% VAT
    "Late Payment Income",
    "Bounce Penalty Income",
    "Other Property Income",
]
UAE_LIABILITY_ACCOUNTS = [
    "Security Deposits Payable",      # CLIENT MONEY — separate bank
    "VAT Payable - FTA",
    "Advance Rent Received",
]
UAE_EXPENSE_ACCOUNTS = [
    "Property Maintenance Expense",
    "Management Fee Expense",
    "Municipality Fee Expense",
    "Insurance Expense - Property",
    "DEWA Utility Expense",
    "SEWA Utility Expense",
    "Security Services Expense",
]
KSA_SPECIFICS = {"VAT Payable - GAZT": "Liability"}
OMAN_SPECIFICS = {"VAT Payable - OTA": "Liability"}
```

### 2. Tax Templates

```python
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
    }
]
```

---
## DOCTYPES TO BUILD (2 new)

### DocType: Owner Disbursement

Naming: `format:DISB-{YYYY}{MM}-{###}`

```
owner               Link→Customer   reqd   "Property owner/investor"
company             Link→Company    reqd
period_from         Date            reqd
period_to           Date            reqd
properties          Table→Owner Disbursement Property  (child)
gross_rent          Currency        read_only
management_fee_pct  Percent         default 5
management_fee      Currency        read_only
maintenance_deductions Currency
municipality_fees   Currency
other_deductions    Currency
net_disbursement    Currency        read_only, bold
status              Select          Draft|Approved|Paid|Disputed  default Draft
payment_date        Date
payment_reference   Data
bank_transfer_ref   Data
statement_pdf       Attach
notes               Text
```

Owner Disbursement Property (child istable):
```
property            Link→Property   reqd
gross_rent_collected Currency
occupancy_rate      Percent
```

**Controller:**
```python
class OwnerDisbursement(Document):
    def validate(self):
        if self.gross_rent:
            self.management_fee = round(
                float(self.gross_rent) * self.management_fee_pct / 100, 2
            )
            self.net_disbursement = (
                float(self.gross_rent)
                - float(self.management_fee or 0)
                - float(self.maintenance_deductions or 0)
                - float(self.municipality_fees or 0)
                - float(self.other_deductions or 0)
            )
```

---
### DocType: PropX Settings (Singleton)

```
# WhatsApp
whatsapp_provider       Select  wati|twilio|none
wati_api_url            Data
wati_api_token          Password
twilio_account_sid      Data
twilio_auth_token       Password
twilio_whatsapp_from    Data

# Billing defaults
late_payment_grace_days Int     default 5
late_fee_rate           Percent default 5
bounce_penalty_amount   Currency default 500
default_security_deposit_months Int default 2
default_notice_period_days Int  default 90
invoice_generation_day  Int     default 1

# E-signature
esign_provider          Select  docusign|hellosign|none
esign_api_key           Password
esign_api_url           Data

# Credit bureau (GCC)
credit_bureau_provider  Select  al_etihad|simah|none
credit_bureau_api_key   Password
credit_bureau_api_url   Data

# RERA
rera_api_enabled        Check   default 0
rera_api_key            Password
```

---
## KEY API ENDPOINTS

```python
# propx/property_management/api/finance_api.py
import frappe
from frappe.utils import get_first_day, get_last_day, today


@frappe.whitelist()
def get_vat_summary(company, from_date, to_date):
    """VAT return summary for FTA/GAZT/OTA filing."""
    taxable = frappe.db.sql("""
        SELECT stc.rate, SUM(stc.base_tax_amount) as tax_amount,
               SUM(stc.base_taxable_amount) as taxable_amount,
               COUNT(DISTINCT si.name) as invoice_count
        FROM `tabSales Invoice` si
        JOIN `tabSales Taxes and Charges` stc ON stc.parent = si.name
        WHERE si.docstatus=1 AND si.company=%(co)s
          AND si.posting_date BETWEEN %(f)s AND %(t)s
        GROUP BY stc.rate
    """, {"co": company, "f": from_date, "t": to_date}, as_dict=True)

    exempt = frappe.db.sql("""
        SELECT SUM(grand_total) FROM `tabSales Invoice`
        WHERE docstatus=1 AND company=%(co)s
          AND (taxes_and_charges IS NULL OR taxes_and_charges='')
          AND posting_date BETWEEN %(f)s AND %(t)s
          AND propx_lease IS NOT NULL
    """, {"co": company, "f": from_date, "t": to_date})[0][0] or 0

    return {"taxable_sales": taxable, "exempt_income": exempt}


@frappe.whitelist()
def get_property_budget_vs_actual(property_name, year):
    """Budget vs actual for a property's cost centre."""
    cc = frappe.db.get_value("Property", property_name, "cost_centre")
    if not cc:
        return {}
    income_actual = frappe.db.sql("""
        SELECT SUM(credit - debit) FROM `tabGL Entry`
        WHERE cost_center=%s AND YEAR(posting_date)=%s
          AND account IN (SELECT name FROM `tabAccount`
                          WHERE account_type='Income Account')
          AND is_cancelled=0
    """, (cc, year))[0][0] or 0
    expense_actual = frappe.db.sql("""
        SELECT SUM(debit - credit) FROM `tabGL Entry`
        WHERE cost_center=%s AND YEAR(posting_date)=%s
          AND account IN (SELECT name FROM `tabAccount`
                          WHERE account_type='Expense Account')
          AND is_cancelled=0
    """, (cc, year))[0][0] or 0
    return {
        "property": property_name,
        "year": year,
        "income_actual": income_actual,
        "expense_actual": expense_actual,
        "noi_actual": income_actual - expense_actual
    }
```

---
## CHECKLIST M04
- [ ] Run accounts_setup.py for each company
- [ ] Create 4 tax templates
- [ ] Create Owner Disbursement DocType + child
- [ ] Create PropX Settings singleton
- [ ] Write OwnerDisbursement controller
- [ ] Write finance_api.py (VAT summary, budget vs actual)
- [ ] Create "Owner Statement" print format
- [ ] Create trust bank account for security deposits
- [ ] Test: VAT summary matches individual invoice tax lines


---
---
# CLAUDE.md — M05: Tenant & CRM
# propx/docs/CLAUDE_M05.md

## PURPOSE
Tenant management on top of ERPNext Customer.
KYC document tracking, communication log, WhatsApp notifications,
credit bureau screening, corporate vs individual handling, payment rating.

## REUSE FROM ERPNext
- `Customer`     → every tenant IS a Customer (extend, don't replace)
- `Contact`      → tenant contact persons
- `Address`      → tenant address
- `Communication`→ use ERPNext comm log for email history

## CUSTOM FIELDS ON CUSTOMER

```python
TENANT_CUSTOM_FIELDS = {
    "Customer": [
        # Flag
        ("is_tenant",           "Check",  "Is Tenant",      "0"),
        ("tenant_type",         "Select", "Individual|Corporate", None),

        # Individual KYC
        ("emirates_id",         "Data",   "Emirates ID No.", None),
        ("emirates_id_expiry",  "Date",   "Emirates ID Expiry", None),
        ("passport_number",     "Data",   "Passport No.",    None),
        ("passport_expiry",     "Date",   "Passport Expiry", None),
        ("visa_number",         "Data",   "Visa/Residency No.", None),
        ("visa_expiry",         "Date",   "Visa Expiry",     None),
        ("nationality",         "Link",   "Country",         None),

        # Corporate KYC
        ("trade_licence_no",    "Data",   "Trade Licence No.", None),
        ("trade_licence_expiry","Date",   "Trade Licence Expiry", None),
        ("company_reg_no",      "Data",   "Company Reg. No.", None),
        ("authorised_signatory","Data",   "Authorised Signatory", None),

        # Contact preferences
        ("whatsapp_number",     "Data",   "WhatsApp No. (+971...)", None),
        ("preferred_language",  "Select", "English|Arabic",  "English"),

        # KYC documents table
        ("kyc_documents",       "Table",  "Tenant KYC Document", None),

        # Computed stats (read-only)
        ("active_leases_count", "Int",    "Active Leases",   None),
        ("total_arrears",       "Currency","Total Arrears",   None),
        ("tenancy_since",       "Date",   "Tenant Since",    None),
        ("payment_rating",      "Select", "Excellent|Good|Fair|Poor|New", None),
        ("credit_score",        "Int",    "Credit Bureau Score", None),
        ("credit_checked_on",   "Date",   "Last Credit Check", None),
    ]
}
```

---
## TENANT KYC DOCUMENT (child DocType)

```
document_type   Select  reqd
                Emirates ID|Passport|Visa/Residency|Trade Licence
                |MOA|POA|Tenancy Contract|Ejari Certificate|Other
document_number Data            in_list_view
expiry_date     Date            in_list_view
document_file   Attach          reqd
kyc_status      Select
                Valid|Expiring Soon|Expired|Pending|Rejected
                in_list_view
verified_by     Link→User
verified_date   Date
remarks         Small Text
```

---
## PYTHON HOOKS ON CUSTOMER

```python
# propx/property_management/hooks_on_customer.py
# Registered via doc_events in hooks.py

import frappe
from frappe.utils import today, date_diff, flt, getdate


def after_save(doc, method):
    if not doc.is_tenant:
        return
    _update_tenant_stats(doc)
    _refresh_kyc_statuses(doc)
    _set_payment_rating(doc)


def _update_tenant_stats(doc):
    active = frappe.db.count("Lease", {
        "tenant": doc.name,
        "status": ["in", ["Active", "Expiring"]]
    })
    arrears = frappe.db.sql("""
        SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
        WHERE customer=%s AND docstatus=1 AND outstanding_amount>0
    """, doc.name)[0][0] or 0
    frappe.db.set_value("Customer", doc.name, {
        "active_leases_count": active,
        "total_arrears": arrears
    })


def _refresh_kyc_statuses(doc):
    for kyc in doc.kyc_documents:
        if not kyc.expiry_date:
            continue
        days = date_diff(kyc.expiry_date, today())
        if days < 0:
            new_status = "Expired"
        elif days <= 30:
            new_status = "Expiring Soon"
        else:
            new_status = "Valid"
        if kyc.kyc_status != new_status:
            frappe.db.set_value(
                "Tenant KYC Document", kyc.name, "kyc_status", new_status
            )


def _set_payment_rating(doc):
    bounces = frappe.db.count(
        "PDC Register", {"tenant": doc.name, "status": "Bounced"}
    )
    overdue = frappe.db.count(
        "Sales Invoice",
        {"customer": doc.name, "status": "Overdue", "docstatus": 1}
    )
    if bounces == 0 and overdue == 0:
        rating = "Excellent"
    elif bounces == 0 and overdue <= 1:
        rating = "Good"
    elif bounces <= 1 and overdue <= 2:
        rating = "Fair"
    else:
        rating = "Poor"
    frappe.db.set_value("Customer", doc.name, "payment_rating", rating)
```

Register in hooks.py:
```python
doc_events = {
    "Customer": {
        "after_save": "propx.property_management.hooks_on_customer.after_save"
    }
}
```

---
## WHATSAPP UTILITY

```python
# propx/property_management/utils/notification_utils.py
import frappe, requests


def send_whatsapp(to_number, message, template_name=None, params=None):
    settings = frappe.get_single("PropX Settings")
    if settings.whatsapp_provider == "wati":
        _send_wati(to_number, message, template_name, params, settings)
    elif settings.whatsapp_provider == "twilio":
        _send_twilio(to_number, message, settings)


def _send_wati(to, msg, template, params, s):
    url = f"{s.wati_api_url}/api/v1/sendSessionMessage/{to.replace('+','')}"
    r = requests.post(url,
        headers={"Authorization": f"Bearer {s.wati_api_token}"},
        json={"messageText": msg},
        timeout=10
    )
    return r.json()


def _send_twilio(to, msg, s):
    from twilio.rest import Client
    client = Client(s.twilio_account_sid, s.twilio_auth_token)
    client.messages.create(
        body=msg,
        from_=f"whatsapp:{s.twilio_whatsapp_from}",
        to=f"whatsapp:{to}"
    )


def notify_tenant(tenant_name, subject, body):
    """Unified: send WhatsApp + email based on preference."""
    tenant = frappe.get_doc("Customer", tenant_name)
    if tenant.whatsapp_number:
        send_whatsapp(tenant.whatsapp_number, body)
    frappe.sendmail(
        recipients=[tenant.email_id],
        subject=subject,
        message=body
    )
```

---
## API ENDPOINTS

```python
# propx/property_management/api/tenant_api.py
import frappe


@frappe.whitelist()
def get_tenant_profile(tenant):
    doc = frappe.get_doc("Customer", tenant)
    leases = frappe.get_all("Lease", {"tenant": tenant},
        fields=["name","unit","property","status",
                "start_date","end_date","annual_rent"])
    invoices = frappe.get_all("Sales Invoice",
        {"customer": tenant, "docstatus": 1},
        fields=["name","posting_date","grand_total",
                "status","outstanding_amount"],
        order_by="posting_date desc", limit=10)
    pdcs = frappe.get_all("PDC Register",
        {"tenant": tenant},
        fields=["name","cheque_number","bank_name",
                "amount","cheque_date","status"],
        order_by="cheque_date desc", limit=12)
    kyc_alerts = [
        k for k in doc.kyc_documents
        if k.kyc_status in ["Expiring Soon","Expired"]
    ]
    return {
        "profile": {
            "name": doc.name,
            "customer_name": doc.customer_name,
            "tenant_type": doc.tenant_type,
            "whatsapp_number": doc.whatsapp_number,
            "preferred_language": doc.preferred_language,
            "payment_rating": doc.payment_rating,
            "active_leases_count": doc.active_leases_count,
            "total_arrears": doc.total_arrears,
        },
        "leases": leases,
        "recent_invoices": invoices,
        "recent_pdcs": pdcs,
        "kyc_alerts": kyc_alerts
    }


@frappe.whitelist()
def get_tenants_list(search=None, tenant_type=None, has_arrears=None,
                      page=1, page_size=25):
    f = {"is_tenant": 1}
    if tenant_type:
        f["tenant_type"] = tenant_type
    if search:
        f["customer_name"] = ["like", f"%{search}%"]
    tenants = frappe.get_all("Customer", filters=f,
        fields=["name","customer_name","tenant_type","mobile_no",
                "whatsapp_number","active_leases_count",
                "total_arrears","payment_rating"],
        start=(int(page)-1)*int(page_size),
        page_length=int(page_size))
    if has_arrears == "1":
        tenants = [t for t in tenants if (t.total_arrears or 0) > 0]
    return {"tenants": tenants,
            "total": frappe.db.count("Customer", f)}
```

---
## CHECKLIST M05
- [ ] Add all custom fields to Customer via fixture
- [ ] Create Tenant KYC Document child DocType
- [ ] Write hooks_on_customer.py (stats, KYC refresh, rating)
- [ ] Register doc_events in hooks.py
- [ ] Write notification_utils.py (WhatsApp + email)
- [ ] Write tenant_api.py (get_tenant_profile, get_tenants_list)
- [ ] Daily task: check KYC expiries, alert manager
- [ ] Test: create tenant → add KYC docs → expiry flag updates
- [ ] Test: 2 bounced PDCs → payment_rating = Poor


---
---
# CLAUDE.md — M06: Maintenance & Facilities Management
# propx/docs/CLAUDE_M06.md

## PURPOSE
Work order lifecycle from tenant request to closure. SLA tracking,
vendor assignment, cost control with PO approval, move-in/move-out
inspections (see M14), preventive maintenance scheduling,
vendor COI tracking.

## DEPENDS ON
- M01: Property Unit
- ERPNext: Employee (technicians), Supplier (vendors), Purchase Order

---
## DOCTYPES TO BUILD (3 new)

### DocType: Maintenance Job Card  ← CORE

Naming: `format:WO-{YYYY}-{#####}`
Track changes: yes

```
# === IDENTITY ===
subject             Data        reqd, in_list_view, bold
property            Link→Property  reqd
unit                Link→Property Unit
location_detail     Data        "e.g. Kitchen, Level 3, Lobby"

# === CATEGORY & PRIORITY ===
category            Select      reqd, in_list_view
                    Plumbing|Electrical|HVAC|Civil|Mechanical
                    |Safety|Cleaning|Pest Control|Painting|Lifts|Other
priority            Select      reqd
                    Low|Medium|High|Emergency  default Medium
is_ppm              Check       default 0  "Preventive maintenance"
ppm_schedule        Link→PPM Schedule

# === DESCRIPTION ===
description         Text Editor
reported_by_tenant  Check       default 0
tenant_reference    Link→Customer  depends_on: reported_by_tenant

# === ASSIGNMENT ===
assigned_technician Link→Employee
vendor              Link→Supplier
vendor_reference    Data        "Vendor's own work order number"
vendor_coi_valid    Check       read_only  default 0

# === SLA ===
sla_hours           Int         read_only  "Set from priority"
sla_deadline        Datetime    read_only
sla_status          Select      On Time|At Risk|Breached  read_only
breached_at         Datetime    read_only

# === STATUS ===
ticket_status       Select      reqd
                    New|Assigned|In Progress|Pending Parts
                    |Pending Approval|Completed|Closed|Cancelled
                    default New, in_list_view

# === COST ===
estimated_cost      Currency
actual_cost         Currency
cost_approval_required Check   read_only
cost_approved       Check       default 0
purchase_order      Link→Purchase Order  read_only
                    "Auto-created when vendor assigned + cost approved"

# === QUALITY ===
resolution_notes    Text Editor
tenant_satisfaction Select      1-Very Unsatisfied|2-Unsatisfied|3-Neutral
                                |4-Satisfied|5-Very Satisfied
tenant_notified     Check       default 0

# === PHOTOS ===
before_photos       Table→Maintenance Photo  (child)
after_photos        Table→Maintenance Photo  (child)

# === TIMESTAMPS ===
opened_at           Datetime    read_only
assigned_at         Datetime    read_only
completed_at        Datetime    read_only
resolution_hours    Float       read_only
```

**Maintenance Photo** (child istable):
```
photo       Attach Image    reqd
caption     Data
taken_at    Datetime
```

---
### DocType: PPM Schedule (Preventive Maintenance)

Naming: `format:PPM-{####}`

```
title               Data        reqd
property            Link→Property  reqd
unit                Link→Property Unit
category            Select      (same as WO category)
frequency           Select      reqd
                    Daily|Weekly|Monthly|Quarterly|Semi-Annual|Annual
next_due_date       Date        reqd
last_done_date      Date        read_only
description         Text
assigned_to         Link→Employee
vendor              Link→Supplier
estimated_duration_hours Float
estimated_cost      Currency
is_active           Check       default 1
```

---
### DocType: Vendor COI (Certificate of Insurance)

Naming: `format:COI-{####}`

```
vendor              Link→Supplier  reqd
insurance_company   Data            reqd
policy_number       Data            reqd
coverage_type       Select
                    Public Liability|Workers Comp|Property Damage|All Risks
coverage_amount     Currency
valid_from          Date            reqd
valid_to            Date            reqd
coi_document        Attach          reqd
status              Select          Valid|Expiring Soon|Expired  read_only
property_scope      Table→COI Property Scope  (child — which properties covered)
```

COI Property Scope (child):
```
property    Link→Property
```

---
## PYTHON CONTROLLER

```python
# propx/property_management/doctype/maintenance_job_card/maintenance_job_card.py

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date, time_diff_in_hours


SLA_HOURS = {"Emergency": 2, "High": 8, "Medium": 24, "Low": 72}
APPROVAL_THRESHOLD_AED = 5000


class MaintenanceJobCard(Document):

    def before_insert(self):
        self.opened_at = now_datetime()
        self._set_sla_deadline()

    def validate(self):
        self._update_sla_status()
        self._check_cost_approval()
        self._check_vendor_coi()

    def _set_sla_deadline(self):
        hours = SLA_HOURS.get(self.priority, 24)
        self.sla_hours = hours
        self.sla_deadline = add_to_date(
            self.opened_at, hours=hours, as_datetime=True
        )

    def _update_sla_status(self):
        if not self.sla_deadline:
            return
        now = now_datetime()
        dl = frappe.utils.get_datetime(self.sla_deadline)
        if self.ticket_status in ["Completed", "Closed"]:
            if self.completed_at:
                self.sla_status = (
                    "On Time"
                    if frappe.utils.get_datetime(self.completed_at) <= dl
                    else "Breached"
                )
            return
        if now > dl:
            self.sla_status = "Breached"
            if not self.breached_at:
                self.breached_at = dl
        elif time_diff_in_hours(dl, now) <= 2:
            self.sla_status = "At Risk"
        else:
            self.sla_status = "On Time"

    def _check_cost_approval(self):
        threshold = frappe.db.get_single_value(
            "PropX Settings", "maintenance_cost_approval_threshold"
        ) or APPROVAL_THRESHOLD_AED
        self.cost_approval_required = (
            bool(self.estimated_cost) and
            float(self.estimated_cost) > float(threshold)
        )

    def _check_vendor_coi(self):
        """Validate vendor has valid COI before assignment."""
        if not self.vendor:
            self.vendor_coi_valid = 0
            return
        valid_coi = frappe.db.exists("Vendor COI", {
            "vendor": self.vendor,
            "status": "Valid"
        })
        self.vendor_coi_valid = 1 if valid_coi else 0
        if self.vendor and not self.vendor_coi_valid:
            frappe.msgprint(
                f"⚠️ Vendor {self.vendor} has no valid Certificate of Insurance. "
                "Please obtain COI before assigning work.",
                indicator="orange"
            )

    def on_update(self):
        self._track_timestamps()
        self._calculate_resolution_time()
        self._auto_create_po()
        self._notify_tenant_on_completion()

    def _track_timestamps(self):
        if self.ticket_status == "Assigned" and not self.assigned_at:
            self.assigned_at = now_datetime()
        elif (self.ticket_status in ["Completed", "Closed"]
              and not self.completed_at):
            self.completed_at = now_datetime()

    def _calculate_resolution_time(self):
        if self.completed_at and self.opened_at:
            self.resolution_hours = round(
                time_diff_in_hours(self.completed_at, self.opened_at), 1
            )

    def _auto_create_po(self):
        """Create Purchase Order when vendor assigned + cost approved."""
        if (self.vendor and self.cost_approved
                and self.estimated_cost
                and not self.purchase_order):
            po = frappe.new_doc("Purchase Order")
            po.supplier = self.vendor
            po.schedule_date = frappe.utils.add_days(
                frappe.utils.today(), 3
            )
            po.append("items", {
                "item_code": "MAINT-SERVICE",
                "qty": 1,
                "rate": float(self.estimated_cost),
                "description": f"Maintenance: {self.subject} | {self.name}"
            })
            po.insert(ignore_permissions=True)
            self.purchase_order = po.name

    def _notify_tenant_on_completion(self):
        if (self.ticket_status == "Completed"
                and self.reported_by_tenant
                and not self.tenant_notified
                and self.unit):
            tenant = frappe.db.get_value(
                "Property Unit", self.unit, "current_tenant"
            )
            if tenant:
                from propx.property_management.utils.notification_utils import (
                    notify_tenant
                )
                notify_tenant(
                    tenant,
                    f"Maintenance request #{self.name} completed",
                    f"Your maintenance request ({self.subject}) "
                    f"has been completed. "
                    f"Please rate your satisfaction: 1 (poor) to 5 (excellent)."
                )
                frappe.db.set_value(
                    "Maintenance Job Card", self.name, "tenant_notified", 1
                )
```

---
## PPM AUTO-GENERATOR

```python
# propx/property_management/tasks.py (add these)

def generate_ppm_work_orders():
    """Daily: create WOs for PPM schedules due today or overdue."""
    today_str = frappe.utils.today()
    due = frappe.get_all("PPM Schedule", filters={
        "is_active": 1,
        "next_due_date": ["<=", today_str]
    }, fields=["name","title","property","unit","category",
               "assigned_to","vendor","estimated_cost"])

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

        # Advance next due date
        freq_map = {
            "Daily": 1, "Weekly": 7, "Monthly": 30,
            "Quarterly": 90, "Semi-Annual": 180, "Annual": 365
        }
        ppm_doc = frappe.get_doc("PPM Schedule", ppm.name)
        days = freq_map.get(ppm_doc.frequency, 30)
        ppm_doc.next_due_date = frappe.utils.add_days(today_str, days)
        ppm_doc.last_done_date = today_str
        ppm_doc.save(ignore_permissions=True)
    frappe.db.commit()


def update_coi_statuses():
    """Daily: mark COIs as Expiring Soon or Expired."""
    today_str = frappe.utils.today()
    warn_date = frappe.utils.add_days(today_str, 30)
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
```

---
## API ENDPOINTS

```python
# propx/property_management/api/maintenance_api.py
import frappe
from frappe.utils import today, add_days


@frappe.whitelist()
def get_maintenance_kpis():
    return {
        "open": frappe.db.count("Maintenance Job Card", {
            "ticket_status": ["in", ["New","Assigned","In Progress"]]
        }),
        "sla_breaches": frappe.db.count("Maintenance Job Card", {
            "sla_status": "Breached",
            "ticket_status": ["not in", ["Closed","Cancelled"]]
        }),
        "pending_approval": frappe.db.count("Maintenance Job Card", {
            "ticket_status": "Pending Approval"
        }),
        "completed_month": frappe.db.count("Maintenance Job Card", {
            "ticket_status": ["in",["Completed","Closed"]],
            "completed_at": [">=", frappe.utils.get_first_day(today())]
        }),
        "avg_resolution_hours": frappe.db.sql(
            "SELECT AVG(resolution_hours) FROM `tabMaintenance Job Card` "
            "WHERE resolution_hours>0 AND completed_at>=%s",
            (add_days(today(), -30),)
        )[0][0] or 0
    }


@frappe.whitelist()
def get_kanban(property_name=None):
    f = {"ticket_status": ["not in",["Closed","Cancelled"]]}
    if property_name:
        f["property"] = property_name
    tickets = frappe.get_all("Maintenance Job Card", filters=f,
        fields=["name","subject","unit","property","category",
                "priority","ticket_status","sla_status",
                "assigned_technician","vendor","estimated_cost",
                "actual_cost","sla_deadline","reported_by_tenant"])
    grouped = {}
    for t in tickets:
        grouped.setdefault(t.ticket_status, []).append(t)
    return grouped


@frappe.whitelist()
def submit_tenant_request(unit, subject, category, description):
    """Called from tenant portal (M09)."""
    tenant = frappe.db.get_value("Property Unit", unit, "current_tenant")
    if not tenant:
        frappe.throw("No active tenant for this unit.")
    # verify caller is this tenant
    caller_customer = frappe.db.get_value(
        "Customer", {"email_id": frappe.session.user}, "name"
    )
    if caller_customer != tenant:
        frappe.throw("You can only raise requests for your own unit.")

    wo = frappe.new_doc("Maintenance Job Card")
    wo.subject = subject
    wo.unit = unit
    wo.property = frappe.db.get_value("Property Unit", unit, "property")
    wo.category = category
    wo.description = description
    wo.priority = "Medium"
    wo.reported_by_tenant = 1
    wo.tenant_reference = tenant
    wo.ticket_status = "New"
    wo.insert(ignore_permissions=True)
    return {"ticket": wo.name}
```

---
## CHECKLIST M06
- [ ] Create Maintenance Job Card DocType
- [ ] Create Maintenance Photo child DocType
- [ ] Create PPM Schedule DocType
- [ ] Create Vendor COI DocType + COI Property Scope child
- [ ] Create item "MAINT-SERVICE" in ERPNext for PO line
- [ ] Write maintenance_job_card.py controller
- [ ] Write tasks.py additions (PPM generator, COI status update)
- [ ] Write maintenance_api.py (5 endpoints)
- [ ] Add hourly scheduler for SLA breach check
- [ ] Add daily scheduler for PPM generation and COI refresh
- [ ] Test: Emergency ticket → SLA deadline = 2h, breach fires after 2h
- [ ] Test: vendor assigned + cost approved → PO auto-created
- [ ] Test: tenant submits via portal → WO created, they can see it
- [ ] Test: PPM due date passes → WO auto-generated, next date advanced
