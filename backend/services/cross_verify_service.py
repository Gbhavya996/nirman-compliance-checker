"""
cross_verify_service.py
───────────────────────
Compares OCR-extracted label fields against URL-scraped listing fields
to detect potential discrepancies (mislabelled MRP, wrong quantity, etc.).

Fields compared
---------------
  • MRP           – label price vs listing price
  • Net Quantity   – label weight/volume vs listing description
  • Manufacturer   – label manufacturer vs listing brand

Each field produces a verdict:
  MATCH                               – values agree within tolerance
  POTENTIAL DISCREPANCY / REVIEW REQUIRED – values differ significantly
  UNAVAILABLE                         – one or both values missing
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

_VERDICT_MATCH       = "MATCH"
_VERDICT_DISCREPANCY = "POTENTIAL DISCREPANCY / REVIEW REQUIRED"
_VERDICT_UNAVAILABLE = "UNAVAILABLE"


def _norm_qty(qty_str: Optional[str]) -> Optional[float]:
    """
    Normalise quantity string to grams (or ml) for numeric comparison.
    Returns None if unparseable.
    """
    if not qty_str:
        return None
    qty_str = str(qty_str).strip().lower()
    # Extract number + unit
    m = re.search(r"([\d]+(?:[.,][\d]+)?)\s*(kg|g|gm|gram|mg|l|lt|ltr|litre|ml|millilitre)", qty_str, re.I)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = m.group(2).lower()
    # Convert everything to grams / ml
    conversions = {
        "kg": 1000, "g": 1, "gm": 1, "gram": 1, "mg": 0.001,
        "l": 1000, "lt": 1000, "ltr": 1000, "litre": 1000, "ml": 1, "millilitre": 1,
    }
    return value * conversions.get(unit, 1)


def _norm_brand(name: Optional[str]) -> str:
    """Lowercase, strip company suffixes and punctuation for fuzzy match."""
    if not name:
        return ""
    s = name.lower()
    s = re.sub(r"\b(pvt|ltd|private|limited|inc|corp|llp|co|foods|india)\b\.?", "", s, flags=re.I)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# Individual field comparisons
# ---------------------------------------------------------------------------

def _compare_mrp(label_val, listing_val) -> dict:
    """Compare MRP values. Allow ±2% tolerance for rounding."""
    row = {
        "field": "MRP",
        "label_value": f"₹{label_val}" if label_val is not None else None,
        "listing_value": f"₹{listing_val}" if listing_val is not None else None,
    }

    if label_val is None or listing_val is None:
        row["verdict"] = _VERDICT_UNAVAILABLE
        row["note"] = "One or both MRP values not available."
        return row

    try:
        lbl = float(label_val)
        lst = float(listing_val)
        diff_pct = round(abs(lbl - lst) / max(lbl, lst) * 100, 1)
        delta_rup = round(lst - lbl, 2)
        row["delta_rupees"] = delta_rup
        row["delta_str"] = f"+₹{delta_rup:.2f}" if delta_rup > 0 else f"-₹{abs(delta_rup):.2f}"
        row["delta_pct"] = diff_pct

        if lst > lbl + 0.05:
            row["verdict"] = _VERDICT_DISCREPANCY
            row["note"] = (
                f"Online listing shows ₹{lst:.2f} but label MRP is ₹{lbl:.2f} "
                f"(Delta: +₹{delta_rup:.2f} / +{diff_pct}%). Over-MRP violation under Section 18 / 36(1) LM-PC Rules."
            )
        elif diff_pct <= 2.0:
            row["verdict"] = _VERDICT_MATCH
            row["note"] = f"Both show ₹{lbl:.2f} (compliant within 2% tolerance)."
        else:
            row["verdict"] = _VERDICT_MATCH
            row["note"] = f"Listing price ₹{lst:.2f} is within package MRP ₹{lbl:.2f} (compliant sale)."
    except (TypeError, ValueError):
        row["verdict"] = _VERDICT_UNAVAILABLE
        row["note"] = "Could not parse MRP values for comparison."

    return row


def _compare_quantity(label_val, listing_val) -> dict:
    """Compare net quantity. Allow ±5% tolerance."""
    row = {
        "field": "Net Quantity",
        "label_value": str(label_val) if label_val else None,
        "listing_value": str(listing_val) if listing_val else None,
    }

    if not label_val or not listing_val:
        row["verdict"] = _VERDICT_UNAVAILABLE
        row["note"] = "One or both quantity values not available."
        return row

    lbl_g = _norm_qty(label_val)
    lst_g = _norm_qty(listing_val)

    if lbl_g is None or lst_g is None:
        # Fall back to string comparison
        lbl_clean = re.sub(r"\s+", "", str(label_val).lower())
        lst_clean = re.sub(r"\s+", "", str(listing_val).lower())
        row["verdict"] = _VERDICT_MATCH if lbl_clean == lst_clean else _VERDICT_DISCREPANCY
        row["note"] = "Compared as text strings (unit conversion not possible)."
        return row

    diff_pct = abs(lbl_g - lst_g) / max(lbl_g, lst_g) * 100
    if diff_pct <= 5.0:
        row["verdict"] = _VERDICT_MATCH
        row["note"] = f"Both quantities agree within 5% tolerance ({label_val} vs {listing_val})."
    else:
        row["verdict"] = _VERDICT_DISCREPANCY
        row["note"] = (
            f"Label shows {label_val} but listing shows {listing_val} "
            f"(difference: {diff_pct:.1f}%). Verify declared weight matches package."
        )

    return row


def _compare_manufacturer(label_val, listing_val) -> dict:
    """Fuzzy compare brand / manufacturer names."""
    row = {
        "field": "Manufacturer / Brand",
        "label_value": str(label_val)[:80] if label_val else None,
        "listing_value": str(listing_val)[:80] if listing_val else None,
    }

    if not label_val or not listing_val:
        row["verdict"] = _VERDICT_UNAVAILABLE
        row["note"] = "One or both manufacturer values not available."
        return row

    lbl_n = _norm_brand(label_val)
    lst_n = _norm_brand(listing_val)

    # Check if either normalised name contains the other (substring match)
    if lbl_n in lst_n or lst_n in lbl_n or lbl_n == lst_n:
        row["verdict"] = _VERDICT_MATCH
        row["note"] = "Brand/manufacturer names match (fuzzy comparison)."
    else:
        # Check word overlap
        lbl_words = set(lbl_n.split())
        lst_words = set(lst_n.split())
        overlap = lbl_words & lst_words
        if overlap and len(overlap) / max(len(lbl_words), len(lst_words), 1) >= 0.5:
            row["verdict"] = _VERDICT_MATCH
            row["note"] = f"Brand names partially match (shared words: {', '.join(overlap)})."
        else:
            row["verdict"] = _VERDICT_DISCREPANCY
            row["note"] = (
                f"Label says '{label_val[:50]}' but listing says '{listing_val[:50]}'. "
                "Verify that the product belongs to the declared manufacturer."
            )

    return row


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def cross_verify(extracted_fields: dict, listing: dict) -> dict:
    """
    Compare OCR-extracted label fields against scraped listing data.

    Parameters
    ----------
    extracted_fields : output of extraction_service.extract_fields()
    listing          : output of url_scraper_service.scrape_listing()

    Returns
    -------
    {
        "available": bool,
        "scraped": bool,
        "listing_url": str,
        "listing_title": str | None,
        "rows": [ { field, label_value, listing_value, verdict, note }, ... ],
        "overall": "ALL_MATCH" | "HAS_DISCREPANCY" | "UNAVAILABLE",
    }
    """
    if not listing.get("scraped"):
        return {
            "available": True,
            "scraped": False,
            "listing_url": listing.get("url", ""),
            "listing_title": None,
            "error": listing.get("error", "Listing data could not be fetched."),
            "rows": [],
            "overall": "UNAVAILABLE",
        }

    # Pull label values
    lbl_mrp  = (extracted_fields.get("mrp")          or {}).get("value")
    lbl_qty  = (extracted_fields.get("net_quantity")  or {}).get("value")
    lbl_mfr  = (extracted_fields.get("manufacturer")  or {}).get("value")

    # Pull listing values
    lst_mrp  = listing.get("mrp")
    lst_qty  = listing.get("net_quantity")
    lst_mfr  = listing.get("manufacturer")

    rows = [
        _compare_mrp(lbl_mrp, lst_mrp),
        _compare_quantity(lbl_qty, lst_qty),
        _compare_manufacturer(lbl_mfr, lst_mfr),
    ]

    verdicts = [r["verdict"] for r in rows]
    if all(v == _VERDICT_UNAVAILABLE for v in verdicts):
        overall = "UNAVAILABLE"
    elif any(v == _VERDICT_DISCREPANCY for v in verdicts):
        overall = "HAS_DISCREPANCY"
    else:
        overall = "ALL_MATCH"

    return {
        "available": True,
        "scraped": True,
        "listing_url": listing.get("url", ""),
        "listing_title": listing.get("product_title"),
        "domain": listing.get("domain", ""),
        "rows": rows,
        "overall": overall,
    }
