# CLAUDE.md — M11: Reporting & Analytics
# propx/docs/CLAUDE_M11.md

## PURPOSE
Script reports, KPI dashboards, AI rent pricing, AI lease abstraction,
NOI forecasting, and VAT reporting. Built on ERPNext's report engine.

---
## SCRIPT REPORTS TO CREATE

Create each as a Frappe Script Report in `propx/property_management/report/`.

### Report 1: Occupancy & Vacancy Analysis

```python
# columns
def get_columns():
    return [
        {"fieldname": "property",       "label": "Property",       "fieldtype": "Link", "options": "Property", "width": 160},
        {"fieldname": "usage_type",     "label": "Type",           "width": 100},
        {"fieldname": "total_units",    "label": "Total",          "fieldtype": "Int",  "width": 70},
        {"fieldname": "occupied",       "label": "Occupied",       "fieldtype": "Int",  "width": 80},
        {"fieldname": "vacant",         "label": "Vacant",         "fieldtype": "Int",  "width": 70},
        {"fieldname": "occupancy_pct",  "label": "Occupancy %",    "fieldtype": "Percent", "width": 100},
        {"fieldname": "avg_days_vacant","label": "Avg Days Vacant","fieldtype": "Float","width": 120},
        {"fieldname": "monthly_revenue","label": "Monthly Rev. AED","fieldtype": "Currency","width": 150},
    ]

def get_data(filters):
    return frappe.db.sql("""
        SELECT pu.property, pu.usage_type,
               COUNT(*) AS total_units,
               SUM(pu.status='Occupied') AS occupied,
               SUM(pu.status='Vacant')   AS vacant,
               ROUND(SUM(pu.status='Occupied')/COUNT(*)*100,1) AS occupancy_pct,
               ROUND(AVG(CASE WHEN pu.status='Vacant' THEN pu.days_vacant END),1) AS avg_days_vacant,
               ROUND(SUM(CASE WHEN pu.status='Occupied'
                   THEN pu.last_agreed_rent/12 ELSE 0 END),0) AS monthly_revenue
        FROM `tabProperty Unit` pu
        WHERE pu.status != 'Decommissioned'
          AND (%(property)s IS NULL OR pu.property=%(property)s)
        GROUP BY pu.property, pu.usage_type
        ORDER BY pu.property
    """, filters, as_dict=True)
```

---
### Report 2: Rent Collection Summary

```python
def get_data(filters):
    return frappe.db.sql("""
        SELECT si.propx_property AS property,
               COUNT(DISTINCT si.customer) AS tenants,
               SUM(si.grand_total) AS invoiced,
               SUM(si.grand_total - si.outstanding_amount) AS collected,
               SUM(si.outstanding_amount) AS outstanding,
               ROUND(SUM(si.grand_total - si.outstanding_amount)
                     / NULLIF(SUM(si.grand_total),0)*100, 1) AS collection_rate
        FROM `tabSales Invoice` si
        WHERE si.docstatus=1
          AND si.propx_lease IS NOT NULL
          AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY si.propx_property
    """, filters, as_dict=True)
```

---
### Report 3: PDC Ageing Report

```python
def get_data(filters):
    return frappe.db.sql("""
        SELECT p.name, p.cheque_number, p.bank_name,
               p.tenant, c.customer_name,
               p.amount, p.cheque_date, p.status,
               p.bounce_risk, p.previous_bounces,
               DATEDIFF(p.cheque_date, CURDATE()) AS days_to_due
        FROM `tabPDC Register` p
        LEFT JOIN `tabCustomer` c ON c.name=p.tenant
        WHERE p.status IN ('Received','Deposited')
        ORDER BY p.cheque_date ASC
    """, as_dict=True)
```

---
### Report 4: Lease Expiry Register

```python
def get_data(filters):
    return frappe.db.sql("""
        SELECT l.name, l.tenant_name, l.unit, l.property,
               l.lease_category, l.start_date, l.end_date,
               l.annual_rent, l.renewal_status,
               DATEDIFF(l.end_date, CURDATE()) AS days_remaining
        FROM `tabLease` l
        WHERE l.status IN ('Active','Expiring')
          AND l.end_date BETWEEN %(from_date)s AND %(to_date)s
        ORDER BY l.end_date ASC
    """, filters, as_dict=True)
```

---
### Report 5: Property P&L (NOI Report)

```python
def get_data(filters):
    props = frappe.get_all("Property",
        filters={"company": filters.get("company")},
        fields=["name","property_name","cost_centre"])

    rows = []
    for p in props:
        income = frappe.db.sql("""
            SELECT SUM(grand_total - outstanding_amount)
            FROM `tabSales Invoice`
            WHERE propx_property=%s AND docstatus=1
              AND posting_date BETWEEN %s AND %s
        """, (p.name, filters["from_date"], filters["to_date"]))[0][0] or 0

        expense = frappe.db.sql("""
            SELECT SUM(grand_total)
            FROM `tabPurchase Invoice`
            WHERE cost_center=%s AND docstatus=1
              AND posting_date BETWEEN %s AND %s
        """, (p.cost_centre, filters["from_date"], filters["to_date"]))[0][0] or 0

        rows.append({
            "property": p.name,
            "property_name": p.property_name,
            "gross_income": income,
            "total_expense": expense,
            "noi": income - expense,
        })
    return rows
```

---
## AI RENT PRICING

```python
# propx/property_management/utils/ai_pricing.py
import frappe


@frappe.whitelist()
def get_rent_recommendation(unit_name):
    unit = frappe.get_doc("Property Unit", unit_name)

    # Last 5 rents for this unit
    history = frappe.db.sql("""
        SELECT annual_rent, start_date FROM `tabLease`
        WHERE unit=%s AND status NOT IN ('Draft','Cancelled')
        ORDER BY start_date DESC LIMIT 5
    """, unit_name, as_dict=True)

    # Comparable units same property, same type, ±20% area
    comps = frappe.db.sql("""
        SELECT pu.area_sqft, l.annual_rent
        FROM `tabProperty Unit` pu
        JOIN `tabLease` l ON l.unit=pu.name
        WHERE pu.property=%s AND pu.usage_type=%s
          AND pu.name!=%s
          AND l.status IN ('Active','Expiring')
          AND pu.area_sqft BETWEEN %s AND %s
    """, (unit.property, unit.usage_type, unit_name,
          (unit.area_sqft or 0)*0.8, (unit.area_sqft or 0)*1.2), as_dict=True)

    comp_rents = [c.annual_rent for c in comps if c.annual_rent]
    avg_comp = sum(comp_rents)/len(comp_rents) if comp_rents else None
    last_rent = history[0].annual_rent if history else None
    benchmark = unit.market_rent_benchmark

    candidates = [r for r in [avg_comp, last_rent, benchmark] if r]
    if not candidates:
        return {"recommendation": None, "reason": "Insufficient data"}

    recommended = round(max(candidates) * 1.05 / 100) * 100  # 5% uplift, round to 100

    return {
        "unit": unit_name,
        "current_asking": unit.asking_rent_annual,
        "last_agreed_rent": last_rent,
        "avg_comparable_rent": avg_comp,
        "market_benchmark": benchmark,
        "recommended_rent": recommended,
        "comparable_units": len(comps),
        "confidence": "High" if len(comps)>=3 else "Medium" if len(comps)>=1 else "Low"
    }
```

---
## AI LEASE ABSTRACTION (Claude API)

```python
# propx/property_management/utils/lease_abstraction.py
import frappe, json, requests


@frappe.whitelist()
def abstract_lease_pdf(lease_name, pdf_base64):
    """
    Upload lease PDF → Claude API extracts key terms
    → auto-fills Lease DocType fields.
    """
    prompt = """You are a GCC real estate lease abstraction specialist.
Extract the following fields from this lease document and return ONLY
valid JSON with these keys (use null if not found):
{
  "tenant_name": "",
  "property_address": "",
  "unit_number": "",
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "annual_rent": 0,
  "currency": "AED",
  "security_deposit": 0,
  "number_of_cheques": 4,
  "notice_period_days": 90,
  "has_break_clause": false,
  "break_clause_date": null,
  "escalation_pct": null,
  "ejari_number": null,
  "special_conditions": ""
}"""

    api_key = frappe.db.get_single_value("PropX Settings", "claude_api_key")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        },
        json={
            "model": "claude-opus-4-6",
            "max_tokens": 1024,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "document",
                     "source": {
                         "type": "base64",
                         "media_type": "application/pdf",
                         "data": pdf_base64
                     }}
                ]
            }]
        },
        timeout=30
    )
    result = r.json()
    text = result["content"][0]["text"]
    try:
        extracted = json.loads(text)
    except Exception:
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        extracted = json.loads(m.group()) if m else {}

    # Auto-fill the lease
    if lease_name and extracted:
        lease_doc = frappe.get_doc("Lease", lease_name)
        field_map = {
            "start_date": "start_date",
            "end_date": "end_date",
            "annual_rent": "annual_rent",
            "security_deposit": "security_deposit",
            "number_of_cheques": "number_of_cheques",
            "notice_period_days": "notice_period_days",
            "ejari_number": "ejari_contract_no",
            "special_conditions": "special_conditions",
        }
        for src, dst in field_map.items():
            if extracted.get(src) is not None:
                setattr(lease_doc, dst, extracted[src])
        lease_doc.save(ignore_permissions=True)

    return {"extracted": extracted, "lease_updated": bool(lease_name)}
```

Add `claude_api_key Password` field to PropX Settings.

---
## CHECKLIST M11
- [ ] Create 5 Script Reports
- [ ] Write ai_pricing.py with get_rent_recommendation
- [ ] Write lease_abstraction.py with Claude API integration
- [ ] Add claude_api_key to PropX Settings
- [ ] Create PropX Dashboard (Frappe Dashboard DocType)
- [ ] Test: all 5 reports render with test data
- [ ] Test: rent recommendation returns value with ≥3 comps
- [ ] Test: lease abstraction extracts dates + amounts from sample PDF


---
---
# CLAUDE.md — M12: Listings & Vacancy Management
# propx/docs/CLAUDE_M12.md  (Phase 3)

## PURPOSE
Vacancy pipeline, online lead capture, broker portal, digital applications.

---
## DOCTYPES TO BUILD

### Vacancy Listing

```
unit                Link→Property Unit  reqd (auto-created when unit goes Vacant)
property            Link→Property       read_only
listing_status      Select  Active|Under Offer|Leased|Withdrawn  default Active
asking_rent         Currency    reqd
available_from      Date
description         Text Editor
features            Table→Listing Feature  (child: feature Data)
photos              Table→Unit Photo
inquiries           Table→Vacancy Inquiry  (child)
listing_views       Int     read_only   default 0
```

### Vacancy Inquiry (child)

```
inquiry_date    Date        default Today
prospect_name   Data        reqd
phone           Data
email           Data
source          Select  Walk-in|Website|Broker|Referral|Bayut|PropertyFinder|Dubizzle|Other
broker_name     Data
status          Select  New|Followed Up|Viewing Scheduled|Offer Made|Converted|Lost
notes           Small Text
next_action_date Date
```

### Lease Application (standalone)

```
vacancy_listing     Link→Vacancy Listing  reqd
applicant_name      Data    reqd
applicant_type      Select  Individual|Corporate
email               Data
phone               Data
trade_licence_no    Data
desired_start_date  Date
proposed_rent       Currency
application_status  Select  Submitted|Under Review|Approved|Rejected
kyc_documents       Table→Tenant KYC Document
notes               Text
```

---
## API

```python
@frappe.whitelist()
def get_active_vacancies(property_name=None, usage_type=None):
    f = {"listing_status": "Active"}
    if property_name:
        f["property"] = property_name
    return frappe.get_all("Vacancy Listing", filters=f,
        fields=["name","unit","property","asking_rent",
                "available_from","listing_views"])

@frappe.whitelist()
def submit_inquiry(listing_name, name, phone, email, source=None):
    doc = frappe.get_doc("Vacancy Listing", listing_name)
    doc.append("inquiries", {
        "prospect_name": name, "phone": phone,
        "email": email, "source": source or "Website",
        "status": "New"
    })
    doc.listing_views = (doc.listing_views or 0) + 1
    doc.save(ignore_permissions=True)
    return {"status": "submitted"}
```

**Auto-create Vacancy Listing when unit goes Vacant:**

```python
# In hooks.py doc_events
"Property Unit": {
    "on_update": "propx.property_management.api.listing_api.auto_create_listing"
}

def auto_create_listing(doc, method):
    if doc.status == "Vacant" and not frappe.db.exists(
        "Vacancy Listing", {"unit": doc.name, "listing_status": "Active"}
    ):
        vl = frappe.new_doc("Vacancy Listing")
        vl.unit = doc.name
        vl.property = doc.property
        vl.asking_rent = doc.asking_rent_annual
        vl.available_from = frappe.utils.today()
        vl.insert(ignore_permissions=True)
```

---
## CHECKLIST M12
- [ ] Create Vacancy Listing DocType + children
- [ ] Create Lease Application DocType
- [ ] Write auto-create hook when unit goes Vacant
- [ ] Write 2 API endpoints
- [ ] Build React pipeline board for vacancies


---
---
# CLAUDE.md — M13: Platform Administration
# propx/docs/CLAUDE_M13.md

## PURPOSE
SaaS multi-tenancy, roles, white-labeling, API key management,
audit logs, app install script.

---
## MULTI-TENANCY MODEL

Small clients: shared Frappe site, Company-level data isolation.
Large clients: dedicated Frappe site (`bench new-site client.propx.com`).

Every PropX DocType has a `company` field. ERPNext enforces Company-level
row permissions if `User Permission` records are set per user.

---
## PROPX CLIENT DocType (SaaS registry)

```
client_name         Data        reqd
company             Link→Company reqd
plan                Select      Starter|Growth|Enterprise
max_units           Int
custom_domain       Data
logo                Attach Image
primary_color       Color       default #c9a84c
whatsapp_configured Check       default 0
subscription_start  Date
subscription_end    Date
is_active           Check       default 1
api_rate_limit      Int         default 1000  "API calls/hour"
```

---
## ROLES TO CREATE

```python
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
```

---
## INSTALL SCRIPT

```python
# propx/install.py

import frappe


def after_install():
    _create_roles()
    _create_default_settings()
    _add_custom_fields()
    _create_billing_items()
    frappe.db.commit()
    frappe.logger().info("PropX installed successfully.")


def _create_roles():
    for role in [
        "PropX Admin", "Property Manager", "Lease Manager",
        "Maintenance Technician", "Security Guard",
        "Property Owner", "Tenant"
    ]:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role}).insert()


def _create_default_settings():
    if frappe.db.exists("DocType", "PropX Settings"):
        settings = frappe.get_single("PropX Settings")
        if not settings.default_currency:
            settings.default_currency = "AED"
            settings.late_payment_grace_days = 5
            settings.late_fee_rate = 5
            settings.bounce_penalty_amount = 500
            settings.default_notice_period_days = 90
            settings.invoice_generation_day = 1
            settings.save()


def _add_custom_fields():
    """Apply all custom fields to ERPNext DocTypes."""
    from propx.property_management.setup.custom_fields import apply_all
    apply_all()


def _create_billing_items():
    """Create billing Items in ERPNext."""
    from propx.property_management.setup.billing_setup import create_items
    create_items()
```

---
## AUDIT LOGGING

All critical DocTypes have `track_changes = 1` set in JSON.
Use ERPNext Version DocType — it auto-tracks all field changes.

DocTypes that must have track_changes enabled:
- Lease, PDC Register, Sales Invoice, Payment Entry,
  Owner Disbursement, Property Unit, Maintenance Job Card

---
## API KEY MANAGEMENT

```python
# propx/property_management/api/admin_api.py
import frappe, secrets


@frappe.whitelist()
def generate_api_key(user):
    """Generate Frappe API key/secret for a user."""
    frappe.only_for("System Manager")
    key = frappe.generate_hash(length=15)
    secret = frappe.generate_hash(length=15)
    frappe.db.set_value("User", user, {
        "api_key": key,
        "api_secret": secret
    })
    return {"api_key": key, "api_secret": secret}
```

---
## CHECKLIST M13
- [ ] Write install.py with after_install hook
- [ ] Create PropX Client DocType
- [ ] Create 8 roles via install
- [ ] Write admin_api.py (API key generation)
- [ ] Set track_changes=1 on 6 financial DocTypes
- [ ] Test: fresh bench install → roles created, settings defaulted
- [ ] Test: two companies on same site → user only sees own company data


---
---
# CLAUDE.md — M14: Inspection Management
# propx/docs/CLAUDE_M14.md

## PURPOSE
Formal move-in / move-out inspections with photographic evidence,
room-by-room condition scoring, digital sign-off, and automated
security deposit settlement calculation.
This is a gap vs Yardi/MRI that PropX closes natively.

## DEPENDS ON
- M01: Property Unit
- M02: Lease (inspection triggers at start/end of lease)
- M03: Security deposit settlement posts to Sales Invoice / Journal Entry

---
## DOCTYPES TO BUILD (2 new + 2 children)

### DocType: Property Inspection  ← CORE

Naming: `format:INSP-{YYYY}-{#####}`
Track changes: yes

```
# === IDENTITY ===
inspection_type     Select      reqd
                    Move-In|Move-Out|Periodic|Pre-Listing|Handover
lease               Link→Lease  in_list_view
unit                Link→Property Unit  reqd, in_list_view
property            Link→Property  reqd (fetched)
tenant              Link→Customer  in_list_view
inspection_date     Date        reqd  default Today
inspector           Link→User   reqd

# === CONDITION ITEMS ===
inspection_items    Table→Inspection Item  (child — room by room)

# === OVERALL SCORE ===
overall_condition   Select      read_only
                    Excellent|Good|Fair|Poor|Unacceptable
overall_score       Float       read_only  "0-100, calculated from items"

# === DEPOSIT SETTLEMENT (Move-Out only) ===
deposit_held        Currency    read_only  (fetched from lease)
deductions          Table→Inspection Deduction  (child)
total_deductions    Currency    read_only
refund_amount       Currency    read_only  "deposit_held - total_deductions"
refund_approved     Check       default 0
refund_journal_entry Link→Journal Entry  read_only

# === SIGN-OFF ===
tenant_agreed       Check       default 0
tenant_signature    Attach      "Digital signature image or DocuSign"
manager_signature   Attach
notes               Text Editor
inspection_report   Attach      "Auto-generated PDF"

# === STATUS ===
status              Select      reqd
                    Draft|In Progress|Completed|Disputed|Closed
                    default Draft
```

---
### Inspection Item (child)

```
area                Data            reqd  in_list_view
                    "Living Room|Bedroom 1|Kitchen|Bathroom|Balcony|Common..."
item_description    Data            reqd  in_list_view  "e.g. Walls, Floor, AC Unit"
condition_move_in   Select          Good|Fair|Poor|N/A
condition_move_out  Select          Good|Fair|Poor|N/A  depends_on: type==Move-Out
change_noted        Check           default 0
before_photo        Attach Image
after_photo         Attach Image
notes               Small Text
```

---
### Inspection Deduction (child)

```
description         Data        reqd  in_list_view  "e.g. Repaint bedroom wall"
responsibility      Select      Tenant|Normal Wear|Owner  default Tenant
amount              Currency    reqd  in_list_view
invoice_ref         Link→Sales Invoice  read_only
```

---
## PYTHON CONTROLLER

```python
# propx/property_management/doctype/property_inspection/property_inspection.py

import frappe
from frappe.model.document import Document
from frappe.utils import flt


class PropertyInspection(Document):

    def validate(self):
        self._fetch_lease_defaults()
        self._calculate_overall_score()
        self._calculate_deposit_refund()

    def _fetch_lease_defaults(self):
        if not self.unit:
            return
        unit = frappe.get_doc("Property Unit", self.unit)
        self.property = unit.property
        if not self.tenant:
            self.tenant = unit.current_tenant
        if not self.lease:
            self.lease = unit.current_lease

    def _calculate_overall_score(self):
        if not self.inspection_items:
            return
        condition_map = {"Excellent": 100, "Good": 80,
                         "Fair": 50, "Poor": 20, "N/A": None}
        scores = []
        for item in self.inspection_items:
            cond = (item.condition_move_out
                    if self.inspection_type == "Move-Out"
                    else item.condition_move_in)
            s = condition_map.get(cond)
            if s is not None:
                scores.append(s)
        if scores:
            avg = sum(scores) / len(scores)
            self.overall_score = round(avg, 1)
            if avg >= 90:
                self.overall_condition = "Excellent"
            elif avg >= 70:
                self.overall_condition = "Good"
            elif avg >= 50:
                self.overall_condition = "Fair"
            elif avg >= 30:
                self.overall_condition = "Poor"
            else:
                self.overall_condition = "Unacceptable"

    def _calculate_deposit_refund(self):
        if self.inspection_type != "Move-Out":
            return
        if not self.lease:
            return
        deposit = frappe.db.get_value("Lease", self.lease, "security_deposit")
        self.deposit_held = flt(deposit)
        total_ded = sum(
            flt(d.amount)
            for d in self.deductions
            if d.responsibility == "Tenant"
        )
        self.total_deductions = total_ded
        self.refund_amount = max(0, self.deposit_held - total_ded)

    def on_submit(self):
        if self.inspection_type == "Move-Out" and self.refund_approved:
            self._post_deposit_refund()
            self._update_lease_deposit_status()

    def _post_deposit_refund(self):
        """Post Journal Entry: debit Deposits Payable, credit tenant."""
        if not self.refund_amount:
            return
        company = frappe.db.get_value("Lease", self.lease, "company")
        je = frappe.new_doc("Journal Entry")
        je.company = company
        je.posting_date = frappe.utils.today()
        je.user_remark = (
            f"Security deposit refund: {self.tenant} | "
            f"Inspection: {self.name}"
        )
        je.append("accounts", {
            "account": "Security Deposits Payable",
            "debit_in_account_currency": self.refund_amount,
            "party_type": "Customer",
            "party": self.tenant
        })
        je.append("accounts", {
            "account": frappe.db.get_value(
                "Company", company, "default_bank_account"
            ),
            "credit_in_account_currency": self.refund_amount
        })
        je.insert(ignore_permissions=True)
        je.submit()
        self.refund_journal_entry = je.name
        frappe.db.set_value("Lease", self.lease, {
            "security_deposit_status": "Refunded",
            "deposit_refund_amount": self.refund_amount
        })

    def _update_lease_deposit_status(self):
        if self.total_deductions > 0:
            frappe.db.set_value("Lease", self.lease,
                                "security_deposit_status", "Refunded")
```

---
## API

```python
# propx/property_management/api/inspection_api.py
import frappe


@frappe.whitelist()
def create_move_in_inspection(lease_name):
    """Auto-create Move-In inspection when lease activates."""
    lease = frappe.get_doc("Lease", lease_name)
    insp = frappe.new_doc("Property Inspection")
    insp.inspection_type = "Move-In"
    insp.lease = lease.name
    insp.unit = lease.unit
    insp.tenant = lease.tenant
    insp.inspection_date = lease.start_date
    insp.status = "Draft"
    insp.insert(ignore_permissions=True)
    return insp.name


@frappe.whitelist()
def get_inspection_summary(unit_name):
    return frappe.get_all("Property Inspection",
        {"unit": unit_name},
        fields=["name","inspection_type","inspection_date",
                "overall_condition","overall_score","status"],
        order_by="inspection_date desc",
        limit=10)
```

Hook `create_move_in_inspection` into Lease `on_submit`:
```python
# In lease.py on_submit:
from propx.property_management.api.inspection_api import create_move_in_inspection
create_move_in_inspection(self.name)
```

---
## INSPECTION TEMPLATES

Pre-load standard inspection templates per unit type:

```python
INSPECTION_TEMPLATES = {
    "Residential": [
        ("Living Room", ["Walls", "Floor", "Ceiling", "Lighting", "AC Unit", "Windows"]),
        ("Bedroom 1",   ["Walls", "Floor", "Wardrobe", "Lighting", "AC Unit"]),
        ("Kitchen",     ["Cabinets", "Countertop", "Sink", "Appliances", "Floor"]),
        ("Bathroom",    ["Tiles", "Fixtures", "Toilet", "Shower/Bath", "Ventilation"]),
        ("Balcony",     ["Floor", "Railing", "Drainage"]),
    ],
    "Commercial": [
        ("Main Space",  ["Floor", "Walls", "Ceiling", "Lighting", "AC"]),
        ("Pantry",      ["Fixtures", "Drainage"]),
        ("Toilets",     ["Tiles", "Fixtures"]),
        ("Exterior",    ["Signage area", "Door", "Windows"]),
    ]
}
```

---
## CHECKLIST M14
- [ ] Create Property Inspection DocType
- [ ] Create Inspection Item child DocType
- [ ] Create Inspection Deduction child DocType
- [ ] Write PropertyInspection controller (validate + on_submit)
- [ ] Write inspection_api.py (2 endpoints)
- [ ] Hook create_move_in_inspection to Lease on_submit
- [ ] Load inspection templates for Residential + Commercial
- [ ] Create "Inspection Report" print format (PDF)
- [ ] Test: activate lease → Move-In inspection auto-created
- [ ] Test: complete Move-Out with deductions → JE posts correctly
- [ ] Test: refund_amount = deposit - tenant deductions


---
---
# CLAUDE.md — M15: Parking Management
# propx/docs/CLAUDE_M15.md

## PURPOSE
Manage parking bays as standalone revenue items or unit allocations.
Monthly parking invoices, visitor parking log, EV charging tracking.

## DEPENDS ON
- M01: Property Unit

---
## DOCTYPES TO BUILD (3 new)

### DocType: Parking Bay

Naming: `format:PARK-{####}`

```
property            Link→Property   reqd
bay_number          Data            reqd, in_list_view, unique per property
bay_label           Data            "e.g. B1-045, Level 2"
level               Data            "Basement 1, Ground, Podium..."
bay_type            Select          reqd
                    Covered|Uncovered|Valet|Motorbike|EV Charging
                    in_list_view
has_ev_charger      Check           default 0
ev_charger_type     Select          Type 1|Type 2|CCS|CHAdeMO
                                    depends_on: has_ev_charger==1

# Allocation
allocated_to_unit   Link→Property Unit
allocated_to_tenant Link→Customer  (read_only, fetched from unit)
monthly_charge      Currency        default 0
currency            Link→Currency   default AED
is_for_sale         Check           default 0
sale_price          Currency        depends_on: is_for_sale==1

# Current status
status              Select          Available|Allocated to Unit|Rented Separately
                                    |Reserved|Out of Service  default Available

# Current standalone rental (if not linked to unit)
current_parking_lease Link→Parking Lease  read_only
```

---
### DocType: Parking Lease (standalone parking rental)

Naming: `format:PLSE-{####}`

```
bay                 Link→Parking Bay   reqd
tenant              Link→Customer      reqd
start_date          Date               reqd
end_date            Date               reqd
monthly_charge      Currency           reqd
currency            Link→Currency      default AED
status              Select             Active|Terminated|Expired  default Active
auto_renew          Check              default 1
invoice_day         Int                default 1
notes               Data
```

---
### DocType: Visitor Parking Log

```
property            Link→Property   reqd
bay                 Link→Parking Bay
vehicle_plate       Data            reqd, in_list_view
visitor_name        Data
host_unit           Link→Property Unit
check_in            Datetime        reqd  default Now
check_out           Datetime
duration_hours      Float           read_only
charge_applicable   Check           default 0
amount              Currency        depends_on: charge_applicable==1
```

---
## PYTHON CONTROLLER

```python
# propx/property_management/doctype/parking_bay/parking_bay.py

class ParkingBay(Document):
    def validate(self):
        # Fetch tenant from allocated unit
        if self.allocated_to_unit:
            tenant = frappe.db.get_value(
                "Property Unit", self.allocated_to_unit, "current_tenant"
            )
            self.allocated_to_tenant = tenant
            self.status = "Allocated to Unit"
        elif self.current_parking_lease:
            self.status = "Rented Separately"
        else:
            self.status = "Available"
```

```python
# Monthly parking invoice generation (add to billing_utils.py)
def generate_parking_invoices():
    """Monthly: invoice standalone parking leases."""
    active = frappe.get_all("Parking Lease",
        {"status": "Active"},
        fields=["name","bay","tenant","monthly_charge","currency"])
    for pl in active:
        si = frappe.new_doc("Sales Invoice")
        si.customer = pl.tenant
        si.propx_invoice_type = "Parking"
        si.due_date = frappe.utils.today()
        si.append("items", {
            "item_code": "PARKING-FEE",
            "qty": 1,
            "rate": pl.monthly_charge,
            "description": f"Parking bay — {pl.bay}"
        })
        si.insert(ignore_permissions=True)
```

---
## API

```python
@frappe.whitelist()
def get_parking_summary(property_name):
    return {
        "total_bays": frappe.db.count("Parking Bay", {"property": property_name}),
        "available": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Available"}),
        "allocated": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Allocated to Unit"}),
        "standalone": frappe.db.count("Parking Bay",
            {"property": property_name, "status": "Rented Separately"}),
        "ev_bays": frappe.db.count("Parking Bay",
            {"property": property_name, "has_ev_charger": 1}),
    }


@frappe.whitelist()
def get_available_bays(property_name, bay_type=None):
    f = {"property": property_name, "status": "Available"}
    if bay_type:
        f["bay_type"] = bay_type
    return frappe.get_all("Parking Bay", filters=f,
        fields=["name","bay_number","bay_label","level",
                "bay_type","has_ev_charger","monthly_charge"])
```

---
## CHECKLIST M15
- [ ] Create Parking Bay DocType
- [ ] Create Parking Lease DocType
- [ ] Create Visitor Parking Log DocType
- [ ] Create PARKING-FEE item in ERPNext
- [ ] Write ParkingBay controller (status auto-set)
- [ ] Add generate_parking_invoices to monthly scheduler
- [ ] Write parking_api.py (get_summary, get_available_bays)
- [ ] Test: allocate bay to unit → tenant auto-filled, status = Allocated
- [ ] Test: standalone parking lease → monthly invoice auto-created
- [ ] Test: bay goes Available → appears in get_available_bays
