# CLAUDE.md — M03: Billing, Revenue & PDC Management
# propx/docs/CLAUDE_M03.md

## PURPOSE
Financial engine: automated rent invoicing, PDC cheque lifecycle
(Received → Deposited → Cleared / Bounced), late fee automation,
service charge reconciliation, security deposit settlement,
and vendor procurement linkage. All posting flows through ERPNext GL.

## DEPENDS ON
- M01: Property Unit, M02: Lease
- ERPNext: Sales Invoice, Payment Entry, Purchase Order, Journal Entry

## REUSE FROM ERPNext (zero new DocTypes for these)
- `Sales Invoice`   → ALL rent invoices. Add custom fields for propx linkage.
- `Payment Entry`   → ALL receipts (PDC clear, cash). Created auto on clear.
- `Purchase Order`  → Vendor work orders. Link from Maintenance Job Card (M06).
- `Journal Entry`   → Security deposit hold / release.

---
## ERPNext ITEMS TO CREATE (run once as fixture)

```python
BILLING_ITEMS = [
    # item_code, item_name, income_account, is_vat_taxable
    ("RENT-RES",    "Residential Rent",     "Rental Income - Residential", False),
    ("RENT-COM",    "Commercial Rent",      "Rental Income - Commercial",  True),
    ("RENT-IND",    "Industrial Rent",      "Rental Income - Industrial",  True),
    ("RENT-STR",    "Short-Term Rent",      "Rental Income - Short-Term",  True),
    ("SVC-CHARGE",  "Service Charge",       "Service Charge Income",       True),
    ("PARKING-FEE", "Parking Fee",          "Parking Income",              True),
    ("LATE-FEE",    "Late Payment Penalty", "Other Income",                False),
    ("BOUNCE-FEE",  "Cheque Bounce Penalty","Other Income",                False),
    ("SEC-DEPOSIT", "Security Deposit",     "Security Deposits Payable",   False),
    ("UTIL-ELEC",   "Electricity Charge",   "Utility Recovery Income",     True),
    ("UTIL-WATER",  "Water Charge",         "Utility Recovery Income",     True),
]
```

---
## CUSTOM FIELDS ON SALES INVOICE (add via fixture)

```python
SI_CUSTOM_FIELDS = [
    # fieldname, label, fieldtype, options
    ("propx_lease",   "Lease",          "Link", "Lease"),
    ("propx_unit",    "Property Unit",  "Link", "Property Unit"),
    ("propx_property","Property",       "Link", "Property"),
    ("propx_billing_month", "Billing Month", "Date", None),
    ("propx_invoice_type",  "Invoice Type",
     "Select", "Rent|Service Charge|Utility|Late Fee|Bounce Penalty|Deposit"),
]
```

---
## DOCTYPES TO BUILD (2 new)

### DocType 1: PDC Register  ← CRITICAL

Naming: `format:PDC-{YYYY}-{#####}`
Title field: `cheque_number`
Track changes: yes

```
# === CHEQUE IDENTITY ===
cheque_number       Data        reqd, in_list_view
bank_name           Data        reqd, in_list_view
account_number      Data
bank_branch         Data
iban                Data

# === AMOUNT ===
amount              Currency    reqd, in_list_view
currency            Link→Currency  default AED

# === DATES ===
cheque_date         Date        reqd, in_list_view  "Due / presentation date"
received_date       Date        reqd  default Today
deposited_date      Date
cleared_date        Date
bounce_date         Date

# === LINKS ===
tenant              Link→Customer    reqd, in_list_view
lease               Link→Lease       reqd
property            Link→Property    (fetched)
unit                Link→Property Unit (fetched)
against_invoice     Link→Sales Invoice
period_from         Date
period_to           Date

# === STATUS ===
status              Select      reqd
                    Received|Deposited|Cleared|Bounced|Replaced|Cancelled
                    default Received, in_list_view
bounce_reason       Select
                    Insufficient Funds|Account Closed|Signature Mismatch
                    |Stale Cheque|Payment Stopped|Other
                    depends_on: status==Bounced
replacement_pdc     Link→PDC Register  depends_on: status==Bounced

# === RISK FLAGS ===
bounce_risk         Check           default 0, in_list_view
bounce_risk_reason  Small Text      depends_on: bounce_risk==1
previous_bounces    Int             default 0, read_only

# === ACCOUNTING LINKS ===
payment_entry       Link→Payment Entry  read_only "Auto on clear"
deposit_batch       Link→PDC Deposit Batch
journal_entry_bounce Link→Journal Entry  "Bounce reversal JE"

remarks             Small Text
```

**Permissions:** Property Manager CRUD, Accountant CRUD, Lease Manager Read

---
### DocType 2: PDC Deposit Batch

Naming: `format:DBATCH-{YYYY}{MM}-{###}`

```
batch_date          Date        reqd  default Today
bank_account        Link→Bank Account  reqd
cheques             Table→PDC Deposit Batch Cheque  (child)
total_cheques       Int         read_only
total_amount        Currency    read_only
status              Select      Draft|Submitted to Bank|Partly Cleared|Fully Cleared
                                default Draft
deposit_slip_pdf    Attach
notes               Small Text
```

**PDC Deposit Batch Cheque** (child istable):
```
pdc_register    Link→PDC Register   reqd, in_list_view
cheque_number   Data                read_only (fetched)
bank_name       Data                read_only
amount          Currency            read_only
cheque_date     Date                read_only
status          Data                read_only
```

---
## PDC REGISTER CONTROLLER

```python
# propx/property_management/doctype/pdc_register/pdc_register.py

import frappe
from frappe.model.document import Document
from frappe.utils import today, flt, getdate


class PDCRegister(Document):

    def validate(self):
        self._fetch_property_from_lease()
        self._check_bounce_history()

    def _fetch_property_from_lease(self):
        if self.lease and not self.property:
            d = frappe.db.get_value(
                "Lease", self.lease, ["property", "unit"], as_dict=True
            )
            if d:
                self.property = d.property
                self.unit = d.unit

    def _check_bounce_history(self):
        if not self.tenant:
            return
        bounces = frappe.db.count("PDC Register", {
            "tenant": self.tenant,
            "status": "Bounced",
            "name": ["!=", self.name or "__new__"]
        })
        self.previous_bounces = bounces
        if bounces >= 2:
            self.bounce_risk = 1
            self.bounce_risk_reason = (
                f"Tenant has {bounces} previous bounced cheques"
            )

    # ── LIFECYCLE METHODS ─────────────────────────────────────────

    @frappe.whitelist()
    def deposit(self, deposited_date=None):
        self.status = "Deposited"
        self.deposited_date = deposited_date or today()
        self.save()

    @frappe.whitelist()
    def clear(self, cleared_date=None):
        """Mark cleared → auto-create Payment Entry → reconcile invoice."""
        self.status = "Cleared"
        self.cleared_date = cleared_date or today()
        pe_name = self._create_payment_entry()
        self.payment_entry = pe_name
        self.save()
        return pe_name

    def _create_payment_entry(self):
        if not self.against_invoice:
            frappe.throw(
                "Cannot create Payment Entry: no Sales Invoice linked to this PDC."
            )
        inv = frappe.get_doc("Sales Invoice", self.against_invoice)
        company = inv.company
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = self.tenant
        pe.company = company
        pe.paid_amount = self.amount
        pe.received_amount = self.amount
        pe.source_exchange_rate = 1
        pe.target_exchange_rate = 1
        pe.reference_no = self.cheque_number
        pe.reference_date = self.cleared_date
        pe.remarks = f"PDC clearance: {self.name} | Cheque: {self.cheque_number}"
        pe.mode_of_payment = "Cheque"
        bank_account = frappe.db.get_value(
            "Company", company, "default_bank_account"
        )
        pe.paid_to = bank_account
        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": self.against_invoice,
            "allocated_amount": self.amount
        })
        pe.insert(ignore_permissions=True)
        pe.submit()
        return pe.name

    @frappe.whitelist()
    def bounce(self, bounce_date=None, reason=None):
        self.status = "Bounced"
        self.bounce_date = bounce_date or today()
        if reason:
            self.bounce_reason = reason
        self.save()
        self._create_bounce_penalty_invoice()
        self._notify_bounce()

    def _create_bounce_penalty_invoice(self):
        settings = frappe.get_single("PropX Settings")
        penalty = flt(settings.bounce_penalty_amount or 500)
        company = frappe.db.get_value(
            "Lease", self.lease, "company"
        ) if self.lease else frappe.defaults.get_global_default("company")

        si = frappe.new_doc("Sales Invoice")
        si.customer = self.tenant
        si.company = company
        si.propx_lease = self.lease
        si.propx_unit = self.unit
        si.propx_invoice_type = "Bounce Penalty"
        si.due_date = today()
        si.append("items", {
            "item_code": "BOUNCE-FEE",
            "qty": 1,
            "rate": penalty,
            "description": f"Cheque bounce penalty — {self.cheque_number}"
        })
        si.insert(ignore_permissions=True)
        return si.name

    def _notify_bounce(self):
        frappe.publish_realtime("pdc_bounced", {
            "pdc": self.name,
            "tenant": self.tenant,
            "amount": self.amount,
            "cheque": self.cheque_number
        })
```

---
## BILLING UTILITIES

```python
# propx/property_management/utils/billing_utils.py

import frappe
from frappe.utils import today, getdate, get_first_day, flt, add_days
from datetime import date


def generate_monthly_invoices():
    """
    Run on 1st of each month via scheduler.
    Creates Sales Invoices for all active leases due for billing.
    """
    active_leases = frappe.get_all(
        "Lease",
        filters={"status": ["in", ["Active", "Expiring"]]},
        fields=["name", "tenant", "unit", "property", "annual_rent",
                "monthly_rent", "currency", "is_vat_applicable",
                "vat_rate", "service_charge_monthly",
                "start_date", "end_date", "company"]
    )
    created = []
    for lease in active_leases:
        if _is_within_term(lease):
            inv = _create_rent_invoice(lease)
            if inv:
                created.append(inv)
    return created


def _is_within_term(lease):
    t = getdate(today())
    return getdate(lease.start_date) <= t <= getdate(lease.end_date)


def _create_rent_invoice(lease):
    t = getdate(today())
    month_start = date(t.year, t.month, 1)

    existing = frappe.db.exists("Sales Invoice", {
        "propx_lease": lease.name,
        "propx_billing_month": str(month_start),
        "docstatus": ["!=", 2]
    })
    if existing:
        return None

    unit_type = frappe.db.get_value(
        "Property Unit", lease.unit, "usage_type"
    )
    item_map = {
        "Residential": "RENT-RES",
        "Commercial":  "RENT-COM",
        "Industrial":  "RENT-IND",
        "Short-Term Rental": "RENT-STR",
    }
    item_code = item_map.get(unit_type, "RENT-COM")

    cost_centre = frappe.db.get_value(
        "Property", lease.property, "cost_centre"
    )
    si = frappe.new_doc("Sales Invoice")
    si.customer = lease.tenant
    si.company = lease.company
    si.currency = lease.currency or "AED"
    si.due_date = str(month_start)
    si.cost_center = cost_centre
    si.propx_lease = lease.name
    si.propx_unit = lease.unit
    si.propx_property = lease.property
    si.propx_billing_month = str(month_start)
    si.propx_invoice_type = "Rent"

    si.append("items", {
        "item_code": item_code,
        "qty": 1,
        "rate": flt(lease.monthly_rent),
        "description": (f"Rent: {lease.unit} | "
                        f"{month_start.strftime('%B %Y')}")
    })

    # Service charge line (if applicable)
    if flt(lease.service_charge_monthly) > 0:
        si.append("items", {
            "item_code": "SVC-CHARGE",
            "qty": 1,
            "rate": flt(lease.service_charge_monthly),
            "description": f"Service charge: {month_start.strftime('%B %Y')}"
        })

    # VAT
    if lease.is_vat_applicable and flt(lease.vat_rate) > 0:
        vat_account = _get_vat_account(lease.company, lease.property)
        si.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": vat_account,
            "description": f"VAT @ {lease.vat_rate}%",
            "rate": flt(lease.vat_rate)
        })

    si.insert(ignore_permissions=True)
    return si.name


def _get_vat_account(company, property_name):
    country = frappe.db.get_value("Property", property_name, "country")
    account_map = {
        "United Arab Emirates": "VAT Payable - FTA",
        "Saudi Arabia":         "VAT Payable - GAZT",
        "Oman":                 "VAT Payable - OTA",
    }
    return account_map.get(country, "VAT Payable - FTA")


def apply_late_fees():
    """
    Daily: charge late payment fee on unpaid invoices past grace period.
    """
    settings = frappe.get_single("PropX Settings")
    grace_days = int(settings.late_payment_grace_days or 5)
    cutoff = add_days(today(), -grace_days)

    overdue = frappe.db.sql("""
        SELECT si.name, si.customer, si.propx_lease,
               si.propx_unit, si.propx_property, si.outstanding_amount,
               si.company
        FROM `tabSales Invoice` si
        WHERE si.docstatus = 1
          AND si.outstanding_amount > 0
          AND si.due_date < %(cutoff)s
          AND si.propx_invoice_type = 'Rent'
          AND si.propx_lease IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM `tabSales Invoice` lf
              WHERE lf.propx_lease = si.propx_lease
                AND lf.propx_invoice_type = 'Late Fee'
                AND lf.propx_billing_month = si.propx_billing_month
                AND lf.docstatus != 2
          )
    """, {"cutoff": cutoff}, as_dict=True)

    for inv in overdue:
        fee_rate = flt(settings.late_fee_rate or 0.05)
        fee_amount = round(flt(inv.outstanding_amount) * fee_rate, 2)
        if fee_amount < 50:
            continue  # minimum threshold
        lf = frappe.new_doc("Sales Invoice")
        lf.customer = inv.customer
        lf.company = inv.company
        lf.propx_lease = inv.propx_lease
        lf.propx_unit = inv.propx_unit
        lf.propx_property = inv.propx_property
        lf.propx_invoice_type = "Late Fee"
        lf.due_date = today()
        lf.append("items", {
            "item_code": "LATE-FEE",
            "qty": 1,
            "rate": fee_amount,
            "description": f"Late payment penalty — Invoice {inv.name}"
        })
        lf.insert(ignore_permissions=True)


def create_pdc_entries(lease):
    """
    Called via enqueue from Lease.on_submit.
    Creates PDC Register records from lease.pdc_schedule.
    """
    lease_doc = frappe.get_doc("Lease", lease)
    for row in lease_doc.pdc_schedule:
        if row.cheque_status == "Pending" and not row.pdc_register_ref:
            pdc = frappe.new_doc("PDC Register")
            pdc.tenant = lease_doc.tenant
            pdc.lease = lease_doc.name
            pdc.property = lease_doc.property
            pdc.unit = lease_doc.unit
            pdc.amount = row.amount
            pdc.cheque_date = row.due_date
            pdc.period_from = row.period_from
            pdc.period_to = row.period_to
            pdc.status = "Received"
            pdc.insert(ignore_permissions=True)
            frappe.db.set_value(
                "PDC Cheque Row", row.name,
                "pdc_register_ref", pdc.name
            )
    frappe.db.commit()
```

---
## SERVICE CHARGE RECONCILIATION

```python
# propx/property_management/utils/service_charge_utils.py

import frappe
from frappe.utils import flt


@frappe.whitelist()
def reconcile_service_charge(property_name, year):
    """
    Annual CAM/service charge reconciliation for a property.
    Compares actual costs vs estimated charges billed.
    Generates adjustment invoices or credit notes.
    """
    # Get all active commercial leases for this property this year
    leases = frappe.db.sql("""
        SELECT l.name, l.tenant, l.unit, l.area_sqft_at_signing,
               l.service_charge_monthly,
               SUM(si.grand_total) as billed_svc_charge
        FROM `tabLease` l
        LEFT JOIN `tabSales Invoice` si
            ON si.propx_lease = l.name
            AND si.propx_invoice_type = 'Service Charge'
            AND YEAR(si.posting_date) = %(year)s
            AND si.docstatus = 1
        WHERE l.property = %(prop)s
          AND l.status IN ('Active','Expiring','Terminated')
          AND l.lease_category = 'Commercial'
        GROUP BY l.name
    """, {"prop": property_name, "year": year}, as_dict=True)

    # Get actual property costs for the year
    actual_costs = frappe.db.sql("""
        SELECT SUM(total) as actual_total
        FROM `tabPurchase Invoice`
        WHERE cost_center = (
            SELECT cost_centre FROM `tabProperty` WHERE name = %(prop)s
        )
        AND YEAR(posting_date) = %(year)s
        AND docstatus = 1
    """, {"prop": property_name, "year": year})[0][0] or 0

    # Total leaseable area for proration
    total_area = frappe.db.sql("""
        SELECT SUM(area_sqft) FROM `tabProperty Unit`
        WHERE property = %(prop)s AND status != 'Decommissioned'
    """, {"prop": property_name})[0][0] or 1

    results = []
    for lease in leases:
        unit_area = frappe.db.get_value(
            "Property Unit", lease.unit, "area_sqft"
        ) or 0
        unit_share = unit_area / total_area
        actual_share = flt(actual_costs) * unit_share
        billed = flt(lease.billed_svc_charge)
        variance = actual_share - billed
        results.append({
            "lease": lease.name,
            "tenant": lease.tenant,
            "unit": lease.unit,
            "billed": round(billed, 2),
            "actual_share": round(actual_share, 2),
            "variance": round(variance, 2),
            "action": "Invoice" if variance > 0 else "Credit Note"
        })
    return results
```

---
## API ENDPOINTS

```python
# propx/property_management/api/billing_api.py

import frappe
from frappe.utils import today, add_days, get_first_day, get_last_day


@frappe.whitelist()
def get_billing_kpis():
    ms = get_first_day(today())
    me = get_last_day(today())
    total_inv = frappe.db.sql("""
        SELECT SUM(grand_total) FROM `tabSales Invoice`
        WHERE docstatus=1 AND propx_lease IS NOT NULL
          AND posting_date BETWEEN %s AND %s
    """, (ms, me))[0][0] or 0
    collected = frappe.db.sql("""
        SELECT SUM(grand_total - outstanding_amount) FROM `tabSales Invoice`
        WHERE docstatus=1 AND propx_lease IS NOT NULL
          AND posting_date BETWEEN %s AND %s
    """, (ms, me))[0][0] or 0
    outstanding = total_inv - collected
    return {
        "total_invoiced": total_inv,
        "collected": collected,
        "outstanding": outstanding,
        "collection_rate": round(collected / total_inv * 100, 1) if total_inv else 0
    }


@frappe.whitelist()
def get_pdc_kpis():
    in7 = add_days(today(), 7)
    in30 = add_days(today(), 30)
    return {
        "on_hand": frappe.db.count("PDC Register", {"status": "Received"}),
        "on_hand_value": frappe.db.sql(
            "SELECT SUM(amount) FROM `tabPDC Register` WHERE status='Received'"
        )[0][0] or 0,
        "due_7": frappe.db.count("PDC Register", {
            "status": "Received",
            "cheque_date": ["between", [today(), in7]]
        }),
        "due_30": frappe.db.count("PDC Register", {
            "status": "Received",
            "cheque_date": ["between", [today(), in30]]
        }),
        "bounce_risk": frappe.db.count("PDC Register", {
            "status": "Received", "bounce_risk": 1
        }),
        "bounced_month": frappe.db.count("PDC Register", {
            "status": "Bounced",
            "bounce_date": [">=", get_first_day(today())]
        }),
        "cleared_month": frappe.db.count("PDC Register", {
            "status": "Cleared",
            "cleared_date": [">=", get_first_day(today())]
        }),
    }


@frappe.whitelist()
def get_upcoming_pdc(days=30):
    cutoff = add_days(today(), int(days))
    return frappe.db.sql("""
        SELECT p.name, p.cheque_number, p.bank_name, p.amount,
               p.cheque_date, p.status, p.bounce_risk,
               p.previous_bounces, p.tenant,
               c.customer_name as tenant_name,
               p.unit, p.property, p.lease
        FROM `tabPDC Register` p
        LEFT JOIN `tabCustomer` c ON c.name = p.tenant
        WHERE p.status IN ('Received','Deposited')
          AND p.cheque_date BETWEEN %(today)s AND %(cutoff)s
        ORDER BY p.cheque_date ASC
    """, {"today": today(), "cutoff": cutoff}, as_dict=True)


@frappe.whitelist()
def mark_pdc_deposited(pdc_name, deposited_date=None):
    doc = frappe.get_doc("PDC Register", pdc_name)
    doc.deposit(deposited_date)
    return {"status": "deposited"}


@frappe.whitelist()
def mark_pdc_cleared(pdc_name, cleared_date=None):
    doc = frappe.get_doc("PDC Register", pdc_name)
    pe = doc.clear(cleared_date)
    return {"status": "cleared", "payment_entry": pe}


@frappe.whitelist()
def mark_pdc_bounced(pdc_name, reason, bounce_date=None):
    doc = frappe.get_doc("PDC Register", pdc_name)
    doc.bounce(bounce_date, reason)
    return {"status": "bounced"}
```

---
## HOOKS ADDITIONS

```python
# In hooks.py
scheduler_events = {
    "monthly": [
        "propx.property_management.utils.billing_utils.generate_monthly_invoices",
    ],
    "daily": [
        "propx.property_management.utils.billing_utils.apply_late_fees",
        "propx.property_management.tasks.send_pdc_due_reminders",
    ]
}
```

---
## CHECKLIST

- [ ] Create billing Items fixture (11 items)
- [ ] Create UAE/KSA/Oman Tax Templates in ERPNext
- [ ] Add custom fields to Sales Invoice (5 propx_ fields)
- [ ] Create PDC Register DocType
- [ ] Create PDC Deposit Batch + child DocType
- [ ] Write pdc_register.py controller
- [ ] Write billing_utils.py (generate invoices, late fees, pdc entries)
- [ ] Write service_charge_utils.py (CAM reconciliation)
- [ ] Write billing_api.py (7 endpoints)
- [ ] Add monthly/daily scheduler entries
- [ ] Test: activate lease → PDC register entries auto-created
- [ ] Test: mark PDC cleared → Payment Entry created + SI reconciled
- [ ] Test: mark PDC bounced → penalty invoice created
- [ ] Test: late fee applies after grace period on unpaid invoice
- [ ] Test: CAM reconciliation calculates correct variance per tenant
