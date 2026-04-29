"""
pdc_utils.py — PDC Register helpers.

create_pdc_entries is the canonical implementation in billing_utils.
This module re-exports it so callers can use either path.
"""
from propx.property_management.utils.billing_utils import create_pdc_entries  # noqa: F401
