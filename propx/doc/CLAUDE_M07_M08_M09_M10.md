# CLAUDE.md — M07: Utility & Meter Management
# propx/docs/CLAUDE_M07.md

## PURPOSE
Track electricity, water, gas, district cooling meters per unit.
Manual and IoT readings, consumption billing to tenants,
DEWA/SEWA/OMAS authority account management.

---
## DOCTYPES TO BUILD (2 new + 1 child)

### DocType: Utility Meter

Naming: `format:MTR-{####}`

```
property            Link→Property   reqd
unit                Link→Property Unit
meter_number        Data            reqd, in_list_view, unique
utility_type        Select          reqd
                    Electricity|Water|Gas|District Cooling|Internet
authority           Select          DEWA|SEWA|ADDC|AADC|OMAS|FEWA|Other
authority_account   Data            in_list_view
tariff_per_unit     Currency        reqd   "Rate per kWh/litre/m3"
currency            Link→Currency   default AED
billing_mode        Select          reqd
                    Charge to Tenant|Included in Rent|Charge to Owner
                    default Charge to Tenant
is_smart_meter      Check           default 0
iot_device_id       Data            depends_on: is_smart_meter
last_reading        Float           read_only
last_reading_date   Date            read_only
status              Select          Active|Disconnected|Replaced  default Active
```

---
### DocType: Meter Reading

Naming: `format:MRD-{YYYY}{MM}-{####}`

```
meter               Link→Utility Meter  reqd, in_list_view
property            Link→Property       read_only (fetched)
unit                Link→Property Unit  read_only (fetched)
reading_date        Date                reqd  default Today, in_list_view
previous_reading    Float               read_only (from last entry)
current_reading     Float               reqd, in_list_view
consumption         Float               read_only  "current - previous"
unit_of_measure     Data                read_only (from meter)
amount_due          Currency            read_only  "consumption × tariff"
reading_type        Select              Manual|IoT|Estimated  default Manual
reading_image       Attach Image
invoice             Link→Sales Invoice  read_only "auto-created on submit"
```

**Controller:**
```python
class MeterReading(Document):
    def validate(self):
        if not self.previous_reading:
            # Get last reading for this meter
            last = frappe.get_all("Meter Reading",
                filters={"meter": self.meter,
                         "docstatus": 1,
                         "name": ["!=", self.name or "__new__"]},
                fields=["current_reading"],
                order_by="reading_date desc",
                limit=1
            )
            self.previous_reading = last[0].current_reading if last else 0

        meter = frappe.get_doc("Utility Meter", self.meter)
        self.consumption = max(
            0, float(self.current_reading) - float(self.previous_reading)
        )
        self.amount_due = round(
            self.consumption * float(meter.tariff_per_unit), 2
        )
        self.property = meter.property
        self.unit = meter.unit

    def on_submit(self):
        # Update last reading on meter
        frappe.db.set_value("Utility Meter", self.meter, {
            "last_reading": self.current_reading,
            "last_reading_date": self.reading_date
        })
        # Create invoice if billing mode is Charge to Tenant
        if self.amount_due > 0:
            self._create_utility_invoice()

    def _create_utility_invoice(self):
        meter = frappe.get_doc("Utility Meter", self.meter)
        if meter.billing_mode != "Charge to Tenant":
            return
        tenant = frappe.db.get_value(
            "Property Unit", self.unit, "current_tenant"
        )
        if not tenant:
            return
        item_map = {"Electricity": "UTIL-ELEC", "Water": "UTIL-WATER"}
        item_code = item_map.get(meter.utility_type, "SVC-CHARGE")

        si = frappe.new_doc("Sales Invoice")
        si.customer = tenant
        si.propx_unit = self.unit
        si.propx_property = self.property
        si.propx_invoice_type = "Utility"
        si.due_date = frappe.utils.today()
        si.append("items", {
            "item_code": item_code,
            "qty": self.consumption,
            "rate": meter.tariff_per_unit,
            "description": (f"{meter.utility_type} — {meter.meter_number} | "
                            f"{self.reading_date}")
        })
        si.insert(ignore_permissions=True)
        self.invoice = si.name
```

---
## API ENDPOINT

```python
@frappe.whitelist()
def get_utility_summary(property_name, from_date, to_date):
    return frappe.db.sql("""
        SELECT m.utility_type, m.unit, m.authority, m.tariff_per_unit,
               SUM(mr.consumption) as total_consumption,
               SUM(mr.amount_due) as total_billed
        FROM `tabMeter Reading` mr
        JOIN `tabUtility Meter` m ON m.name = mr.meter
        WHERE m.property=%(p)s
          AND mr.reading_date BETWEEN %(f)s AND %(t)s
          AND mr.docstatus=1
        GROUP BY m.name
    """, {"p": property_name, "f": from_date, "t": to_date}, as_dict=True)
```

---
## CHECKLIST M07
- [ ] Create Utility Meter DocType
- [ ] Create Meter Reading DocType
- [ ] Write MeterReading controller (validate + on_submit)
- [ ] Write get_utility_summary API
- [ ] Test: submit reading → consumption invoice created for tenant


---
---
# CLAUDE.md — M08: Security & Access Management
# propx/docs/CLAUDE_M08.md

## PURPOSE
Guard shift management, visitor log, vehicle entry, key management,
incident reporting, and mobile guard app API.
Partially based on Frappe HR (Employee for guards).

---
## DOCTYPES TO BUILD (4 new)

### DocType: Guard Shift

```
property            Link→Property   reqd
shift_date          Date            reqd  default Today
shift_type          Select          Morning|Afternoon|Night|24hr
shift_start         Time            reqd
shift_end           Time            reqd
guards              Table→Guard Shift Assignment  (child)
handover_notes      Text
```

Guard Shift Assignment (child):
```
employee        Link→Employee   reqd, in_list_view
post            Data            "Main Gate|Lobby|Parking|Patrol"
check_in_time   Time
check_out_time  Time
status          Select          Scheduled|On Duty|Absent|Left Early
```

---
### DocType: Visitor Log

Naming: `format:VIS-{YYYYMMDD}-{###}`

```
property            Link→Property   reqd
visitor_name        Data            reqd, in_list_view
id_type             Select          Emirates ID|Passport|DL|Other
id_number           Data
host_unit           Link→Property Unit  in_list_view
host_tenant         Link→Customer
visit_purpose       Select
                    Personal Guest|Business|Delivery|Maintenance Vendor
                    |Inspection|Government|Other
vehicle_plate       Data
check_in            Datetime        reqd  default Now, in_list_view
check_out           Datetime
guard_on_duty       Link→Employee
pre_approved        Check           default 0
status              Select
                    On Premises|Left|Denied Entry  default On Premises
                    in_list_view
notes               Small Text
```

---
### DocType: Security Incident

Naming: `format:INC-{YYYY}-{###}`

```
property            Link→Property   reqd
incident_datetime   Datetime        reqd
incident_type       Select
                    Trespass|Theft|Vandalism|Fire|Medical
                    |Noise Complaint|Unauthorised Access|Other
location_detail     Data
description         Text Editor     reqd
reported_by         Link→Employee
tenants_involved    Table→Incident Tenant (child)
status              Select          Open|Under Investigation|Resolved|Closed
police_report_no    Data
resolution          Text
photos              Table→Maintenance Photo
```

---
### DocType: Key Register

```
property            Link→Property   reqd
unit                Link→Property Unit
key_type            Select          Unit Key|Master Key|Parking|Post Box|Other
key_number          Data            reqd, unique per property
total_copies        Int             default 2
current_holder      Link→Customer   "Tenant holding key"
issued_date         Date
returned_date       Date
status              Select          Available|Issued|Lost|Damaged
                    default Available
notes               Small Text
```

---
## API ENDPOINTS

```python
# propx/property_management/api/security_api.py
import frappe
from frappe.utils import today, now_datetime


@frappe.whitelist()
def get_security_kpis(property_name=None):
    f = {}
    if property_name:
        f["property"] = property_name
    return {
        "guards_on_duty": frappe.db.count("Guard Shift Assignment", {
            "status": "On Duty"
        }),
        "visitors_today": frappe.db.count("Visitor Log", {
            **f,
            "check_in": [">=", today()]
        }),
        "on_premises": frappe.db.count("Visitor Log", {
            **f, "status": "On Premises"
        }),
        "open_incidents": frappe.db.count("Security Incident", {
            **f, "status": ["in", ["Open", "Under Investigation"]]
        })
    }


@frappe.whitelist()
def log_visitor_in(property_name, visitor_name, host_unit=None,
                    id_type=None, id_number=None,
                    vehicle_plate=None, purpose=None):
    doc = frappe.new_doc("Visitor Log")
    doc.property = property_name
    doc.visitor_name = visitor_name
    doc.host_unit = host_unit
    doc.id_type = id_type
    doc.id_number = id_number
    doc.vehicle_plate = vehicle_plate
    doc.visit_purpose = purpose
    doc.check_in = now_datetime()
    doc.status = "On Premises"
    doc.insert(ignore_permissions=True)
    return doc.name


@frappe.whitelist()
def log_visitor_out(visitor_log_name):
    frappe.db.set_value("Visitor Log", visitor_log_name, {
        "check_out": now_datetime(), "status": "Left"
    })
    return {"status": "checked_out"}
```

---
## CHECKLIST M08
- [ ] Create Guard Shift + child DocType
- [ ] Create Visitor Log DocType
- [ ] Create Security Incident DocType
- [ ] Create Key Register DocType
- [ ] Write security_api.py (4 endpoints)
- [ ] Test: log visitor in → on_premises count increments
- [ ] Test: log visitor out → status = Left, check_out set


---
---
# CLAUDE.md — M09: Tenant Self-Service Portal
# propx/docs/CLAUDE_M09.md

## PURPOSE
React web portal + React Native mobile app for tenants.
All data from Frappe REST API.

## TECH STACK
```
Web:    React 18 + Vite + TanStack Query + React Router v6
Mobile: React Native + Expo SDK 51 + React Navigation 6
Auth:   Frappe /api/method/login → session cookie (web) / token (mobile)
i18n:   react-i18next → English + Arabic RTL
Fonts:  IBM Plex Sans + IBM Plex Mono (clean, bilingual-friendly)
Theme:  Dark navy (#05080f) + gold (#c9a84c) matching PropX brand
```

## SCREENS

### React Web
```
/login                  Email + password
/dashboard              Lease summary, outstanding, next PDC, open tickets
/lease/:id              Lease detail, terms, PDC schedule, documents
/invoices               Invoice list, download PDF
/maintenance            My requests list
/maintenance/new        Submit request (category, description, photo)
/maintenance/:id        Ticket status + updates
/documents              Download contracts, receipts
/profile                Profile + KYC + language preference
```

### React Native
```
Tab 1 - Home            Dashboard cards (rent due, open requests, notices)
Tab 2 - Maintenance     List + new request with camera
Tab 3 - Payments        Invoice history + pay online (Phase 2 payment gateway)
Tab 4 - Documents       Download receipts and contracts
Tab 5 - Profile         Settings, language toggle, logout
```

---
## FRAPPE API INTEGRATION

```javascript
// src/api/client.js
const BASE = import.meta.env.VITE_FRAPPE_URL;

export async function call(method, params = {}) {
  const r = await fetch(`${BASE}/api/method/${method}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Frappe-CSRF-Token": window.csrf_token || "fetch",
    },
    credentials: "include",
    body: JSON.stringify(params),
  });
  const d = await r.json();
  if (d.exc) throw new Error(d.message || d.exc);
  return d.message;
}

export const tenantAPI = {
  dashboard: (tenant) =>
    call("propx.property_management.api.tenant_portal_api.get_tenant_dashboard",
         { tenant }),
  submitRequest: (data) =>
    call("propx.property_management.api.maintenance_api.submit_tenant_request",
         data),
  getInvoices: (customer) =>
    call("frappe.client.get_list", {
      doctype: "Sales Invoice",
      filters: { customer, docstatus: 1 },
      fields: ["name","posting_date","grand_total","status","outstanding_amount"],
      order_by: "posting_date desc"
    }),
};
```

---
## BACKEND API FOR TENANT PORTAL

```python
# propx/property_management/api/tenant_portal_api.py
import frappe


@frappe.whitelist()
def get_tenant_dashboard(tenant):
    leases = frappe.get_all("Lease",
        {"tenant": tenant, "status": ["in", ["Active","Expiring"]]},
        fields=["name","unit","property","start_date","end_date",
                "annual_rent","monthly_rent","currency"])

    outstanding = frappe.db.sql("""
        SELECT SUM(outstanding_amount) FROM `tabSales Invoice`
        WHERE customer=%s AND docstatus=1 AND outstanding_amount>0
    """, tenant)[0][0] or 0

    next_pdc = frappe.get_all("PDC Register",
        {"tenant": tenant, "status": "Received"},
        fields=["cheque_number","cheque_date","amount","bank_name"],
        order_by="cheque_date asc", limit=1)

    unit_names = [l.unit for l in leases]
    open_tickets = 0
    if unit_names:
        open_tickets = frappe.db.count("Maintenance Job Card", {
            "unit": ["in", unit_names],
            "reported_by_tenant": 1,
            "ticket_status": ["not in", ["Closed","Cancelled"]]
        })

    return {
        "leases": leases,
        "outstanding_amount": outstanding,
        "next_pdc": next_pdc[0] if next_pdc else None,
        "open_maintenance_tickets": open_tickets
    }
```

---
## ARABIC RTL SETUP

```javascript
// src/i18n/index.js
import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import ar from "./locales/ar.json";

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: localStorage.getItem("propx_lang") || "en",
  fallbackLng: "en",
});

// In App.jsx
document.documentElement.dir = i18n.language === "ar" ? "rtl" : "ltr";
document.documentElement.lang = i18n.language;
```

---
## CHECKLIST M09
- [ ] Scaffold React web app (Vite + React 18)
- [ ] Scaffold React Native app (Expo)
- [ ] Implement Frappe session auth (login/logout)
- [ ] Build tenant dashboard (web + mobile)
- [ ] Build lease detail screen
- [ ] Build invoice list + PDF download
- [ ] Build maintenance request form with photo upload
- [ ] Build documents screen
- [ ] Implement Arabic RTL toggle
- [ ] Write tenant_portal_api.py get_tenant_dashboard
- [ ] Test: tenant logs in → sees their lease and balance
- [ ] Test: submit maintenance request → WO appears in M06 kanban


---
---
# CLAUDE.md — M10: Owner & Investor Portal
# propx/docs/CLAUDE_M10.md

## PURPOSE
React web portal for property owners. Read-only view of portfolio P&L,
per-property performance, owner statements, disbursement history.
Role: Property Owner (linked to Customer record).

## SCREENS

```
/owner/login            Same Frappe login as PropX
/owner/dashboard        Portfolio KPIs (NOI, yield, occupancy)
/owner/properties       Per-property revenue + occupancy table
/owner/statements       Monthly statements list
/owner/statement/:id    Statement detail: income/expenses/net disbursement
/owner/disbursements    Disbursement history (paid/pending/upcoming)
```

## ACCESS CONTROL
- Owner user role: `Property Owner`
- Owner's ERPNext User is linked to a Customer record
- All queries filter by `owner = current_customer`
- Route guard in React: redirect to /owner/login if not Property Owner role

---
## API ENDPOINTS

```python
# propx/property_management/api/owner_api.py
import frappe
from frappe.utils import today, get_first_day


def _get_owner_for_user():
    """Get Customer linked to current user (owner)."""
    return frappe.db.get_value(
        "Customer", {"email_id": frappe.session.user}, "name"
    )


@frappe.whitelist()
def get_owner_dashboard():
    owner = _get_owner_for_user()
    if not owner:
        frappe.throw("No owner profile linked to this account.")

    props = frappe.get_all("Property", {"owner": owner},
                            fields=["name","property_name",
                                    "property_category","total_units",
                                    "occupied_units","occupancy_pct"])
    prop_names = [p.name for p in props]

    monthly_rev = frappe.db.sql("""
        SELECT SUM(grand_total - outstanding_amount)
        FROM `tabSales Invoice`
        WHERE propx_property IN %(props)s
          AND docstatus=1
          AND posting_date >= %(ms)s
    """, {"props": prop_names,
          "ms": get_first_day(today())})[0][0] or 0

    recent_disb = frappe.get_all("Owner Disbursement",
        {"owner": owner},
        fields=["name","period_from","period_to",
                "gross_rent","net_disbursement","status"],
        order_by="period_from desc", limit=6)

    total_units = sum(p.total_units or 0 for p in props)
    occ_units = sum(p.occupied_units or 0 for p in props)

    return {
        "properties": props,
        "monthly_revenue": monthly_rev,
        "occupancy_pct": (round(occ_units / total_units * 100, 1)
                          if total_units else 0),
        "recent_disbursements": recent_disb
    }


@frappe.whitelist()
def get_property_performance():
    owner = _get_owner_for_user()
    props = frappe.get_all("Property", {"owner": owner},
                            fields=["name","property_name",
                                    "property_category","total_units",
                                    "occupied_units","occupancy_pct"])
    result = []
    ms = get_first_day(today())
    for p in props:
        rev = frappe.db.sql("""
            SELECT SUM(grand_total - outstanding_amount)
            FROM `tabSales Invoice`
            WHERE propx_property=%s AND docstatus=1 AND posting_date>=%s
        """, (p.name, ms))[0][0] or 0
        result.append({**p, "monthly_revenue": rev})
    return result


@frappe.whitelist()
def get_owner_statements():
    owner = _get_owner_for_user()
    return frappe.get_all("Owner Disbursement",
        {"owner": owner},
        fields=["name","period_from","period_to","gross_rent",
                "management_fee","net_disbursement","status",
                "payment_date","statement_pdf"],
        order_by="period_from desc")
```

---
## CHECKLIST M10
- [ ] Build owner login + route guard
- [ ] Build owner dashboard screen
- [ ] Build per-property performance table
- [ ] Build statements list + detail view
- [ ] Write owner_api.py (3 endpoints, scoped to current user's owner)
- [ ] Test: owner logs in → only sees their properties
- [ ] Test: statement detail shows correct income/expense breakdown
