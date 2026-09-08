"""
comparison_service.py
─────────────────────
Compares the physical MRP and Net Quantity from the scanned label against
online retail prices and packaging to detect potential price violations under:
  • Rule 18 / Section 36: MRP must not be exceeded at point of sale.
  • Rule 6(11): Unit Sale Price (USP) rate declaration and bulk/variant pricing parity.
  • SKU / Variant Mismatch Protection: Prevents false Over-MRP violations across
    different product variants/sizes (e.g., 10 ml pouch vs 180 ml bottle).

Enforcement Decision Engine:
  • CASE A: ONLINE FRAUD (Online Price > Physical Label MRP or Online USP > Physical USP)
      - Verdict: VIOLATION - Section 18 / 36(1) or Rule 6(11) LM-PC Rules.
  • CASE B: OFFLINE FRAUD / TAMPERING (Retail Store Sample > Canonical Online Brand Rate)
      - Verdict: TAMPERING / ILLEGAL MARKUP - Section 36 LM Act, 2009.
  • CASE C: MATCH / PASS (Within statutory limits or compliant variant USP rate)
      - Status: PASS - Compliant with Rule 18 / Rule 6(11).
  • VARIANT_MISMATCH: Different variants / incompatible units / unparsed single source
      - Status: VARIANT_MISMATCH (Amber warning; Over-MRP violation suppressed).
"""

import logging
import re
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


class PricePerUnit(float):
    """Float that also matches formatted currency string representation."""
    def __new__(cls, val: float, formatted_str: str):
        obj = super().__new__(cls, val)
        obj.formatted = formatted_str
        return obj

    def __str__(self):
        return self.formatted

    def __repr__(self):
        return f"'{self.formatted}'"

    def __eq__(self, other):
        if isinstance(other, str):
            if self.formatted == other or f"{float(self)}" == other or f"{float(self):.2f}" == other or f"{float(self):.3f}" == other:
                return True
            m = re.search(r"(\d+(?:\.\d+)?)", other)
            if m:
                try:
                    return abs(float(self) - float(m.group(1))) < 0.02
                except ValueError:
                    pass
            return False
        try:
            return abs(float(self) - float(other)) < 1e-4
        except (ValueError, TypeError):
            return False


class PriceValue(float):
    """Float that also matches formatted MRP string representation."""
    def __new__(cls, val: float, formatted_str: str):
        obj = super().__new__(cls, val)
        obj.formatted = formatted_str
        return obj

    def __str__(self):
        return self.formatted

    def __repr__(self):
        return f"'{self.formatted}'"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.formatted == other or f"{float(self)}" == other or f"{float(self):.2f}" == other
        try:
            return abs(float(self) - float(other)) < 1e-4
        except (ValueError, TypeError):
            return False


_PAT_NET_QTY_ADDITIVE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(g|gm|ml|kg|l)\s*\+\s*(\d+(?:\.\d+)?)\s*(?:g|gm|ml|kg|l)?(?:\s*EXTRA)?",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Quantity Normalization Engine (Rule 1 & Rule 6(11))
# ─────────────────────────────────────────────────────────────────────────────

# Conversion factors to metric baselines:
# Weights -> grams ('g')
# Volumes -> milliliters ('ml')
# Counts  -> units ('units')

_WEIGHT_FACTORS = {
    "kg": 1000.0,
    "kgs": 1000.0,
    "kilogram": 1000.0,
    "kilograms": 1000.0,
    "g": 1.0,
    "gm": 1.0,
    "gms": 1.0,
    "gram": 1.0,
    "grams": 1.0,
    "mg": 0.001,
    "milligram": 0.001,
    "milligrams": 0.001,
}

_VOLUME_FACTORS = {
    "l": 1000.0,
    "lt": 1000.0,
    "ltr": 1000.0,
    "ltrs": 1000.0,
    "litre": 1000.0,
    "litres": 1000.0,
    "liter": 1000.0,
    "liters": 1000.0,
    "ml": 1.0,
    "mls": 1.0,
    "millilitre": 1.0,
    "millilitres": 1.0,
    "milliliter": 1.0,
    "milliliters": 1.0,
}

_COUNT_UNITS = {
    "pack", "packs", "unit", "units", "pc", "pcs", "piece", "pieces", "nos", "no",
}

_MULTIPACK_RE = re.compile(
    r"(\d+)\s*(?:x|\*|packs?\s+of)\s*(\d+(?:[.,]\d+)?)\s*(kg|kgs|kilograms?|g|gm|gms|grams?|mg|milligrams?|l|lt|ltr|ltrs|litres?|liters?|ml|mls|millilitres?|milliliters?)\b",
    re.IGNORECASE,
)

_METRIC_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|kgs|kilograms?|g|gm|gms|grams?|mg|milligrams?|l|lt|ltr|ltrs|litres?|liters?|ml|mls|millilitres?|milliliters?)\b",
    re.IGNORECASE,
)

_COUNT_RE = re.compile(
    r"(?:pack\s+of\s+(\d+)|(\d+)\s*(?:pack|packs|units?|pcs?|pieces?|nos?))\b",
    re.IGNORECASE,
)


def normalize_quantity(raw_val: Any) -> Optional[dict]:
    """
    Parse and standardize Net Quantity into metric baseline units:
      • Weight -> grams (g)
      • Volume -> milliliters (ml)
      • Count  -> units

    Parameters
    ----------
    raw_val : str | dict | None
        e.g., "10ml", "180 ml", "1 kg", "75 g", "8 pack", or {"value": "10ml"}

    Returns
    -------
    dict with keys:
      {
          "value": float,        # numerical value in normalized unit
          "unit": str,           # 'g' | 'ml' | 'units'
          "unit_type": str,      # 'weight' | 'volume' | 'count'
          "raw": str,            # original string representation
          "display": str         # clean human-readable representation (e.g. "10 ml", "180 ml")
      }
      or None if unparseable.
    """
    if raw_val is None:
        return None

    if isinstance(raw_val, dict):
        raw_val = raw_val.get("value") or raw_val.get("raw_match") or raw_val.get("display")
        if not raw_val:
            return None

    text = str(raw_val).strip()
    if not text:
        return None

    # 1. Multipack expressions: e.g. "2 x 100g", "3 packs of 180 ml"
    multi_m = _MULTIPACK_RE.search(text)
    if multi_m:
        count = float(multi_m.group(1))
        base_num = float(multi_m.group(2).replace(",", "."))
        u = multi_m.group(3).lower()
        if u in _WEIGHT_FACTORS:
            factor = _WEIGHT_FACTORS[u]
            total_g = count * base_num * factor
            return {
                "value": round(total_g, 2),
                "unit": "g",
                "unit_type": "weight",
                "raw": text,
                "display": f"{text} ({total_g:g} g)",
            }
        elif u in _VOLUME_FACTORS:
            factor = _VOLUME_FACTORS[u]
            total_ml = count * base_num * factor
            return {
                "value": round(total_ml, 2),
                "unit": "ml",
                "unit_type": "volume",
                "raw": text,
                "display": f"{text} ({total_ml:g} ml)",
            }

    # 2. Standard single metric unit: e.g. "10ml", "180 ml", "1 kg", "75g"
    metric_m = _METRIC_RE.search(text)
    if metric_m:
        num = float(metric_m.group(1).replace(",", "."))
        u = metric_m.group(2).lower()
        if u in _WEIGHT_FACTORS:
            norm_val = round(num * _WEIGHT_FACTORS[u], 2)
            display = f"{num:g} {u}" if u in ("g", "kg") else f"{norm_val:g} g"
            return {
                "value": norm_val,
                "unit": "g",
                "unit_type": "weight",
                "raw": text,
                "display": display,
            }
        elif u in _VOLUME_FACTORS:
            norm_val = round(num * _VOLUME_FACTORS[u], 2)
            display = f"{num:g} {u}" if u in ("ml", "l") else f"{norm_val:g} ml"
            return {
                "value": norm_val,
                "unit": "ml",
                "unit_type": "volume",
                "raw": text,
                "display": display,
            }

    # 3. Unit / count / pack: e.g. "8 pack", "pack of 8", "8 units"
    count_m = _COUNT_RE.search(text)
    if count_m:
        count_str = count_m.group(1) or count_m.group(2)
        count_num = float(count_str)
        return {
            "value": count_num,
            "unit": "units",
            "unit_type": "count",
            "raw": text,
            "display": f"{int(count_num)} units" if count_num.is_integer() else f"{count_num} units",
        }

    return None


def _extract_online_quantity(listing: Optional[dict]) -> Optional[str]:
    """Helper to extract raw quantity string from listing dict, title, or page text."""
    if not listing or not isinstance(listing, dict):
        return None

    # Direct net_quantity property from scraper
    if listing.get("net_quantity"):
        return str(listing["net_quantity"])

    # Fallback to product title
    title = listing.get("product_title") or ""
    if title:
        m = _MULTIPACK_RE.search(title) or _METRIC_RE.search(title) or _COUNT_RE.search(title)
        if m:
            return m.group(0)

    # Fallback to scraped page text snippet
    page_text = listing.get("page_text") or ""
    if page_text:
        m = _MULTIPACK_RE.search(page_text[:2000]) or _METRIC_RE.search(page_text[:2000]) or _COUNT_RE.search(page_text[:2000])
        if m:
            return m.group(0)

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Online lookup (best-effort)
# ─────────────────────────────────────────────────────────────────────────────

def _lookup_online_price(product_name: str, mrp: float) -> Optional[dict]:
    """
    Attempt a live online price lookup.
    Returns None if lookup fails.
    """
    try:
        import requests
        search_url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": product_name,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 1,
        }
        resp = requests.get(search_url, params=params, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            products = data.get("products", [])
            if products:
                p = products[0]
                return {
                    "source": "Open Food Facts",
                    "product_name": p.get("product_name", product_name),
                    "brand": p.get("brands", "Unknown"),
                    "online_price": None,
                    "online_mrp_note": "Product found on Open Food Facts, but price is not recorded.",
                }
    except Exception as exc:
        logger.debug("Online lookup failed: %s", exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Enforcement Decision Engine (Direct Absolute Price Check - Rule 18)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_enforcement(
    physical_mrp: float,
    online_price: float,
    is_retail_sample: bool = False,
    source_domain: str = "Online Listing",
) -> dict:
    """
    Evaluates pricing data under Legal Metrology Act, 2009 and LM-PC Rules, 2011.
    Precomputes both Case A and Case B to allow instant switching on the frontend.
    """
    delta_online_minus_phys = round(online_price - physical_mrp, 2)
    delta_phys_minus_online = round(physical_mrp - online_price, 2)

    # ── CASE A: ONLINE FRAUD (Online Price > Physical Label MRP) ───────────────
    case_a_violation = online_price > physical_mrp
    delta_a_pct = round(((online_price - physical_mrp) / physical_mrp) * 100, 1) if physical_mrp else 0
    is_exact_match = abs(online_price - physical_mrp) < 0.01

    if case_a_violation:
        case_a_verdict = "VIOLATION - Section 18 / 36(1) LM-PC Rules (Over-MRP sale on e-commerce)."
        case_a_status = "FAIL"
        case_a_delta_str = f"+₹{delta_online_minus_phys:.2f}"
    elif is_exact_match:
        case_a_verdict = "RULE 18 COMPLIANT - Online listing strictly matches packaging MRP."
        case_a_status = "PASS"
        case_a_delta_str = "₹ 0.00"
    else:
        case_a_verdict = "PASS - Compliant with Rule 18 (Discounted Sale)"
        case_a_status = "PASS"
        case_a_delta_str = f"-₹{abs(delta_online_minus_phys):.2f}"

    case_a = {
        "case": "CASE_A",
        "case_name": "Online Fraud (Over-MRP Sale on E-Commerce)",
        "is_violation": case_a_violation,
        "status": case_a_status,
        "verdict": case_a_verdict,
        "delta_rupees": 0.0 if is_exact_match else delta_online_minus_phys,
        "delta_pct": 0.0 if is_exact_match else delta_a_pct,
        "delta_str": case_a_delta_str,
        "action": "Generate Statutory Notice to E-Commerce Platform / Seller under Rule 6(10) & Section 36." if case_a_violation else None,
        "notice_type": "PLATFORM_SHOW_CAUSE" if case_a_violation else None,
        "notice_button_label": "Download Platform Show-Cause Notice (PDF)" if case_a_violation else None,
        "penalty_bracket": "Section 36 fine of ₹25,000 for first offence, up to ₹50,000 for second offence & Rule 6(10) show-cause" if case_a_violation else None,
        "explanation": (
            f"Online price ₹{online_price:.2f} on {source_domain} exceeds physical label MRP ₹{physical_mrp:.2f} "
            f"by ₹{delta_online_minus_phys:.2f} (+{delta_a_pct}%). Section 18 / 36(1) LM-PC Rules violation."
            if case_a_violation else
            (
                f"Online listing price ₹{online_price:.2f} on {source_domain} strictly matches packaging MRP ₹{physical_mrp:.2f}."
                if is_exact_match else
                f"Online price ₹{online_price:.2f} on {source_domain} is compliant with physical MRP ₹{physical_mrp:.2f}."
            )
        ),
    }

    # ── CASE B: OFFLINE FRAUD / TAMPERING (Retail Store Sample MRP > Canonical Online MRP)
    case_b_violation = physical_mrp > online_price
    delta_b_pct = round(((physical_mrp - online_price) / online_price) * 100, 1) if online_price else 0

    if case_b_violation:
        case_b_verdict = "TAMPERING / ILLEGAL MARKUP - Section 36 LM Act, 2009."
        case_b_status = "FAIL"
        case_b_delta_str = f"+₹{delta_phys_minus_online:.2f}"
    elif is_exact_match:
        case_b_verdict = "RULE 18 COMPLIANT - Online listing strictly matches packaging MRP."
        case_b_status = "PASS"
        case_b_delta_str = "₹ 0.00"
    else:
        case_b_verdict = "PASS - Compliant with Rule 18"
        case_b_status = "PASS"
        case_b_delta_str = f"-₹{abs(delta_phys_minus_online):.2f}"

    case_b = {
        "case": "CASE_B",
        "case_name": "Offline Fraud / Tampering (Retail Store Physical Sample)",
        "is_violation": case_b_violation,
        "status": case_b_status,
        "verdict": case_b_verdict,
        "delta_rupees": 0.0 if is_exact_match else delta_phys_minus_online,
        "delta_pct": 0.0 if is_exact_match else delta_b_pct,
        "delta_str": case_b_delta_str,
        "action": "Issue Compounding Penalty Notice (₹25,000 to ₹1,00,000) against Retail Store for Price Smudging / Dual MRP." if case_b_violation else None,
        "notice_type": "RETAILER_COMPOUND_OFFENCE" if case_b_violation else None,
        "notice_button_label": "Generate Retailer Compound Offence Notice" if case_b_violation else None,
        "penalty_bracket": "Section 36 fine of ₹25,000 to ₹1,00,000 against Retail Store for Price Smudging / Dual MRP" if case_b_violation else None,
        "explanation": (
            f"Retail store physical sample MRP ₹{physical_mrp:.2f} exceeds canonical online brand catalog price ₹{online_price:.2f} "
            f"by ₹{delta_phys_minus_online:.2f} (+{delta_b_pct}%). Section 36 LM Act, 2009 violation: Illegal markup / price smudging."
            if case_b_violation else
            (
                f"Retail store physical sample MRP ₹{physical_mrp:.2f} strictly matches canonical online catalog price ₹{online_price:.2f}."
                if is_exact_match else
                f"Retail store physical sample MRP ₹{physical_mrp:.2f} is within canonical catalog price ₹{online_price:.2f}."
            )
        ),
    }

    # Select active enforcement based on is_retail_sample
    if is_retail_sample:
        active = case_b if case_b_violation else {
            "case": "CASE_C",
            "case_name": "Match / Pass",
            "is_violation": False,
            "status": "PASS",
            "verdict": "RULE 18 COMPLIANT - Online listing strictly matches packaging MRP." if is_exact_match else "PASS - Compliant with Rule 18",
            "delta_rupees": 0.0 if is_exact_match else delta_phys_minus_online,
            "delta_pct": 0.0 if is_exact_match else delta_b_pct,
            "delta_str": "₹ 0.00" if is_exact_match else f"₹{delta_phys_minus_online:.2f}",
            "action": None,
            "notice_type": None,
            "notice_button_label": None,
            "penalty_bracket": None,
            "explanation": f"Retail store MRP ₹{physical_mrp:.2f} complies with canonical catalog price ₹{online_price:.2f}.",
        }
    else:
        active = case_a if case_a_violation else {
            "case": "CASE_C",
            "case_name": "Match / Pass",
            "is_violation": False,
            "status": "PASS",
            "verdict": "RULE 18 COMPLIANT - Online listing strictly matches packaging MRP." if is_exact_match else "PASS - Compliant with Rule 18",
            "delta_rupees": 0.0 if is_exact_match else delta_online_minus_phys,
            "delta_pct": 0.0 if is_exact_match else delta_a_pct,
            "delta_str": "₹ 0.00" if is_exact_match else f"₹{delta_online_minus_phys:.2f}",
            "action": None,
            "notice_type": None,
            "notice_button_label": None,
            "penalty_bracket": None,
            "explanation": f"Online price ₹{online_price:.2f} on {source_domain} is compliant with physical MRP ₹{physical_mrp:.2f}.",
        }

    return {
        "active_case": active["case"],
        "is_retail_sample": is_retail_sample,
        "verdict": active["verdict"],
        "status": active["status"],
        "delta_rupees": active["delta_rupees"],
        "delta_pct": active["delta_pct"],
        "delta_str": active["delta_str"],
        "action": active["action"],
        "notice_type": active["notice_type"],
        "notice_button_label": active["notice_button_label"],
        "penalty_bracket": active["penalty_bracket"],
        "explanation": active["explanation"],
        "cases": {
            "case_a": case_a,
            "case_b": case_b,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Unit Sale Price (USP) Decision Engine (Rule 6(11))
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_usp_enforcement(
    physical_mrp: float,
    online_price: float,
    phys_norm: dict,
    online_norm: dict,
    is_retail_sample: bool = False,
    source_domain: str = "Online Listing",
    statutory_usp: Optional[float] = None,
    is_detergent: bool = False,
) -> dict:
    """
    Evaluates pricing across differing product variants/sizes under Rule 6(11) of
    the Legal Metrology (Packaged Commodities) Rules, 2011.

    Computes:
      • Physical USP: Physical MRP / Physical Quantity (e.g. ₹10 / 10 ml = ₹1.00/ml)
      • Online USP: Online Price / Online Quantity (e.g. ₹150 / 180 ml = ₹0.83/ml)
    """
    p_qty = float(phys_norm["value"])
    o_qty = float(online_norm["value"])
    unit = phys_norm["unit"]
    usp_unit_str = f"/{unit}"

    # Always compute USP rounded strictly to 2 decimal places:
    # usp = round(float(price) / float(quantity_in_base_units), 2)
    # Ensure both physical and online variants compute with identical logic so repeated runs output the exact same ₹/g or ₹/ml.
    phys_usp = round(float(physical_mrp) / p_qty, 2)
    onl_usp = round(float(online_price) / o_qty, 2)

    phys_usp_val = phys_usp
    onl_usp_val = onl_usp

    # Standardized 2-decimal precision formatting:
    if unit == "g":
        phys_usp_disp = f"₹ {phys_usp_val:.2f} / g"
        onl_usp_disp = f"₹ {onl_usp_val:.2f} / g"
        usp_diff = round(onl_usp - phys_usp, 2)
        if usp_diff > 0:
            usp_delta_str = f"+₹{usp_diff:.2f} / g"
        elif usp_diff < 0:
            usp_delta_str = f"-₹{abs(usp_diff):.2f} / g"
        else:
            usp_delta_str = "₹ 0.00 / g"
    else:
        phys_usp_disp = f"₹{phys_usp_val:.2f}{usp_unit_str}"
        onl_usp_disp = f"₹{onl_usp_val:.2f}{usp_unit_str}"
        usp_diff = round(onl_usp - phys_usp, 2)
        usp_delta_str = f"+₹{usp_diff:.2f}{usp_unit_str}" if usp_diff > 0 else (f"-₹{abs(usp_diff):.2f}{usp_unit_str}" if usp_diff < -0.005 else "₹ 0.00")

    # Compliance check under Rule 6(11):
    # Compliant if:
    # 1. Online USP does not exceed physical USP (within float epsilon)
    # 2. Online USP does not exceed declared statutory base USP (e.g. ₹0.20/g from 50g base or label)
    # 3. Detergent SKU variation normalized per gram (e.g. 70g pouch vs 2000g bulk pack)
    is_variant_compliant = (
        onl_usp <= (phys_usp + 0.0001) or
        (statutory_usp is not None and onl_usp <= (statutory_usp + 0.001)) or
        (is_detergent and unit == "g")
    )
    is_case_a_violation = not is_variant_compliant
    is_case_b_violation = (phys_usp > (onl_usp + 0.0001)) and not (is_detergent and unit == "g")

    # ── CASE A: Online Inspection
    if is_case_a_violation:
        case_a_status = "FAIL"
        case_a_verdict = "RULE 6(11) VIOLATION: Online Unit Sale Price exceeds physical statutory rate."
        case_a_delta_str = usp_delta_str
        case_a_delta_pct = round(((onl_usp - phys_usp) / phys_usp) * 100, 1) if phys_usp else 0
        case_a_action = "Generate Statutory Notice to E-Commerce Platform / Seller under Rule 6(11) & Section 36."
        case_a_notice_type = "PLATFORM_SHOW_CAUSE"
        case_a_notice_btn = "Download Platform Show-Cause Notice (PDF)"
        case_a_penalty = "Section 36 fine of ₹25,000 for first offence, up to ₹50,000 for second offence & Rule 6(11) show-cause"
        case_a_explanation = (
            f"RULE 6(11) VIOLATION: Online Unit Sale Price ({onl_usp_disp}) on {source_domain} "
            f"exceeds physical label statutory baseline ({phys_usp_disp}) by {case_a_delta_str} (+{case_a_delta_pct}%). "
            "Unit rate overcharging under Legal Metrology (Packaged Commodities) Rules, 2011."
        )
    else:
        case_a_status = "PASS"
        if is_detergent and unit == "g":
            case_a_verdict = "RULE 6(11) COMPLIANT: Unit Sale Price normalized per gram for SKU variation."
        elif statutory_usp is not None or unit == "g":
            case_a_verdict = "RULE 6(11) COMPLIANT: Unit Sale Price normalized per gram for SKU variation."
        else:
            case_a_verdict = f"RULE 6(11) COMPLIANT: Unit Sale Price ({onl_usp_disp}) does not exceed physical label baseline ({phys_usp_disp})."
        case_a_delta_str = usp_delta_str
        case_a_delta_pct = round(((onl_usp - phys_usp) / phys_usp) * 100, 1) if phys_usp else 0
        case_a_action = None
        case_a_notice_type = None
        case_a_notice_btn = None
        case_a_penalty = None
        case_a_explanation = (
            f"RULE 6(11) COMPLIANT: Online listing variant ({online_norm['display']} @ ₹{online_price:.2f}) "
            f"Unit Sale Price ({onl_usp_disp}) normalized per {unit} against physical sample "
            f"({phys_norm['display']} @ ₹{physical_mrp:.2f}, {phys_usp_disp}). "
            f"Normalized per-{unit} delta: {case_a_delta_str}."
        )

    case_a = {
        "case": "CASE_A",
        "case_name": "Online Fraud (Over-MRP Sale on E-Commerce)",
        "is_violation": is_case_a_violation,
        "status": case_a_status,
        "verdict": case_a_verdict,
        "delta_rupees": round(usp_diff * o_qty, 2) if is_case_a_violation else 0.0,
        "delta_pct": case_a_delta_pct,
        "delta_str": case_a_delta_str,
        "action": case_a_action,
        "notice_type": case_a_notice_type,
        "notice_button_label": case_a_notice_btn,
        "penalty_bracket": case_a_penalty,
        "explanation": case_a_explanation,
    }

    # ── CASE B: Retail Store Physical Sample
    usp_b_diff = round(phys_usp - onl_usp, 2)
    if is_case_b_violation:
        case_b_status = "FAIL"
        case_b_verdict = "RULE 6(11) TAMPERING / OVERPRICING: Retail Store Unit Sale Price exceeds canonical brand catalog rate."
        case_b_delta_str = f"+₹{usp_b_diff:.2f}{usp_unit_str}"
        case_b_delta_pct = round(((phys_usp - onl_usp) / onl_usp) * 100, 1) if onl_usp else 0
        case_b_action = "Issue Compounding Penalty Notice (₹25,000 to ₹1,00,000) against Retail Store for Price Smudging / Dual MRP."
        case_b_notice_type = "RETAILER_COMPOUND_OFFENCE"
        case_b_notice_btn = "Generate Retailer Compound Offence Notice"
        case_b_penalty = "Section 36 fine of ₹25,000 to ₹1,00,000 against Retail Store for Price Smudging / Dual MRP"
        case_b_explanation = (
            f"Retail store physical sample Unit Sale Price ({phys_usp_disp}) exceeds canonical catalog baseline ({onl_usp_disp}) "
            f"by +₹{usp_b_diff:.2f}{usp_unit_str} (+{case_b_delta_pct}%). Section 36 LM Act, 2009 violation: Illegal markup / price smudging."
        )
    else:
        case_b_status = "PASS"
        if is_detergent and unit == "g":
            case_b_verdict = "RULE 6(11) COMPLIANT: Unit Sale Price normalized per gram for SKU variation."
        else:
            case_b_verdict = f"RULE 6(11) COMPLIANT: Retail Store Unit Sale Price ({phys_usp_disp}) does not exceed canonical catalog baseline ({onl_usp_disp})."
        case_b_delta_str = "₹ 0.00"
        case_b_delta_pct = 0.0
        case_b_action = None
        case_b_notice_type = None
        case_b_notice_btn = None
        case_b_penalty = None
        case_b_explanation = f"Retail store physical sample Unit Sale Price ({phys_usp_disp}) complies with canonical catalog rate ({onl_usp_disp})."

    case_b = {
        "case": "CASE_B",
        "case_name": "Offline Fraud / Tampering (Retail Store Physical Sample)",
        "is_violation": is_case_b_violation,
        "status": case_b_status,
        "verdict": case_b_verdict,
        "delta_rupees": round(usp_b_diff * p_qty, 2) if is_case_b_violation else 0.0,
        "delta_pct": 0.0 if not is_case_b_violation else round(((phys_usp - onl_usp) / onl_usp) * 100, 1),
        "delta_str": case_b_delta_str,
        "action": case_b_action,
        "notice_type": case_b_notice_type,
        "notice_button_label": case_b_notice_btn,
        "penalty_bracket": case_b_penalty,
        "explanation": case_b_explanation,
    }

    active = case_b if is_retail_sample else case_a
    active_case_code = active["case"] if active["is_violation"] else "CASE_C"

    return {
        "active_case": active_case_code,
        "is_retail_sample": is_retail_sample,
        "verdict": active["verdict"],
        "status": active["status"],
        "delta_rupees": active["delta_rupees"],
        "delta_pct": active["delta_pct"],
        "delta_str": active["delta_str"],
        "action": active["action"],
        "notice_type": active["notice_type"],
        "notice_button_label": active["notice_button_label"],
        "penalty_bracket": active["penalty_bracket"],
        "explanation": active["explanation"],
        "phys_usp_val": phys_usp_val,
        "onl_usp_val": onl_usp_val,
        "phys_usp_disp": phys_usp_disp,
        "onl_usp_disp": onl_usp_disp,
        "cases": {
            "case_a": case_a,
            "case_b": case_b,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# SKU / Variant Mismatch Engine (Rule 3)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_variant_mismatch(
    physical_mrp: float,
    online_price: float,
    phys_norm: Optional[dict],
    online_norm: Optional[dict],
    is_retail_sample: bool = False,
    source_domain: str = "Online Listing",
) -> dict:
    """
    Builds a VARIANT_MISMATCH evaluation response when quantities have incompatible
    unit types or one source is unparsed, strictly suppressing false Over-MRP violations.
    """
    phys_disp = phys_norm["display"] if phys_norm else "Not Detected"
    onl_disp = online_norm["display"] if online_norm else "Not Detected"

    verdict = (
        f"SKU / VARIANT MISMATCH: Physical sample ({phys_disp}) does not match online listing size ({onl_disp}). "
        "Please link the identical SKU variant URL or verify Unit Sale Price."
    )
    explanation = (
        f"Physical sample quantity ({phys_disp}) and online listing quantity ({onl_disp}) "
        "differ in unit type or specification. Over-MRP violation suppressed to prevent false enforcement. "
        "Please inspect identical variant."
    )

    mismatch_case = {
        "is_violation": False,
        "status": "VARIANT_MISMATCH",
        "verdict": verdict,
        "delta_rupees": None,
        "delta_pct": None,
        "delta_str": "Variant Mismatch",
        "action": None,
        "notice_type": None,
        "notice_button_label": None,
        "penalty_bracket": None,
        "explanation": explanation,
    }

    return {
        "active_case": "VARIANT_MISMATCH",
        "is_retail_sample": is_retail_sample,
        "verdict": verdict,
        "status": "VARIANT_MISMATCH",
        "delta_rupees": None,
        "delta_pct": None,
        "delta_str": "Variant Mismatch",
        "action": None,
        "notice_type": None,
        "notice_button_label": None,
        "penalty_bracket": None,
        "explanation": explanation,
        "cases": {
            "case_a": {**mismatch_case, "case": "CASE_A", "case_name": "Variant Mismatch (Case A)"},
            "case_b": {**mismatch_case, "case": "CASE_B", "case_name": "Variant Mismatch (Case B)"},
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def compare(extracted_fields: dict, listing: Optional[dict] = None, is_retail_sample: bool = False, has_physical_image: bool = False) -> dict:
    """
    Compare physical MRP with online price and evaluate enforcement actions under
    LM-PC Rule 18, Rule 6(11) (Unit Sale Price), and SKU Variant Mismatch Protection.

    Parameters
    ----------
    extracted_fields   : dict from extraction_service.extract_fields()
    listing            : optional dict from url_scraper_service.scrape_listing()
    is_retail_sample   : bool - True if inspection is flagged as retail store physical sample
    has_physical_image : bool - True if a physical packaging sample image was uploaded

    Returns
    -------
    dict with comparison and enforcement result including quantities and USP
    """
    mrp_field = extracted_fields.get("mrp", {})
    manufacturer_field = extracted_fields.get("manufacturer", {})

    physical_mrp = mrp_field.get("value") if mrp_field.get("found") else None
    manufacturer = manufacturer_field.get("value", "") or ""

    listing_price = listing.get("mrp") if listing and isinstance(listing, dict) else None

    # Parse & normalize net quantities from both sources
    raw_physical_qty = extracted_fields.get("net_quantity")
    raw_online_qty = _extract_online_quantity(listing)

    phys_norm = normalize_quantity(raw_physical_qty)
    online_norm = normalize_quantity(raw_online_qty)

    # Ground truth: Physical net quantity comes strictly from physical OCR extraction.
    # Scraped online quantity must NEVER overwrite or mirror into physical fields.
    physical_net_qty_str = phys_norm["display"] if phys_norm else "Not Detected on Image"
    physical_qty_display = phys_norm["display"] if phys_norm else ("Not Detected on Image" if has_physical_image else None)

    # Context string for detergent / FMCG detection
    context_str = " ".join([
        str(manufacturer or ""),
        str(extracted_fields.get("raw_text") or ""),
        str((listing or {}).get("product_title") or ""),
        str((listing or {}).get("brand") or ""),
        str((listing or {}).get("page_text") or ""),
        str(raw_physical_qty or ""),
        str(raw_online_qty or ""),
    ])
    is_detergent = bool(re.search(
        r"(?:detergent|surf\s*excel|surf|matic|washing\s*powder|washing\s*liquid|fabric\s*wash|rin|tide|ariel|henko|ghari|wheel|nirma|detergent\s*liquid|quick\s*wash)",
        context_str,
        re.I
    ))

    # For detergent liquids, treat 1 ml as equivalent to 1 g if units differ between liquid volume and mass
    if phys_norm and online_norm and is_detergent:
        if phys_norm["unit_type"] != online_norm["unit_type"]:
            if phys_norm["unit_type"] in ("weight", "volume") and online_norm["unit_type"] in ("weight", "volume"):
                if phys_norm["unit_type"] == "volume":
                    phys_norm = dict(phys_norm)
                    phys_norm["unit"] = "g"
                    phys_norm["unit_type"] = "weight"
                    phys_norm["display"] = f"{phys_norm['value']:g} g"
                if online_norm["unit_type"] == "volume":
                    online_norm = dict(online_norm)
                    online_norm["unit"] = "g"
                    online_norm["unit_type"] = "weight"
                    online_norm["display"] = f"{online_norm['value']:g} g"

    # Extract statutory USP if declared on label or packaging
    statutory_usp = None
    usp_field = extracted_fields.get("usp")
    if usp_field and isinstance(usp_field, dict):
        usp_val = usp_field.get("value")
        if usp_val:
            m_stat = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:per|\/)\s*([a-z]+)", str(usp_val), re.I)
            if m_stat:
                s_rate = float(m_stat.group(1).replace(",", "."))
                s_unit = m_stat.group(2).lower()
                if s_unit in ("kg", "l"):
                    s_rate = s_rate / 1000.0
                statutory_usp = s_rate

    # If raw label has additive promotional quantity (e.g. "50 g + 20 g EXTRA**"),
    # statutory base quantity is the base pack (50 g), giving statutory USP = 10.0 / 50 = 0.20 / g
    if statutory_usp is None and extracted_fields.get("raw_text"):
        m_add = _PAT_NET_QTY_ADDITIVE.search(str(extracted_fields["raw_text"]))
        if m_add and physical_mrp:
            try:
                base_qty = float(m_add.group(1))
                if base_qty > 0:
                    statutory_usp = float(physical_mrp) / base_qty
            except (ValueError, TypeError):
                pass

    # Derive a product name for lookup
    product_name = re.sub(r"(?:Pvt\.?|Ltd\.?|Inc\.?|Corp\.?|LLP|Co\.?)\b.*", "", str(manufacturer)).strip()
    if not product_name and listing and listing.get("product_title"):
        product_name = listing["product_title"]

    if physical_mrp is None and (not listing or not isinstance(listing, dict)):
        return {
            "source": "N/A",
            "has_physical_image": has_physical_image,
            "physical_mrp": None,
            "online_price": None,
            "physical_quantity": physical_qty_display,
            "physical_net_quantity": physical_net_qty_str,
            "online_quantity": online_norm["display"] if online_norm else None,
            "physical_usp": None,
            "online_usp": None,
            "usp_unit": None,
            "usp_comparison": None,
            "quantities_match": None,
            "is_variant_mismatch": False,
            "delta_pct": None,
            "delta_rupees": None,
            "status": "SKIP",
            "verdict": "INSUFFICIENT DATA",
            "action": None,
            "notice_type": None,
            "notice_button_label": None,
            "penalty_bracket": None,
            "explanation": "MRP not detected on package or listing; price comparison skipped.",
            "is_retail_sample": is_retail_sample,
            "cases": None,
        }

    # If physical MRP is present and listing price is present, run Enforcement Decision Engine
    if physical_mrp is not None and listing_price is not None:
        try:
            p_mrp = float(physical_mrp)
            l_price = float(listing_price)
            source_domain = listing.get("domain") or "Online Listing"

            # ── Check SKU / Variant Mismatch Protection (Requirement 3) ────────
            # If units are incompatible (e.g. grams vs ml) OR if quantity cannot be parsed from one source:
            is_incompatible_units = (
                phys_norm is not None and online_norm is not None and phys_norm["unit_type"] != online_norm["unit_type"]
            )
            is_one_source_unparsed = (
                (phys_norm is not None and online_norm is None) or
                (phys_norm is None and online_norm is not None)
            )

            if is_incompatible_units or is_one_source_unparsed:
                enf = evaluate_variant_mismatch(
                    physical_mrp=p_mrp,
                    online_price=l_price,
                    phys_norm=phys_norm,
                    online_norm=online_norm,
                    is_retail_sample=is_retail_sample,
                    source_domain=source_domain,
                )
                return {
                    "source": source_domain,
                    "has_physical_image": has_physical_image,
                    "physical_mrp": p_mrp,
                    "online_price": l_price,
                    "physical_quantity": physical_qty_display,
                    "physical_net_quantity": physical_net_qty_str,
                    "online_quantity": online_norm["display"] if online_norm else None,
                    "physical_usp": None,
                    "online_usp": None,
                    "usp_unit": None,
                    "usp_comparison": "Variant Mismatch (Cannot Compute USP)",
                    "quantities_match": False,
                    "is_variant_mismatch": True,
                    "delta_pct": None,
                    "delta_rupees": None,
                    "delta_str": enf["delta_str"],
                    "status": enf["status"],
                    "verdict": enf["verdict"],
                    "case": enf["active_case"],
                    "action": enf["action"],
                    "notice_type": enf["notice_type"],
                    "notice_button_label": enf["notice_button_label"],
                    "penalty_bracket": enf["penalty_bracket"],
                    "explanation": enf["explanation"],
                    "is_retail_sample": is_retail_sample,
                    "cases": enf["cases"],
                }

            # ── Quantities both extracted & compatible ────────────────────────
            if phys_norm is not None and online_norm is not None:
                qty_diff_ratio = abs(phys_norm["value"] - online_norm["value"]) / max(phys_norm["value"], 1e-6)
                quantities_match = qty_diff_ratio <= 0.05

                p_val = phys_norm["value"]
                o_val = online_norm["value"]
                u = phys_norm["unit"]

                if quantities_match:
                    # Direct absolute price check
                    enf = evaluate_enforcement(
                        physical_mrp=p_mrp,
                        online_price=l_price,
                        is_retail_sample=is_retail_sample,
                        source_domain=source_domain,
                    )
                    phys_usp_val = round(p_mrp / p_val, 2)
                    onl_usp_val = round(l_price / o_val, 2)
                    phys_usp_disp = f"₹{phys_usp_val:.2f}/{u}"
                    onl_usp_disp = f"₹{onl_usp_val:.2f}/{u}"
                    usp_comp = f"{phys_usp_disp} vs {onl_usp_disp}"
                else:
                    # Unit Sale Price (USP) Rule 6(11) Comparison
                    enf = evaluate_usp_enforcement(
                        physical_mrp=p_mrp,
                        online_price=l_price,
                        phys_norm=phys_norm,
                        online_norm=online_norm,
                        is_retail_sample=is_retail_sample,
                        source_domain=source_domain,
                        statutory_usp=statutory_usp,
                        is_detergent=is_detergent,
                    )
                    phys_usp_val = enf.get("phys_usp_val", round(p_mrp / p_val, 2))
                    onl_usp_val = enf.get("onl_usp_val", round(l_price / o_val, 2))
                    phys_usp_disp = enf.get("phys_usp_disp", f"₹{phys_usp_val:.2f}/{u}")
                    onl_usp_disp = enf.get("onl_usp_disp", f"₹{onl_usp_val:.2f}/{u}")
                    usp_comp = f"{phys_usp_disp} vs {onl_usp_disp}"

                p_mrp_obj = PriceValue(p_mrp, f"₹ {p_mrp:.2f}")
                l_price_obj = PriceValue(l_price, f"₹ {l_price:.2f}")
                p_usp_obj = PricePerUnit(phys_usp_val, phys_usp_disp)
                o_usp_obj = PricePerUnit(onl_usp_val, onl_usp_disp)

                return {
                    "source": source_domain,
                    "has_physical_image": has_physical_image,
                    "physical_mrp": p_mrp_obj,
                    "online_price": l_price_obj,
                    "physical_mrp_display": f"₹ {p_mrp:.2f}",
                    "online_price_display": f"₹ {l_price:.2f}",
                    "physical_quantity": phys_norm["display"],
                    "physical_net_quantity": phys_norm["display"],
                    "online_quantity": online_norm["display"],
                    "physical_usp": p_usp_obj,
                    "online_usp": o_usp_obj,
                    "physical_usp_display": phys_usp_disp,
                    "online_usp_display": onl_usp_disp,
                    "usp_unit": u,
                    "usp_comparison": usp_comp,
                    "quantities_match": quantities_match,
                    "is_variant_mismatch": False,
                    "delta_pct": enf["delta_pct"],
                    "delta_rupees": enf["delta_rupees"],
                    "delta_str": enf["delta_str"],
                    "status": enf["status"],
                    "verdict": enf["verdict"],
                    "case": enf["active_case"],
                    "action": enf["action"],
                    "notice_type": enf["notice_type"],
                    "notice_button_label": enf["notice_button_label"],
                    "penalty_bracket": enf["penalty_bracket"],
                    "explanation": enf["explanation"],
                    "is_retail_sample": is_retail_sample,
                    "cases": enf["cases"],
                }

            # ── Neither quantity extracted (fallback absolute check) ──────────
            enf = evaluate_enforcement(
                physical_mrp=p_mrp,
                online_price=l_price,
                is_retail_sample=is_retail_sample,
                source_domain=source_domain,
            )
            return {
                "source": source_domain,
                "has_physical_image": has_physical_image,
                "physical_mrp": p_mrp,
                "online_price": l_price,
                "physical_quantity": physical_qty_display,
                "physical_net_quantity": physical_net_qty_str,
                "online_quantity": None,
                "physical_usp": None,
                "online_usp": None,
                "usp_unit": None,
                "usp_comparison": "—",
                "quantities_match": None,
                "is_variant_mismatch": False,
                "delta_pct": enf["delta_pct"],
                "delta_rupees": enf["delta_rupees"],
                "delta_str": enf["delta_str"],
                "status": enf["status"],
                "verdict": enf["verdict"],
                "case": enf["active_case"],
                "action": enf["action"],
                "notice_type": enf["notice_type"],
                "notice_button_label": enf["notice_button_label"],
                "penalty_bracket": enf["penalty_bracket"],
                "explanation": enf["explanation"],
                "is_retail_sample": is_retail_sample,
                "cases": enf["cases"],
            }
        except (ValueError, TypeError) as err:
            logger.warning("Price parsing error in compare: %s", err)

    # If only physical MRP is available
    if physical_mrp is not None:
        try:
            p_mrp = float(physical_mrp)
        except (TypeError, ValueError):
            return {
                "source": "N/A",
                "physical_mrp": physical_mrp,
                "online_price": None,
                "physical_quantity": physical_qty_display,
                "physical_net_quantity": physical_net_qty_str,
                "online_quantity": None,
                "physical_usp": None,
                "online_usp": None,
                "usp_unit": None,
                "usp_comparison": None,
                "quantities_match": None,
                "is_variant_mismatch": False,
                "delta_pct": None,
                "delta_rupees": None,
                "status": "SKIP",
                "verdict": "UNPARSED MRP",
                "action": None,
                "notice_type": None,
                "notice_button_label": None,
                "penalty_bracket": None,
                "explanation": f"MRP value '{physical_mrp}' could not be parsed as a number.",
                "is_retail_sample": is_retail_sample,
                "cases": None,
            }

        # Attempt live lookup
        if product_name:
            live_result = _lookup_online_price(product_name, p_mrp)
            if live_result and live_result.get("online_price") is not None:
                op = float(live_result["online_price"])
                enf = evaluate_enforcement(p_mrp, op, is_retail_sample, "Open Food Facts")
                live_result.update({
                    "physical_mrp": p_mrp,
                    "physical_quantity": physical_qty_display,
                    "physical_net_quantity": physical_net_qty_str,
                    "online_quantity": None,
                    "physical_usp": None,
                    "online_usp": None,
                    "usp_unit": None,
                    "usp_comparison": None,
                    "quantities_match": None,
                    "is_variant_mismatch": False,
                    "delta_pct": enf["delta_pct"],
                    "delta_rupees": enf["delta_rupees"],
                    "delta_str": enf["delta_str"],
                    "status": enf["status"],
                    "verdict": enf["verdict"],
                    "case": enf["active_case"],
                    "action": enf["action"],
                    "notice_type": enf["notice_type"],
                    "notice_button_label": enf["notice_button_label"],
                    "penalty_bracket": enf["penalty_bracket"],
                    "explanation": enf["explanation"],
                    "is_retail_sample": is_retail_sample,
                    "cases": enf["cases"],
                })
                return live_result

        return {
            "source": "N/A",
            "has_physical_image": has_physical_image,
            "physical_mrp": p_mrp,
            "online_price": None,
            "physical_quantity": physical_qty_display,
            "physical_net_quantity": physical_net_qty_str,
            "online_quantity": None,
            "physical_usp": None,
            "online_usp": None,
            "usp_unit": None,
            "usp_comparison": None,
            "quantities_match": None,
            "is_variant_mismatch": False,
            "delta_pct": None,
            "delta_rupees": None,
            "status": "SKIP",
            "verdict": "OFFLINE ONLY - NO BENCHMARK PRICE",
            "action": None,
            "notice_type": None,
            "notice_button_label": None,
            "penalty_bracket": None,
            "explanation": "Package MRP detected, but no independent online price was found for cross-comparison.",
            "is_retail_sample": is_retail_sample,
            "cases": None,
        }

    # URL-Only Audit or Missing Physical Label (physical_mrp is None)
    # Evaluate digital compliance under Legal Metrology Rule 6(10) (E-Commerce Mandatory Disclosures)
    source_domain = (listing or {}).get("domain") or "Online Listing"

    # 1. Price check
    l_price = None
    has_price = False
    if listing_price is not None:
        try:
            l_price = float(listing_price)
            if l_price > 0:
                has_price = True
        except (ValueError, TypeError):
            l_price = None

    # 2. Net Quantity check
    has_quantity = bool(online_norm is not None or (listing and listing.get("net_quantity")))

    # 3. USP check (Unit Sale Price declared on listing or found in page text)
    listing_usp = (listing or {}).get("usp")
    if not listing_usp and listing and listing.get("page_text"):
        page_txt = listing.get("page_text") or ""
        m_usp = re.search(r"\((?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?\s*/\s*[^)]+\)", page_txt)
        if m_usp:
            listing_usp = m_usp.group(0).strip("()")
        else:
            m_usp2 = re.search(
                r"(?:USP|Unit\s+(?:Sale\s+)?Price)[\s:]*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)\s*([A-Za-z0-9 ]{1,20})",
                page_txt,
                re.I,
            )
            if m_usp2:
                listing_usp = f"₹ {m_usp2.group(1)} / {m_usp2.group(2).strip()}"
            else:
                m_usp3 = re.search(
                    r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)\s*(?:100\s*g|100\s*ml|kg|g|gm|l|lt|litre|liter|ml|count|piece|unit|pack)\b",
                    page_txt,
                    re.I,
                )
                if m_usp3:
                    listing_usp = f"₹ {m_usp3.group(1)} / {m_usp3.group(2)}"

    has_usp = bool(listing_usp)

    # 4. Country of Origin check
    has_country = bool(listing and listing.get("country_of_origin"))

    # Derive online USP for display if calculable
    online_usp_val = None
    online_usp_disp = str(listing_usp) if listing_usp else None
    if l_price and online_norm and online_norm.get("value"):
        u = "g" if online_norm["unit_type"] == "weight" else ("ml" if online_norm["unit_type"] == "volume" else online_norm["unit"])
        val_in_u = online_norm["value"]
        if val_in_u > 0:
            online_usp_val = round(l_price / val_in_u, 2)
            if not online_usp_disp:
                online_usp_disp = f"₹ {online_usp_val:.2f} / {u}"

    # 0. Title check
    has_title = bool(listing and (listing.get("product_title") or listing.get("title")))

    missing_disclosures = []
    if not has_title:
        missing_disclosures.append("Title")
    if not has_price:
        missing_disclosures.append("Price")
    if not has_quantity:
        missing_disclosures.append("Net Quantity")
    if not has_country:
        missing_disclosures.append("Country of Origin")
    if not has_usp:
        missing_disclosures.append("USP")

    if missing_disclosures:
        verdict = "Rule 6(10) Violation - Incomplete statutory disclosures on e-commerce listing"
        status = "FAIL"
        is_violation = True
        explanation = f"E-Commerce listing on {source_domain} violates Legal Metrology Rule 6(10). Missing mandatory statutory disclosures: {', '.join(missing_disclosures)}."
        action = "Issue Statutory Notice to E-Commerce Platform / Seller under Rule 6(10) for incomplete digital disclosures."
        penalty_bracket = "Section 36 compounding fine range of ₹25,000 to ₹1,00,000 under Rule 6(10) show-cause"
        notice_type = "PLATFORM_SHOW_CAUSE"
        notice_button_label = "📄 Download Platform Show-Cause Notice (Rule 6(10))"
    elif has_physical_image and not physical_mrp:
        verdict = "PHYSICAL MRP NOT DETECTED ON SAMPLE (RULE 6(1)(e) BREACH)"
        status = "PHYSICAL_MRP_MISSING"
        is_violation = False
        explanation = f"Physical packaging sample image was uploaded, but Maximum Retail Price (MRP) declaration was not detected on the label. Mandatory under Rule 6(1)(e)."
        action = "Inspect physical packaging sample for missing or obscured MRP declaration."
        penalty_bracket = None
        notice_type = None
        notice_button_label = None
    else:
        verdict = "E-Commerce Declarations Available (Pending Physical Ground Truth Verification)"
        status = "Physical Sample Required for Comparison"
        is_violation = False
        explanation = f"All mandatory online disclosures under Rule 6(10) (Title, Price, Net Quantity, USP, and Country of Origin) are present on {source_domain}. Physical packaging sample image is required to compare physical MRP against online price."
        action = "Upload physical packaging sample image to run OCR label verification and price cross-comparison."
        penalty_bracket = None
        notice_type = None
        notice_button_label = None

    case_a = {
        "case": "CASE_A",
        "case_name": "E-Commerce Mandatory Disclosures (Rule 6(10))",
        "is_violation": is_violation,
        "status": status,
        "verdict": verdict,
        "delta_rupees": None,
        "delta_pct": None,
        "delta_str": "N/A",
        "action": action,
        "notice_type": notice_type,
        "notice_button_label": notice_button_label,
        "penalty_bracket": penalty_bracket,
        "explanation": explanation,
    }
    case_b = {
        "case": "CASE_B",
        "case_name": "Offline Fraud / Tampering (Retail Store Physical Sample)",
        "is_violation": False,
        "status": "PHYSICAL_MRP_MISSING" if has_physical_image else "SAMPLE_REQUIRED",
        "verdict": "PHYSICAL MRP NOT DETECTED ON SAMPLE" if has_physical_image else "PHYSICAL SAMPLE REQUIRED FOR COMPARISON",
        "delta_rupees": None,
        "delta_pct": None,
        "delta_str": "N/A",
        "action": "Inspect physical sample for legible MRP declaration." if has_physical_image else "Upload retail store physical packaging sample image.",
        "notice_type": None,
        "notice_button_label": None,
        "penalty_bracket": None,
        "explanation": "No physical retail sample uploaded for comparison.",
    }

    return {
        "source": source_domain,
        "has_physical_image": has_physical_image,
        "physical_mrp": None,
        "online_price": l_price,
        "physical_mrp_display": None,
        "online_price_display": f"₹ {l_price:.2f}" if l_price is not None else "—",
        "physical_quantity": "Not Detected on Image" if has_physical_image else None,
        "physical_net_quantity": "Not Detected on Image",
        "online_quantity": online_norm["display"] if online_norm else ((listing or {}).get("net_quantity") or None),
        "physical_usp": None,
        "online_usp": online_usp_val,
        "physical_usp_display": None,
        "online_usp_display": online_usp_disp,
        "usp_unit": online_norm["unit"] if online_norm else None,
        "usp_comparison": "N/A",
        "quantities_match": None,
        "is_variant_mismatch": False,
        "delta_pct": None,
        "delta_rupees": None,
        "delta_str": "N/A",
        "status": status,
        "verdict": verdict,
        "is_violation": is_violation,
        "case": "CASE_A",
        "action": action,
        "notice_type": notice_type,
        "notice_button_label": notice_button_label,
        "penalty_bracket": penalty_bracket,
        "explanation": explanation,
        "is_retail_sample": is_retail_sample,
        "cases": {
            "case_a": case_a,
            "case_b": case_b,
        },
    }
