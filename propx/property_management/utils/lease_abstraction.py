"""
lease_abstraction.py — M11 AI Lease Abstraction via Claude API
Accepts a base64-encoded lease PDF, extracts key terms using Claude,
and optionally auto-fills the linked Lease DocType.
"""
import json
import re

import frappe
import requests
from frappe.utils import flt


CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_MODEL = "claude-opus-4-5"   # kept current; update when 4.6 GA

EXTRACTION_PROMPT = """You are a GCC real estate lease abstraction specialist.
Extract the following fields from the lease document provided and return ONLY
valid JSON with exactly these keys (use null if a field cannot be determined):

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
}

Return ONLY the JSON object. No markdown, no explanation."""

# Mapping: extracted JSON key → Lease DocType fieldname
FIELD_MAP = {
    "start_date":          "start_date",
    "end_date":            "end_date",
    "annual_rent":         "annual_rent",
    "security_deposit":    "security_deposit",
    "number_of_cheques":   "number_of_cheques",
    "notice_period_days":  "notice_period_days",
    "ejari_number":        "ejari_contract_no",
    "special_conditions":  "special_conditions",
    "currency":            "currency",
}


@frappe.whitelist()
def abstract_lease_pdf(lease_name=None, pdf_base64=None):
    """
    Upload a base64-encoded lease PDF to Claude, extract key lease terms,
    and (if lease_name provided) auto-fill the Lease DocType.

    Args:
        lease_name  : Optional Lease document name to update.
        pdf_base64  : Base64-encoded PDF content (string).

    Returns dict:
        extracted       : dict of extracted fields
        lease_updated   : bool
        lease_name      : str or None
        errors          : list of any non-fatal issues
    """
    if not pdf_base64:
        frappe.throw("pdf_base64 is required.")

    api_key = frappe.db.get_single_value("PropX Settings", "claude_api_key")
    if not api_key:
        frappe.throw(
            "Claude API key is not configured. "
            "Please set it in PropX Settings → Claude API Key."
        )

    # ── Call Claude ─────────────────────────────────────────────────────
    payload = {
        "model": CLAUDE_MODEL,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_PROMPT},
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_base64,
                        },
                    },
                ],
            }
        ],
    }

    try:
        response = requests.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        frappe.throw(f"Claude API request failed: {e}")

    result = response.json()
    raw_text = result.get("content", [{}])[0].get("text", "")

    # ── Parse extracted JSON ─────────────────────────────────────────────
    extracted = _parse_json_from_text(raw_text)
    errors = []

    # ── Apply to Lease DocType ────────────────────────────────────────────
    lease_updated = False
    if lease_name and extracted:
        try:
            lease_doc = frappe.get_doc("Lease", lease_name)
            for src_key, dst_field in FIELD_MAP.items():
                value = extracted.get(src_key)
                if value is None:
                    continue
                # Coerce numeric fields
                if dst_field in ("annual_rent", "security_deposit"):
                    value = flt(value)
                elif dst_field in ("number_of_cheques", "notice_period_days"):
                    value = int(value) if value else None
                setattr(lease_doc, dst_field, value)
            lease_doc.save(ignore_permissions=True)
            lease_updated = True
        except Exception as e:
            errors.append(f"Failed to update Lease: {e}")

    return {
        "extracted": extracted,
        "lease_updated": lease_updated,
        "lease_name": lease_name,
        "errors": errors,
    }


def _parse_json_from_text(text):
    """Try to parse JSON from Claude's response; fall back to regex extraction."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to pull JSON block out of surrounding text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    frappe.log_error(
        title="Lease Abstraction: JSON parse failure",
        message=f"Could not parse Claude response:\n{text}",
    )
    return {}
