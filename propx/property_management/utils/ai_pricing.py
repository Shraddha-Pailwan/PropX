"""
ai_pricing.py — M11 AI Rent Pricing Recommendation
Provides data-driven rent suggestions based on:
  - Historical rent for the unit
  - Comparable units in the same property (same type, ±20% area)
  - Market benchmark stored on the Property Unit
"""
import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_rent_recommendation(unit_name):
    """
    Return a rent recommendation for a Property Unit.

    Returns a dict with:
      unit, current_asking, last_agreed_rent, avg_comparable_rent,
      market_benchmark, recommended_rent, comparable_units, confidence
    """
    if not frappe.db.exists("Property Unit", unit_name):
        frappe.throw(f"Property Unit '{unit_name}' not found.")

    unit = frappe.get_doc("Property Unit", unit_name)

    # ── Historical rent for this unit ─────────────────────────────────
    history = frappe.db.sql(
        """
        SELECT annual_rent, start_date
        FROM `tabLease`
        WHERE unit = %s
          AND status NOT IN ('Draft', 'Cancelled')
          AND annual_rent > 0
        ORDER BY start_date DESC
        LIMIT 5
        """,
        unit_name,
        as_dict=True,
    )
    last_rent = flt(history[0].annual_rent) if history else None

    # ── Comparable units (same property, same type, ±20% area) ─────────
    area = flt(unit.area_sqft) or 0
    area_low = area * 0.8
    area_high = area * 1.2

    comps = frappe.db.sql(
        """
        SELECT pu.area_sqft, l.annual_rent
        FROM `tabProperty Unit` pu
        JOIN `tabLease` l ON l.unit = pu.name
        WHERE pu.property = %s
          AND pu.usage_type = %s
          AND pu.name != %s
          AND l.status IN ('Active', 'Expiring')
          AND l.annual_rent > 0
          AND pu.area_sqft BETWEEN %s AND %s
        """,
        (unit.property, unit.usage_type, unit_name, area_low, area_high),
        as_dict=True,
    )
    comp_rents = [flt(c.annual_rent) for c in comps if c.annual_rent]
    avg_comp = round(sum(comp_rents) / len(comp_rents), 0) if comp_rents else None

    # ── Market benchmark from Property Unit ────────────────────────────
    benchmark = flt(getattr(unit, "market_rent_benchmark", 0)) or None

    # ── Build recommendation ────────────────────────────────────────────
    candidates = [r for r in [avg_comp, last_rent, benchmark] if r]
    if not candidates:
        return {
            "unit": unit_name,
            "current_asking": flt(unit.asking_rent_annual),
            "last_agreed_rent": None,
            "avg_comparable_rent": None,
            "market_benchmark": None,
            "recommended_rent": None,
            "comparable_units": 0,
            "confidence": "Low",
            "reason": "Insufficient data to generate recommendation.",
        }

    base = max(candidates)
    # 5% uplift, rounded to nearest 100
    recommended = round(base * 1.05 / 100) * 100

    confidence = (
        "High" if len(comp_rents) >= 3
        else "Medium" if len(comp_rents) >= 1
        else "Low"
    )

    return {
        "unit": unit_name,
        "current_asking": flt(unit.asking_rent_annual),
        "last_agreed_rent": last_rent,
        "avg_comparable_rent": avg_comp,
        "market_benchmark": benchmark,
        "recommended_rent": recommended,
        "comparable_units": len(comp_rents),
        "confidence": confidence,
        "reason": (
            f"Based on {len(comp_rents)} comparable unit(s), "
            f"last agreed rent, and market benchmark. "
            f"5% uplift applied."
        ),
    }


@frappe.whitelist()
def get_bulk_recommendations(property_name):
    """
    Return rent recommendations for all vacant units in a property.
    Useful for repricing campaigns.
    """
    units = frappe.get_all(
        "Property Unit",
        filters={"property": property_name, "status": "Vacant"},
        fields=["name"],
    )
    results = []
    for u in units:
        try:
            rec = get_rent_recommendation(u.name)
            results.append(rec)
        except Exception as e:
            results.append({"unit": u.name, "error": str(e)})
    return results
