"""
extraction_service.py
─────────────────────
Parses raw OCR text and extracts mandatory fields required under the
Legal Metrology (Packaged Commodities) Rules, 2011.

Mandatory declarations per Rule 6:
  (a) Name & address of the manufacturer / importer / packer
  (b) Common / generic name of the commodity
  (c) Net quantity
  (d) Month & year of manufacture / packing / import
  (e) Retail sale price (MRP)
  (f) Consumer care details
  (g) Country of origin (for imported goods)
  (h) FSSAI / BIS / other statutory licence number (where applicable)

Returns
-------
dict: { field_name -> { "value": ..., "raw_match": ..., "found": bool } }
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Regex patterns
# ─────────────────────────────────────────────────────────────────────────────

# MRP – handles "MRP Rs. 20", "MRP ₹20.00", "M.R.P.: Rs 125/-"
_PAT_MRP = re.compile(
    r"(?:M\.?R\.?P\.?|Maximum\s+Retail\s+Price)"
    r"[\s:]*"
    r"(?:Rs\.?|₹|INR)?\s*"
    r"([\d,]+(?:\.\d{1,2})?)"
    r"(?:\s*(?:/-|/-))?",
    re.IGNORECASE,
)

# Net quantity – e.g. "500 g", "1.5 kg", "200 ml", "1 L", "250GM", "20Og" (OCR O/0 confusion)
_PAT_NET_QTY = re.compile(
    r"(?:Net\s+(?:Weight|Qty|Quantity|Content|Vol(?:ume)?)|Contents?)"
    r"[\s:]*"
    r"([\dO]+(?:[.,][\dO]+)?)\s*"          # allow capital-O anywhere as digit (OCR artefact)
    r"(kg|g|gm|gram|mg|l|lt|ltr|litre|liter|ml|millilitre|milliliter|units?|pcs?|nos?|pieces?)",
    re.IGNORECASE,
)

# Manufacturing date – "Mfg. Date: 01/2026", "Mfg: Date: 03/2026", "Manufactured: Jan 2026", "MFG: 2026-01"
_PAT_MFG_DATE = re.compile(
    r"(?:Mfg\.?|Manufactured|Manufacturing|Packed|Packing)\s*[:]?\s*(?:Date|Dt\.?)?[\s:]*"
    r"((?:\d{1,2}[/-])?(?:\d{4}|\d{2})|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4})",
    re.IGNORECASE,
)

# Expiry / Best-before date
_PAT_EXP_DATE = re.compile(
    r"(?:Exp(?:iry)?\.?|Best\s+Before|Use\s+By|BB(?:D)?\.?)\s*(?:Date|Dt\.?)?[\s:]*"
    r"((?:\d{1,2}[/-])?(?:\d{4}|\d{2})|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}|"
    r"\d+\s*(?:months?|years?|days?)\s*(?:from\s+(?:manufacture|mfg\.?|packing|date of manufacture))?)",
    re.IGNORECASE,
)

# Consumer care – phone / email / address
# Handles toll-free with placeholders (1800-XXX-1234) and standard 10-digit
_PAT_CONSUMER_PHONE = re.compile(
    r"(?:Consumer\s+Care|Helpline|Toll\s*[- ]?Free|Customer\s+Care)[\s:]*"
    r"((?:\+91[\s-]?)?(?:1800[\s-]?[\w]{3}[\s-]?[\d]{4}|\d{10}))",
    re.IGNORECASE,
)

_PAT_CONSUMER_EMAIL = re.compile(
    r"(?:Consumer\s+Care|Helpline|Customer\s+Care|Email|E-mail)[\s:]*"
    r"([\w.\-+]+@[\w.\-]+\.\w{2,})",
    re.IGNORECASE,
)

# Manufacturer name & address — captures across newlines since EasyOCR
# often splits name and address onto separate lines.
# Matches both "Manufactured by", "Packed by", AND bare "Manufacturer:"
_PAT_MANUFACTURER = re.compile(
    r"(?:(?:Manufactured|Marketed|Packed|Imported)\s+(?:by|for|in)|Manufacturer)[\s:]*"
    r"(.{10,200}?)(?=\nFSSAI|\nConsumer|\nMRP|\nNet|\nBest|\nCountry|\nBatch|$)",
    re.IGNORECASE | re.DOTALL,
)

# Country of origin
_PAT_COUNTRY = re.compile(
    r"(?:Country\s+of\s+Origin|Made\s+in)[\s:]*([A-Za-z ]+)",
    re.IGNORECASE,
)

# FSSAI licence
_PAT_FSSAI = re.compile(
    r"(?:FSSAI\s+(?:Lic(?:ence|ense)?\.?\s+No\.?|Approval\s+No\.?|Reg(?:istration)?\.?\s+No\.?)|FSSAI\s*No\.?)[\s:]*"
    r"(\d{14})",
    re.IGNORECASE,
)

# BIS / ISI mark
_PAT_BIS = re.compile(
    r"(?:BIS|ISI|IS\s+\d+)[\s:]*([A-Z0-9\-/]+)",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _first(pattern: re.Pattern, text: str, group: int = 1) -> Optional[str]:
    m = pattern.search(text)
    if m:
        return m.group(group).strip()
    return None


def _all_matches(pattern: re.Pattern, text: str, group: int = 1) -> list:
    return [m.group(group).strip() for m in pattern.finditer(text)]


def _field(value, raw=None) -> dict:
    return {
        "value": value,
        "raw_match": raw,
        "found": value is not None,
        # If nothing was found, expose a human-readable placeholder
        # so the UI never shows a blank cell.
        "display": str(value) if value is not None else "NOT DETECTED / REVIEW REQUIRED",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Main extraction function
# ─────────────────────────────────────────────────────────────────────────────

def extract_fields(raw_text: str) -> dict:
    """
    Extract all mandatory LM-PC Rule 6 fields from *raw_text*.

    Returns a dict mapping field names to result dicts:
      { "value": <extracted value or None>, "raw_match": <matched string>, "found": bool }
    """
    text = raw_text

    # ── MRP ──────────────────────────────────────────────────────────────────
    mrp_match = _PAT_MRP.search(text)
    mrp_value = None
    if mrp_match:
        raw_num = mrp_match.group(1).replace(",", "")
        try:
            mrp_value = float(raw_num)
        except ValueError:
            mrp_value = raw_num

    # ── Net Quantity ──────────────────────────────────────────────────────────
    qty_match = _PAT_NET_QTY.search(text)
    net_qty = None
    if qty_match:
        # Normalise OCR artefact: capital-O often misread as digit 0
        qty_num = qty_match.group(1).replace("O", "0").replace("o", "0")
        net_qty = f"{qty_num} {qty_match.group(2).upper()}"

    # ── Manufacturing Date ────────────────────────────────────────────────────
    mfg_date = _first(_PAT_MFG_DATE, text)

    # ── Expiry / Best Before ─────────────────────────────────────────────────
    exp_date = _first(_PAT_EXP_DATE, text)

    # ── Consumer Care ─────────────────────────────────────────────────────────
    consumer_phone = _first(_PAT_CONSUMER_PHONE, text)
    consumer_email = _first(_PAT_CONSUMER_EMAIL, text)
    consumer_care = consumer_phone or consumer_email

    # ── Manufacturer ──────────────────────────────────────────────────────────
    manufacturer = _first(_PAT_MANUFACTURER, text)
    if manufacturer:
        # Clean up OCR artefacts
        manufacturer = re.sub(r"\s+", " ", manufacturer).strip(" ,.")

    # ── Country of Origin ─────────────────────────────────────────────────────
    country = _first(_PAT_COUNTRY, text)

    # ── FSSAI ─────────────────────────────────────────────────────────────────
    fssai = _first(_PAT_FSSAI, text)

    # ── BIS / ISI ─────────────────────────────────────────────────────────────
    bis = _first(_PAT_BIS, text)

    return {
        "mrp": _field(mrp_value, mrp_match.group(0) if mrp_match else None),
        "net_quantity": _field(net_qty, qty_match.group(0) if qty_match else None),
        "mfg_date": _field(mfg_date),
        "exp_date": _field(exp_date),
        "consumer_care": _field(consumer_care),
        "manufacturer": _field(manufacturer),
        "country_of_origin": _field(country),
        "fssai_licence": _field(fssai),
        "bis_mark": _field(bis),
    }


def extract_from_listing_and_text(listing: Optional[dict] = None, raw_text: str = "") -> dict:
    """
    Synthesize declarations from OCR text (if package was scanned/OCRed)
    and scraped online listing metadata.

    Prioritizes label OCR text, filling in and corroborating declarations with
    structured listing metadata (Title, MRP, Net Quantity, Brand/Manufacturer, Country of Origin).
    """
    extracted = extract_fields(raw_text)

    if not listing or not isinstance(listing, dict):
        return extracted

    # 1. MRP
    if not extracted["mrp"]["found"] and listing.get("mrp") is not None:
        extracted["mrp"] = _field(listing["mrp"], raw=f"₹{listing['mrp']} (from online listing)")

    # 2. Net Quantity
    if not extracted["net_quantity"]["found"] and listing.get("net_quantity"):
        extracted["net_quantity"] = _field(listing["net_quantity"], raw=f"{listing['net_quantity']} (from online listing)")

    # 3. Manufacturer / Brand
    if not extracted["manufacturer"]["found"] and listing.get("manufacturer"):
        extracted["manufacturer"] = _field(listing["manufacturer"], raw=f"{listing['manufacturer']} (from online listing)")

    # 4. Country of Origin
    if not extracted["country_of_origin"]["found"] and listing.get("country_of_origin"):
        extracted["country_of_origin"] = _field(listing["country_of_origin"], raw=f"{listing['country_of_origin']} (from online listing)")

    # 5. Extract additional fields from listing's raw page text if available
    page_text = listing.get("page_text") or ""
    if page_text:
        if not extracted["mfg_date"]["found"]:
            mfg = _first(_PAT_MFG_DATE, page_text)
            if mfg:
                extracted["mfg_date"] = _field(mfg, raw=mfg)

        if not extracted["exp_date"]["found"]:
            exp = _first(_PAT_EXP_DATE, page_text)
            if exp:
                extracted["exp_date"] = _field(exp, raw=exp)

        if not extracted["consumer_care"]["found"]:
            c_phone = _first(_PAT_CONSUMER_PHONE, page_text)
            c_email = _first(_PAT_CONSUMER_EMAIL, page_text)
            care = c_phone or c_email
            if care:
                extracted["consumer_care"] = _field(care, raw=care)

        if not extracted["fssai_licence"]["found"]:
            fssai = _first(_PAT_FSSAI, page_text)
            if fssai:
                extracted["fssai_licence"] = _field(fssai, raw=fssai)

    return extracted

