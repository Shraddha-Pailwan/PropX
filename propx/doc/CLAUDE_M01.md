# CLAUDE.md — M01: Property & Asset Registry
# propx/docs/CLAUDE_M01.md

## PURPOSE
Master registry of all real estate assets. Every lease, invoice, work order,
inspection, and meter links back to a Property Unit. Build this first.

## REUSE FROM ERPNext (zero new code)
- `Cost Center`  — create one per Property via script; links to Company
- `Asset`        — link building/equipment assets here for depreciation
- `Address`      — use for property location

## DOCTYPES TO BUILD (4 new + 1 child)

---
### DocType 1: Property

Naming: `format:PROP-{####}` (e.g. PROP-0001)
Title field: `property_name`
Track changes: yes

Fields:
```
property_name       Data        reqd, in_list_view
property_code       Data        unique identifier, e.g. "TowerA"
company             Link→Company  reqd
owner               Link→Customer reqd  "Owner/Investor"
property_category   Select      reqd    Residential|Commercial|Industrial|Mixed-Use|Short-Term Rental
property_type       Select              Apartment Block|Villa Complex|Office Tower|Retail Centre|Warehouse|Serviced Apartments|Mixed-Use Tower
address_line_1      Data        reqd
address_line_2      Data
city                Data        reqd
emirate_region      Select      Dubai|Abu Dhabi|Sharjah|Ajman|RAK|Fujairah|UAQ|Muscat|Riyadh|Jeddah|Nairobi|Other
country             Link→Country  default "United Arab Emirates"
google_maps_link    Data

# GCC compliance
ejari_building_id   Data        "Ejari Building Registration ID"
dewa_premise_number Data        "DEWA Premise No. (Dubai)"
sewa_account        Data        "SEWA Account No. (Sharjah)"
omas_account        Data        "OMAS Account No. (Oman)"
municipality_code   Data

# Financial
cost_centre         Link→Cost Center  reqd  "ERPNext Cost Centre for this property P&L"
currency            Link→Currency     default AED
vat_registration    Data              "VAT/TRN Registration Number"

# Physical
total_floors        Int
total_area_sqft     Float
year_built          Int
commissioning_date  Date

# Media
property_photos     Table→Property Photo  (child)
property_documents  Table→Property Document (child)

# Computed (read-only, updated by scheduler)
total_units         Int         read_only
occupied_units      Int         read_only
occupancy_pct       Percent     read_only
```

Permissions:
- Property Manager: CRUD
- Lease Manager: Read
- Accountant: Read
- Property Owner: Read (match_field: owner)

---
### DocType 2: Property Floor

Naming: `format:{property}-F{floor_number}`
Parent: Property

Fields:
```
property        Link→Property   reqd
floor_number    Int             reqd, in_list_view
floor_label     Data            "Ground, Mezzanine, Level 1 ..."
floor_area_sqft Float
common_area_sqft Float
floor_plan      Attach Image
status          Select          Active|Under Renovation|Decommissioned  default Active
```

---
### DocType 3: Property Unit  ← ANCHOR DOCTYPE

Naming: `format:{property}-{unit_number}`
Title field: `unit_number`
Track changes: yes

Fields:
```
# Identity
unit_number         Data        reqd, in_list_view, bold
property            Link→Property  reqd, in_list_view
floor               Link→Property Floor
property_category   Select (fetched from Property, read_only)

# Classification
usage_type          Select      reqd
                    Residential|Commercial|Industrial|Short-Term Rental|Storage|Parking|Common Area
sub_type            Select
                    Studio|1 Bedroom|2 Bedroom|3 Bedroom|4+ Bedroom|Penthouse
                    |Office|Retail Shop|Showroom|Warehouse|Lab|Serviced Apartment
furnished_status    Select      Unfurnished|Semi-Furnished|Furnished

# Dimensions
area_sqft           Float       in_list_view
area_sqm            Float       read_only   "auto: sqft × 0.0929"
bedrooms            Int
bathrooms           Float
parking_spaces      Int         default 0
parking_bays        Table→Unit Parking Bay Link  (child, optional)

# Financial
asking_rent_annual  Currency    in_list_view
last_agreed_rent    Currency
market_rent_benchmark Currency  "For AI pricing comparison"
is_vat_applicable   Check       default 0
                    "Auto-set: Residential=0, Commercial=1"
service_charge_annual Currency  "Annual service charge estimate"
security_deposit_months Int     default 2

# Current tenancy (read-only, auto-updated by lease workflow)
status              Select      reqd
                    Vacant|Occupied|Reserved|Under Maintenance|Under Renovation|Decommissioned
                    default Vacant, in_list_view
current_lease       Link→Lease  read_only
current_tenant      Link→Customer  read_only
vacancy_since       Date        read_only
days_vacant         Int         read_only

# GCC compliance
ejari_unit_number   Data        "Ejari Unit Reference"
dewa_account_number Data        "DEWA Meter Account"
municipality_unit_code Data

# Media
unit_photos         Table→Unit Photo  (child)
floor_plan_image    Attach Image

# Computed
total_revenue_ytd   Currency    read_only
maintenance_cost_ytd Currency   read_only
```

Permissions:
- Property Manager: CRUD
- Lease Manager: Read+Write (no delete)
- Maintenance Technician: Read
- Tenant: Read (match on current_tenant — portal only)

---
### DocType 4: Unit Asset

Naming: Autoname (Series: UA-.#####)
Parent DocType: Property Unit (via child table or standalone with link)

Fields:
```
unit            Link→Property Unit  reqd
asset_name      Data                reqd, in_list_view
asset_category  Select
                HVAC|Electrical|Plumbing|Appliance|Furniture|Security|Fire Safety|Lift|Other
make_model      Data
serial_number   Data
purchase_date   Date
warranty_expiry Date
condition       Select              Good|Fair|Needs Repair|Replace
notes           Small Text
erpnext_asset   Link→Asset          "Link to ERPNext Asset for depreciation"
```

---
### Child DocTypes

**Unit Photo** (istable=1):
- photo: Attach Image, reqd
- caption: Data
- photo_type: Select  Exterior|Living Area|Bedroom|Kitchen|Bathroom|Other

**Property Photo** (istable=1):
- photo: Attach Image, reqd
- caption: Data

**Property Document** (istable=1):
- document_type: Select  Title Deed|NOC|Insurance|Floor Plans|Building Permit|Other
- document: Attach, reqd
- expiry_date: Date
- notes: Small Text

---
## PYTHON CONTROLLER

```python
# propx/property_management/doctype/property_unit/property_unit.py

import frappe
from frappe.model.document import Document
from frappe.utils import today, date_diff, flt


class PropertyUnit(Document):

    def validate(self):
        self.calculate_area_sqm()
        self.calculate_days_vacant()
        self.set_vat_rule()
        self.fetch_property_category()

    def calculate_area_sqm(self):
        if self.area_sqft:
            self.area_sqm = round(flt(self.area_sqft) * 0.0929, 2)

    def calculate_days_vacant(self):
        if self.status == "Vacant" and self.vacancy_since:
            self.days_vacant = date_diff(today(), self.vacancy_since)
        elif self.status != "Vacant":
            self.days_vacant = 0

    def set_vat_rule(self):
        """UAE: Residential rent is VAT exempt. Commercial is 5%."""
        if self.usage_type == "Residential":
            self.is_vat_applicable = 0
        elif self.usage_type in ["Commercial", "Industrial", "Storage"]:
            self.is_vat_applicable = 1

    def fetch_property_category(self):
        if self.property:
            cat = frappe.db.get_value("Property", self.property,
                                       "property_category")
            if cat:
                self.property_category = cat

    def on_update(self):
        self._refresh_property_occupancy()

    def _refresh_property_occupancy(self):
        if not self.property:
            return
        total = frappe.db.count(
            "Property Unit",
            {"property": self.property,
             "status": ["not in", ["Decommissioned"]]}
        )
        occupied = frappe.db.count(
            "Property Unit",
            {"property": self.property, "status": "Occupied"}
        )
        pct = round(occupied / total * 100, 1) if total else 0
        frappe.db.set_value("Property", self.property, {
            "total_units": total,
            "occupied_units": occupied,
            "occupancy_pct": pct
        })

    @frappe.whitelist()
    def get_lease_history(self):
        return frappe.get_all(
            "Lease",
            filters={"unit": self.name},
            fields=["name", "tenant", "tenant_name", "start_date",
                    "end_date", "annual_rent", "status"],
            order_by="start_date desc"
        )
```

---
## SCHEDULED TASKS

```python
# propx/property_management/tasks.py

import frappe
from frappe.utils import today, date_diff


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
```

Add to `hooks.py`:
```python
scheduler_events = {
    "daily": [
        "propx.property_management.tasks.update_vacancy_days",
    ]
}
```

---
## API ENDPOINTS

```python
# propx/property_management/api/property_api.py

import frappe


@frappe.whitelist()
def get_portfolio_summary(company=None):
    """Dashboard KPIs. Called on React dashboard load."""
    f = {}
    if company:
        f["company"] = company

    total = frappe.db.count(
        "Property Unit",
        {**f, "status": ["!=", "Decommissioned"]}
    )
    occupied = frappe.db.count(
        "Property Unit", {**f, "status": "Occupied"}
    )
    vacant = frappe.db.count(
        "Property Unit", {**f, "status": "Vacant"}
    )
    return {
        "total_units": total,
        "occupied": occupied,
        "vacant": vacant,
        "occupancy_pct": round(occupied / total * 100, 1) if total else 0,
    }


@frappe.whitelist()
def get_units_by_property(property_name, status=None):
    """Unit grid for React view."""
    f = {"property": property_name}
    if status:
        f["status"] = status
    return frappe.get_all(
        "Property Unit", filters=f,
        fields=["name", "unit_number", "floor", "usage_type", "sub_type",
                "area_sqft", "status", "current_tenant", "current_lease",
                "asking_rent_annual", "last_agreed_rent", "days_vacant",
                "is_vat_applicable", "furnished_status"]
    )


@frappe.whitelist()
def get_vacant_units(property_name=None, usage_type=None):
    """Leasing module: find available units."""
    f = {"status": "Vacant"}
    if property_name:
        f["property"] = property_name
    if usage_type:
        f["usage_type"] = usage_type
    return frappe.get_all(
        "Property Unit", filters=f,
        fields=["name", "unit_number", "property", "floor", "usage_type",
                "sub_type", "area_sqft", "asking_rent_annual",
                "days_vacant", "is_vat_applicable", "furnished_status"]
    )


@frappe.whitelist()
def get_properties_list(company=None):
    """Properties table for React portfolio view."""
    f = {}
    if company:
        f["company"] = company
    return frappe.get_all(
        "Property", filters=f,
        fields=["name", "property_name", "property_category",
                "city", "emirate_region", "total_units",
                "occupied_units", "occupancy_pct", "cost_centre",
                "owner", "currency"]
    )
```

---
## INSTALL SETUP SCRIPT

```python
# propx/property_management/setup/create_cost_centres.py

import frappe


def create_cost_centre_for_property(property_name, company):
    """
    Called when a new Property is saved.
    Creates an ERPNext Cost Centre matching the property name.
    """
    cc_name = f"{property_name} - {frappe.db.get_value('Company', company, 'abbr')}"
    if frappe.db.exists("Cost Center", cc_name):
        return cc_name

    parent = frappe.db.get_value(
        "Cost Center",
        {"is_group": 1, "company": company},
        "name"
    )
    cc = frappe.get_doc({
        "doctype": "Cost Center",
        "cost_center_name": property_name,
        "parent_cost_center": parent,
        "company": company,
        "is_group": 0
    })
    cc.insert(ignore_permissions=True)
    frappe.db.set_value("Property", property_name, "cost_centre", cc.name)
    return cc.name
```

Add to Property `on_submit` or `after_insert`:
```python
from propx.property_management.setup.create_cost_centres import (
    create_cost_centre_for_property
)
create_cost_centre_for_property(self.name, self.company)
```

---
## CHECKLIST

- [ ] Create Property DocType (all fields above)
- [ ] Create Property Floor DocType
- [ ] Create Property Unit DocType (anchor)
- [ ] Create Unit Asset DocType
- [ ] Create all 3 child DocTypes (Unit Photo, Property Photo, Property Document)
- [ ] Write property_unit.py controller
- [ ] Write tasks.py with update_vacancy_days
- [ ] Write property_api.py with 4 whitelisted methods
- [ ] Add scheduler entry to hooks.py
- [ ] Write create_cost_centres.py
- [ ] Set permissions on all DocTypes
- [ ] Export as fixtures: `bench export-fixtures --app propx --doctype "Property Unit"`
- [ ] Test: create Property → Cost Centre auto-created
- [ ] Test: set unit to Vacant → days_vacant increments daily
- [ ] Test: get_portfolio_summary returns correct occupancy %
