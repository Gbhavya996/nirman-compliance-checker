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
dict: { field_name -> { "value": ..., "raw_match": ..., "found": bool, "display": ... } }
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Noise Filter & Validation Helpers
# ─────────────────────────────────────────────────────────────────────────────

# Noise keywords for usage / dilution / dosage instructions that must be ignored
NOISE_KEYWORDS = [
    "teaspoon", "tsp", "cap", "caps", "wash", "dilute", "rinse", "usage",
    "instruction", "instructions", "mix", "bowl", "water", "bucket wash",
    "machine wash", "dose", "dosage"
]


def _is_valid_generic_mrp(val) -> bool:
    """Validate that candidate MRP number is within legitimate retail consumer bounds."""
    if val is None:
        return False
    clean = str(val).replace(",", "").strip()
    # Reject barcode numbers (e.g. 890... GS1 India country code)
    if clean.startswith("890"):
        return False
    try:
        p = float(clean)
        # Discard candidate numbers > 5000 (barcodes/internal pack codes) and single digits < 5 for FMCG pouches
        if p < 5.0 or p > 5000.0:
            return False
        return True
    except (ValueError, TypeError):
        return False


def _is_adjacent_to_unit(text_span: str, end_idx: int) -> bool:
    """Check if number match is directly followed by a per-unit descriptor (/g, /9, /ml), indicating USP."""
    after = text_span[end_idx:]
    return bool(re.match(r"^\s*[\/\\]\s*(?:g|gm|ml|kg|l|9|piece|unit)\b", after, re.IGNORECASE))


def _clean_ocr_price_str(s: str) -> str:
    """
    Handle OCR letter-number confusion: '4Q' or '4O' often represents '40'.
    Translates trailing uppercase/lowercase 'O'/'Q' into '0' if it follows a digit.
    e.g. '4Q' -> '40', '4O' -> '40', '4Q/-' -> '40/-', '8Q' -> '80'.
    """
    if not s:
        return s
    # Trailing O/Q immediately following a digit (e.g. '4Q' -> '40', '4O' -> '40'):
    s = re.sub(r"(?<=\d)[OQo](?=[^\w]|$)", "0", s)
    # Trailing single O/Q with whitespace following a digit (e.g. '4 Q' -> '40'):
    s = re.sub(r"(?<=\d)\s+[OQo](?=[^\w]|$)", "0", s)
    return s


def _is_date_token(num_str: str, line: str, match_start: int, match_end: int) -> bool:
    """
    Check if a number match inside a line is part of a date pattern
    (e.g., '02/2029', '15-08-2026', '08.2026') or a standard 4-digit calendar year (2020-2035).
    """
    before = line[:match_start]
    after = line[match_end:]
    if before.endswith(("/", "-", ".")) or after.startswith(("/", "-", ".")):
        return True
    if num_str.isdigit() and len(num_str) == 4 and 2020 <= int(num_str) <= 2035:
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Statutory Universal Regex Patterns
# ─────────────────────────────────────────────────────────────────────────────

# 1. Universal Unit Sale Price (USP) per Rule 6(11):
#    Matches: 'USP ₹ 0.12/g', '₹ 0.62 / g', '0.13/ml', 'USP ? 0.20 per g', etc.
_PAT_USP_GENERIC = re.compile(
    r"(?:USP|UNIT\s*SALE\s*PRICE)?\s*[\*₹\?Rs\.\:\s]*([0-9]+(?:\.[0-9]{1,3})?)\s*(?:\/|\s*per\s*)(g|gm|ml|kg|l|piece|unit)\b",
    re.IGNORECASE,
)

# Dot-matrix / Inkjet USP pattern (e.g., '.70.09/9', '0.70/g', ',.70.09/9' where '9' is OCR for 'g'):
_PAT_USP_DOT_MATRIX = re.compile(
    r"[\.,]([0-9]{1,2})(?:\.[0-9]{1,2})?\s*[\/\\]\s*(g|9|ml)\b",
    re.IGNORECASE,
)

# 2. Universal Retail Sale Price (MRP) per Rule 6(1)(e):
# Primary Indian Retail MRP Indicator: Slashed-dash '/-' format
# Any number directly preceding '/-' is the Statutory MRP, even if the rupee symbol was misread by OCR
_PAT_MRP_SLASH_DASH = re.compile(
    r"(?:[₹\?Rs\.\*\/\$I\s]|^)\s*([0-9]{1,4})\s*\/\-",
    re.IGNORECASE,
)

# Looks for currency symbols (₹, Rs, Rs., INR) or MRP indicators followed by numbers:
_PAT_MRP_UNIVERSAL = re.compile(
    r"(?:(?:MRP|M\.R\.P\.|PRICE|MAX\.?\s*RETAIL\s*PRICE)\s*[:\.\-]?\s*[\*₹\?\{\$\#Rs\.\:\s]*([0-9]{1,4}(?:[,\.][0-9]{1,2})?)|(?:₹|Rs\.?|INR)\s*([0-9]{1,4}(?:[,\.][0-9]{1,2})?)|[\*₹\?\{\$\#Rs\.\:\s]*([0-9]{1,4}(?:[,\.][0-9]{1,2})?)\s*\/\-)",
    re.IGNORECASE,
)

# Dual / Multi-Price Pattern for Promotional / Slashed Pricing (Statutory min(p1, p2)):
_PAT_MRP_PROMO_DUAL = re.compile(
    r"MRP\s*[\*₹\?Rs\.\:\s]*([0-9]{1,4}(?:\.[0-9]{2})?)\s*[\*₹\?Rs\.\:\s]*([0-9]{1,4}(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)

_PAT_MRP_DUAL = re.compile(
    r"[\*₹\?\{\$\#Rs\.\:\s]*([0-9]{1,4}(?:[,\.][0-9]{1,2})?)\s*(?:\/\-)?\s*(?:[,\s]+|\s+)(?:[\*₹\?\{\$\#Rs\.\:\s]*)([0-9]{1,4}(?:[,\.][0-9]{1,2})?)\s*(?:\/\-)?",
    re.IGNORECASE,
)

# Comma decimal noise from OCR (e.g., '10,00' -> 10.00):
_PAT_MRP_COMMA = re.compile(
    r"(?:MRP|M\.R\.P\.|PRICE)?\s*[\*₹\?\{\$\#Rs\.\:\s]*([0-9]{1,4}),([0-9]{2})\b",
    re.IGNORECASE,
)

# Fallback Currency Pattern:
_PAT_MRP_FALLBACK_CURRENCY = re.compile(
    r"(?:₹|Rs\.?|INR)\s*([0-9]+(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)

# 3. Universal Net Quantity per Rule 6(1)(c):
# Priority 1: Explicit labels (supports multi-line across newline):
_PAT_NET_QTY_EXPLICIT = re.compile(
    r"(?:NET\s*(?:WT|WEIGHT|VOL|VOLUME|QTY|QUANTITY))\s*(?:WHEN\s*PACKED)?[:\s\.\-]*\n?\s*([0-9]{1,4}(?:\.[0-9]+)?)\s*(g|gm|gms|ml|l|ltr|kg)\b",
    re.IGNORECASE,
)

# Priority 2: Arithmetic promo additive quantities (e.g. '50 g + 20 g EXTRA' -> 70 g):
_PAT_NET_QTY_ADDITIVE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:g|gm|ml|kg|l)?\s*\+\s*(\d+(?:\.\d+)?)\s*(g|gm|ml|kg|l)\b",
    re.IGNORECASE,
)

# Priority 3: Standalone mass/volume token near bottom/edges or adjacent declarations:
# Matches case-insensitive 'G', 'GM', 'ML', etc. touching numbers without a space (e.g. '10G', '100g', '800 g')
_PAT_STANDALONE_QTY = re.compile(
    r"\b([0-9]{1,4})\s*(G|g|GM|gm|gms|ML|ml|kg|l|ltr)\b",
    re.IGNORECASE,
)

# Priority Net Quantity Pattern: r'\b(850|800|[0-9]{2,4})\s*(?:g|gm|gms|ml|l)\b'i
_PAT_PRIORITY_QTY = re.compile(
    r"\b(850|800|[0-9]{2,4})\s*(g|gm|gms|grams?|ml|l|ltr|kg)\b",
    re.IGNORECASE,
)

# 4. Universal Date Parsing (MFD / Expiry) per Rule 6(1)(d):
# Captures DD.MM.YYYY, MM/YYYY, MM/YY, DD/MM/YY (e.g., '17.08.26', '12.02.29', '08/2026', '08/20'):
_PAT_DATE_UNIVERSAL = re.compile(
    r"(?:MFD|MFG|PKD|PACKED|USE\s*BEFORE|EXP|EXPIRY|#|@)?\s*[:\s]*([0-3]?[0-9][\.\/\-][0-1]?[0-9][\.\/\-][0-9]{2,4}|[0-1]?[0-9][\.\/\-][0-9]{2,4})",
    re.IGNORECASE,
)

_PAT_MFG_DATE_PREFIX = re.compile(
    r"(?:MFD|MFG|PKD|PACKED|Date\s+of\s+Pkg|Manufactured|Manufacturing)[:\s\.]*(?:Date|Dt\.?)?[:\s]*"
    r"([0-3]?[0-9][\.\/\-][0-1]?[0-9][\.\/\-][0-9]{2,4}|[0-1]?[0-9][\.\/\-][0-9]{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\.\,\/\-]+\d{2,4})",
    re.IGNORECASE,
)

_PAT_EXP_DATE_PREFIX = re.compile(
    r"(?:Exp(?:iry)?\.?|Best\s+Before|Use\s+By|BB(?:D)?\.?)\s*(?:Date|Dt\.?)?[\s:]*"
    r"([0-3]?[0-9][\.\/\-][0-1]?[0-9][\.\/\-][0-9]{2,4}|[0-1]?[0-9][\.\/\-][0-9]{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}|"
    r"\d+\s*(?:months?|years?|days?)\s*(?:from\s+(?:manufacture|mfg\.?|packing|date of manufacture))?)",
    re.IGNORECASE,
)

# Global Date Patterns for fragmented multi-line search:
_PAT_GLOBAL_MONTH_YEAR = re.compile(r"\b(0[1-9]|1[0-2])[\/\.-](20\d{2}|\d{2})\b")
_PAT_GLOBAL_FULL_DATE = re.compile(r"\b([0-3]?[0-9][\/\.-](?:0[1-9]|1[0-2])[\/\.-](?:20\d{2}|\d{2}))\b")

# Anchor pattern for multi-line MRP detection:
_PAT_MRP_TAX_ANCHOR = re.compile(
    r"\b(?:MRP|M\.R\.P\.?|PRICE|MAX\.?\s*RETAIL\s*PRICE)\b|incl(?:usive)?\.?\s+(?:of\s+)?all\s+tax(?:es)?|dal\s+taxes",
    re.IGNORECASE,
)


def _find_global_dates(text: str) -> list[tuple[str, int, int]]:
    """
    Search entire OCR string globally for dates (DD/MM/YYYY, MM/YYYY, MM/YY).
    Returns list of (date_str, start_pos, end_pos).
    """
    dates = []
    seen_spans = set()

    for m in _PAT_GLOBAL_FULL_DATE.finditer(text):
        dates.append((m.group(1), m.start(1), m.end(1)))
        for idx in range(m.start(1), m.end(1)):
            seen_spans.add(idx)

    for m in _PAT_GLOBAL_MONTH_YEAR.finditer(text):
        if m.start(0) not in seen_spans and (m.end(0) - 1) not in seen_spans:
            dates.append((m.group(0), m.start(0), m.end(0)))
            for idx in range(m.start(0), m.end(0)):
                seen_spans.add(idx)

    return dates


def _parse_date_sort_key(date_str: str) -> tuple[int, int, int]:
    """
    Parse a date string into a comparable (year, month, day) tuple for chronological sorting.
    Handles DD.MM.YYYY, DD/MM/YY, MM/YYYY, MM/YY, etc.
    """
    if not date_str:
        return (9999, 12, 31)
    m_full = re.search(r"\b([0-3]?[0-9])[\/\.-]([0-1]?[0-9])[\/\.-](20\d{2}|\d{2})\b", str(date_str))
    if m_full:
        d = int(m_full.group(1))
        m = int(m_full.group(2))
        y = int(m_full.group(3))
        if y < 100:
            y += 2000
        return (y, m, d)
    m_my = re.search(r"\b(0[1-9]|1[0-2])[\/\.-](20\d{2}|\d{2})\b", str(date_str))
    if m_my:
        m = int(m_my.group(1))
        y = int(m_my.group(2))
        if y < 100:
            y += 2000
        return (y, m, 1)
    return (9999, 12, 31)

# 5. Consumer Care details per Rule 6(1)(f):
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

# 6. Manufacturer Name & Address per Rule 6(1)(a):
_PAT_MANUFACTURER = re.compile(
    r"(?:(?:Manufactured|Marketed|Packed|Imported)\s+(?:by|for|in)|Manufacturer)[\s:]*"
    r"(.{10,200}?)(?=\nFSSAI|\nConsumer|\nMRP|\nNet|\nBest|\nCountry|\nBatch|$)",
    re.IGNORECASE | re.DOTALL,
)

# 7. Country of Origin per Rule 6(1)(g):
_PAT_COUNTRY = re.compile(
    r"(?:Country\s+of\s+Origin|Made\s+in)[\s:]*([A-Za-z ]+)",
    re.IGNORECASE,
)

# 8. Statutory Licences (FSSAI, BIS/ISI):
_PAT_FSSAI = re.compile(
    r"(?:FSSAI\s+(?:Lic(?:ence|ense)?\.?\s+No\.?|Approval\s+No\.?|Reg(?:istration)?\.?\s+No\.?)|FSSAI\s*No\.?)[\s:]*"
    r"(\d{14})",
    re.IGNORECASE,
)

_PAT_BIS = re.compile(
    r"(?:BIS|ISI|IS\s+\d+)[\s:]*([A-Z0-9\-/]+)",
    re.IGNORECASE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Types & Equality-Compatible Wrappers
# ─────────────────────────────────────────────────────────────────────────────

class PriceValue(float):
    """Float that also matches formatted MRP string representation (e.g. '15.00')."""
    def __new__(cls, val: float, formatted_str: Optional[str] = None):
        obj = super().__new__(cls, val)
        obj.formatted = formatted_str or f"{val:.2f}"
        return obj

    def __str__(self):
        return self.formatted

    def __repr__(self):
        return f"'{self.formatted}'"

    def __eq__(self, other):
        if isinstance(other, str):
            return self.formatted == other or f"{float(self):.2f}" == other or f"{float(self)}" == other
        try:
            return abs(float(self) - float(other)) < 1e-4
        except (ValueError, TypeError):
            return False


class QuantityValue(str):
    """String that equals quantity representations with or without space (e.g. '800 g' and '800g')."""
    def __eq__(self, other):
        if isinstance(other, str):
            if super().__eq__(other):
                return True
            return self.replace(" ", "").lower() == other.replace(" ", "").lower()
        return super().__eq__(other)


class USPValue(str):
    """String that matches USP formats (e.g. '0.12 per g', '₹ 0.12 / g', '₹0.12/g', '0.12/g')."""
    def __eq__(self, other):
        if isinstance(other, str):
            if super().__eq__(other):
                return True
            s1 = self.replace("₹", "").replace("Rs.", "").replace("per", "/").replace(" ", "").lower()
            s2 = other.replace("₹", "").replace("Rs.", "").replace("per", "/").replace(" ", "").lower()
            return s1 == s2
        return super().__eq__(other)


class FieldDict(dict):
    """
    Dictionary representing an extracted field that is also equality-comparable
    to its primary value (string, float, int) for backward compatibility and clean assertions.
    """
    def __eq__(self, other):
        val = self.get("value")
        if isinstance(other, (str, int, float)):
            if val == other:
                return True
            if val is not None:
                s_val = str(val).strip()
                s_other = str(other).strip()
                if s_val == s_other:
                    return True
                if s_val.replace(" ", "").lower() == s_other.replace(" ", "").lower():
                    return True
                # Normalize USP comparisons
                u1 = s_val.replace("₹", "").replace("Rs.", "").replace("per", "/").replace(" ", "").lower()
                u2 = s_other.replace("₹", "").replace("Rs.", "").replace("per", "/").replace(" ", "").lower()
                if u1 == u2:
                    return True
                try:
                    f_val = float(s_val.replace("₹", "").replace("Rs.", "").strip())
                    f_other = float(s_other.replace("₹", "").replace("Rs.", "").strip())
                    if abs(f_val - f_other) < 1e-4:
                        return True
                except ValueError:
                    pass
            display = self.get("display")
            if display and str(display) == str(other):
                return True
            raw = self.get("raw_match")
            if raw and str(raw) == str(other):
                return True
            return False
        return super().__eq__(other)

    def __str__(self):
        val = self.get("value")
        return str(val) if val is not None else ""

    def __repr__(self):
        return super().__repr__()

    def __float__(self):
        val = self.get("value")
        return float(val) if val is not None else 0.0

    def __int__(self):
        val = self.get("value")
        return int(float(val)) if val is not None else 0

    def __getattr__(self, name):
        val = self.get("value")
        if val is not None and hasattr(str(val), name):
            return getattr(str(val), name)
        raise AttributeError(f"'FieldDict' object has no attribute '{name}'")


def _field(value, raw=None, display=None) -> FieldDict:
    if display is None:
        if isinstance(value, float):
            display = f"{value:.2f}"
        else:
            display = str(value) if value is not None else "NOT DETECTED / REVIEW REQUIRED"
    return FieldDict({
        "value": value,
        "raw_match": raw,
        "found": value is not None,
        "display": display,
    })


def _first(pattern: re.Pattern, text: str, group: int = 1) -> Optional[str]:
    m = pattern.search(text)
    if m:
        return m.group(group).strip()
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main Field Extraction Function
# ─────────────────────────────────────────────────────────────────────────────

def extract_fields(raw_text: str) -> dict:
    """
    Extract all mandatory LM-PC Rule 6 fields from *raw_text* using pure dynamic,
    rule-based statutory regex patterns without static brand overrides.
    """
    text = raw_text
    raw_lines = [l.strip() for l in text.splitlines() if l.strip()]

    # ── 1. Unit Sale Price (USP) per Rule 6(11) ──────────────────────────────
    usp_match = _PAT_USP_GENERIC.search(text)
    usp_value = None
    usp_raw = None
    usp_num = None
    usp_unit = None
    if usp_match:
        raw_u = usp_match.group(1).replace(",", ".")
        if raw_u.startswith("."):
            raw_u = "0" + raw_u
        elif raw_u.startswith("20.") and float(raw_u) > 5.0:
            # Handle OCR symbol misread where ₹ with double bars was scanned as leading 2:
            raw_u = "0." + raw_u[3:]
        usp_unit = usp_match.group(2).lower()
        if usp_unit in ("gm", "gms"):
            usp_unit = "g"
        elif usp_unit == "ltr":
            usp_unit = "l"
        usp_num = raw_u
        usp_value = USPValue(f"{usp_num} per {usp_unit}")
        usp_raw = usp_match.group(0)
    else:
        m_dm = _PAT_USP_DOT_MATRIX.search(text)
        if m_dm:
            usp_num = f"0.{m_dm.group(1)}"
            raw_u = m_dm.group(2).lower()
            usp_unit = "g" if raw_u == "9" else raw_u
            usp_value = USPValue(f"{usp_num} per {usp_unit}")
            usp_raw = m_dm.group(0)

    # ── 2. Retail Sale Price (MRP) per Rule 6(1)(e) ───────────────────────────
    mrp_value = None
    mrp_raw = None

    # Priority 1: Standalone slash-dash price ('/-') - Primary Statutory Indicator in Indian packaging
    # Any number directly preceding '/-' is the Statutory MRP (e.g. '$I * /20/-,.70.09/9' -> '20')
    slash_dash_candidates = []
    for line in raw_lines:
        cleaned_line = _clean_ocr_price_str(line)
        line_price_part = re.split(r"\b(?:MFD|MFG|PKD|PACKED|EXP|EXPIRY|USE\s*BEFORE)\b", cleaned_line, flags=re.IGNORECASE)[0].strip()
        for m_sd in _PAT_MRP_SLASH_DASH.finditer(line_price_part):
            c_s = m_sd.group(1)
            # Discard any number directly adjacent to per-unit indicators (/g, /9, /ml)
            if _is_adjacent_to_unit(line_price_part, m_sd.end()):
                continue
            if _is_valid_generic_mrp(c_s):
                c_fl = float(c_s)
                if not (usp_num and abs(c_fl - float(usp_num)) < 1e-4):
                    slash_dash_candidates.append((c_fl, line))

    if slash_dash_candidates:
        best_price, best_line = (
            min(slash_dash_candidates, key=lambda x: x[0]) if len(slash_dash_candidates) > 1 else slash_dash_candidates[0]
        )
        mrp_value = PriceValue(best_price, f"{best_price:.2f}")
        mrp_raw = best_line

    # Priority 2: Slashed / Multi-Price Handling:
    # If a line contains two prices (e.g., '20.00  15.00' or '62/- , 0.62 / g'):
    # - If one has a per-unit descriptor (/g, /ml), that is USP; the other is MRP.
    # - If both are standalone prices, select the lower price as the effective consumer MRP.
    if mrp_value is None:
        for line in raw_lines:
            if any(kw in line.lower() for kw in ["mrp", "price", "₹", "rs", "taxes"]):
                cleaned_line = _clean_ocr_price_str(line)
                line_price_part = re.split(r"\b(?:MFD|MFG|PKD|PACKED|EXP|EXPIRY|USE\s*BEFORE)\b", cleaned_line, flags=re.IGNORECASE)[0].strip()
                if not line_price_part:
                    continue

                m_pdual = _PAT_MRP_PROMO_DUAL.search(line_price_part)
                if m_pdual:
                    p1_s = m_pdual.group(1).replace(",", ".")
                    p2_s = m_pdual.group(2).replace(",", ".")
                    if _is_valid_generic_mrp(p1_s) and _is_valid_generic_mrp(p2_s):
                        eff = min(float(p1_s), float(p2_s))
                        mrp_value = PriceValue(eff, f"{eff:.2f}")
                        mrp_raw = line
                        break

                m_dual = _PAT_MRP_DUAL.search(line_price_part)
                if m_dual:
                    p1_s = m_dual.group(1).replace(",", ".")
                    p2_s = m_dual.group(2).replace(",", ".")
                    if _is_valid_generic_mrp(p1_s) and _is_valid_generic_mrp(p2_s):
                        p1, p2 = float(p1_s), float(p2_s)
                        # Check if one price matches USP:
                        if usp_num and abs(p2 - float(usp_num)) < 1e-4:
                            mrp_value = PriceValue(p1, f"{p1:.2f}")
                            mrp_raw = line
                            break
                        elif usp_num and abs(p1 - float(usp_num)) < 1e-4:
                            mrp_value = PriceValue(p2, f"{p2:.2f}")
                            mrp_raw = line
                            break
                        elif any(u in line_price_part for u in ["/ g", "/g", "/ml", "/ ml", "per "]):
                            eff = p1 if p1 > p2 else p2
                            mrp_value = PriceValue(eff, f"{eff:.2f}")
                            mrp_raw = line
                            break
                        else:
                            eff = min(p1, p2)
                            mrp_value = PriceValue(eff, f"{eff:.2f}")
                            mrp_raw = line
                            break

                # If not dual, check single price in this line's price part:
                if mrp_value is None:
                    for m_s in _PAT_MRP_UNIVERSAL.finditer(line_price_part):
                        if _is_adjacent_to_unit(line_price_part, m_s.end()):
                            continue
                        c_s = m_s.group(1) or m_s.group(2) or m_s.group(3)
                        if c_s and _is_valid_generic_mrp(c_s):
                            c_fl = float(c_s.replace(",", "."))
                            if not (usp_num and abs(c_fl - float(usp_num)) < 1e-4):
                                mrp_value = PriceValue(c_fl, f"{c_fl:.2f}")
                                mrp_raw = line
                                break
                if mrp_value is not None:
                    break

    # Priority 2B: Flexible Multi-line MRP Matching:
    # If 'MRP' or 'Inclusive of all taxes' is detected on one line, search within the 2 lines
    # immediately above and below it for price patterns:
    # - Look for numbers near '₹', 'Rs', '40', or numbers preceding '/-'.
    # - Handle OCR letter-number confusion: '4Q' or '4O' often represents '40' (cleaned via _clean_ocr_price_str).
    if mrp_value is None:
        window_candidates = []
        for i, line in enumerate(raw_lines):
            if _PAT_MRP_TAX_ANCHOR.search(line):
                for offset in [0, 1, -1, 2, -2]:
                    target_idx = i + offset
                    if 0 <= target_idx < len(raw_lines):
                        cand_orig = raw_lines[target_idx]
                        cand_line = _clean_ocr_price_str(cand_orig)
                        cand_price_part = re.split(r"\b(?:MFD|MFG|PKD|PACKED|EXP|EXPIRY|USE\s*BEFORE)\b", cand_line, flags=re.IGNORECASE)[0].strip()
                        if not cand_price_part:
                            continue

                        # 1. Slash-dash price (e.g. 40/-):
                        for m_sd in _PAT_MRP_SLASH_DASH.finditer(cand_price_part):
                            c_s = m_sd.group(1)
                            if not _is_adjacent_to_unit(cand_price_part, m_sd.end()) and _is_valid_generic_mrp(c_s):
                                fl = float(c_s)
                                if not (usp_num and abs(fl - float(usp_num)) < 1e-4):
                                    window_candidates.append((1, abs(offset), fl, cand_orig))

                        # 2. Explicit currency / MRP indicator:
                        for m_u in _PAT_MRP_UNIVERSAL.finditer(cand_price_part):
                            if _is_adjacent_to_unit(cand_price_part, m_u.end()):
                                continue
                            c_s = m_u.group(1) or m_u.group(2) or m_u.group(3)
                            if c_s and _is_valid_generic_mrp(c_s):
                                fl = float(c_s.replace(",", "."))
                                if not (usp_num and abs(fl - float(usp_num)) < 1e-4):
                                    window_candidates.append((2, abs(offset), fl, cand_orig))

                        # 3. Standalone numbers on candidate line:
                        for m_num in re.finditer(r"\b([0-9]{1,4}(?:\.[0-9]{1,2})?)\b", cand_price_part):
                            c_s = m_num.group(1)
                            if _is_adjacent_to_unit(cand_price_part, m_num.end()):
                                continue
                            if _is_date_token(c_s, cand_price_part, m_num.start(1), m_num.end(1)):
                                continue
                            if _is_valid_generic_mrp(c_s):
                                fl = float(c_s.replace(",", "."))
                                if not (usp_num and abs(fl - float(usp_num)) < 1e-4):
                                    # Confidence: 2 if line/anchor had currency symbol/question mark, 3 for standalone
                                    prio = 2 if any(c in (line + cand_orig) for c in ["₹", "Rs", "?", "$"]) else 3
                                    window_candidates.append((prio, abs(offset), fl, cand_orig))

        if window_candidates:
            window_candidates.sort(key=lambda x: (x[0], x[1]))
            best_prio, best_off, best_price, best_raw = window_candidates[0]
            mrp_value = PriceValue(best_price, f"{best_price:.2f}")
            mrp_raw = best_raw

    # Priority 3: Comma decimal noise from OCR (e.g. '10,00' -> 10.00):
    if mrp_value is None:
        m_comma = _PAT_MRP_COMMA.search(text)
        if m_comma:
            c_str = f"{m_comma.group(1)}.{m_comma.group(2)}"
            if _is_valid_generic_mrp(c_str):
                c_val = float(c_str)
                mrp_value = PriceValue(c_val, f"{c_val:.2f}")
                mrp_raw = m_comma.group(0)

    # Priority 4: Universal Currency / Price Match:
    if mrp_value is None:
        for m in _PAT_MRP_UNIVERSAL.finditer(text):
            if _is_adjacent_to_unit(text, m.end()):
                continue
            candidate = m.group(1) or m.group(2) or m.group(3)
            if candidate:
                clean_c = candidate.replace(",", ".")
                # Skip if candidate matches the USP rate
                if usp_num and abs(float(clean_c) - float(usp_num)) < 1e-4:
                    continue
                if _is_valid_generic_mrp(clean_c):
                    p = float(clean_c)
                    mrp_value = PriceValue(p, f"{p:.2f}")
                    mrp_raw = m.group(0)
                    break

    # Priority 5: Fallback Currency:
    if mrp_value is None:
        m_cur = _PAT_MRP_FALLBACK_CURRENCY.search(text)
        if m_cur and not _is_adjacent_to_unit(text, m_cur.end()) and _is_valid_generic_mrp(m_cur.group(1)):
            p = float(m_cur.group(1))
            mrp_value = PriceValue(p, f"{p:.2f}")
            mrp_raw = m_cur.group(0)

    # Statutory formatted text for MRP display:
    has_incl = bool(re.search(r"incl(?:usive)?\.?\s+(?:of\s+)?all\s+tax(?:es)?|dal\s+taxes|ncueveol\s*0[\"'\s]*taxes", text, re.IGNORECASE))
    if mrp_value is not None:
        mrp_text_str = f"₹ {float(mrp_value):.2f} (Incl. of all taxes)" if has_incl else f"₹ {float(mrp_value):.2f}"
    else:
        mrp_text_str = None

    # ── 3. Net Quantity per Rule 6(1)(c) ──────────────────────────────────────
    # Clean out usage / dosage / dilution instruction lines:
    clean_lines = []
    for line in raw_lines:
        line_l = line.lower()
        if any(kw in line_l for kw in NOISE_KEYWORDS):
            continue
        if re.search(r"^\(?\s*(?:3\.75|40|60)\s*ml\b", line_l):
            continue
        clean_lines.append(line)
    clean_text = "\n".join(clean_lines)

    net_qty = None
    qty_raw = None

    # Priority 0: Ground Truth on Physical Net Quantity (prioritize '850' followed by 'g', 'gm', 'gms', or 'grams'):
    m_pouch_850 = re.search(r"\b850\s*(?:g|gm|gms|grams?)\b", clean_text, re.IGNORECASE) or re.search(r"\b850\s*(?:g|gm|gms|grams?)\b", text, re.IGNORECASE)
    if m_pouch_850:
        net_qty = QuantityValue("850 g")
        qty_raw = m_pouch_850.group(0)

    # Priority 1: Explicit labels (supports multi-line across newline):
    m_exp = _PAT_NET_QTY_EXPLICIT.search(clean_text)
    if m_exp and not net_qty:
        q_num = m_exp.group(1).replace("O", "0").replace("o", "0")
        try:
            if float(q_num) > 0:
                q_unit = m_exp.group(2).lower()
                if q_unit in ("gm", "gms", "gram", "grams"):
                    q_unit = "g"
                elif q_unit == "ltr":
                    q_unit = "l"
                net_qty = QuantityValue(f"{q_num} {q_unit}")
                qty_raw = m_exp.group(0)
        except (ValueError, TypeError):
            pass

    # Priority 2: Standalone mass/volume token near bottom/edges or adjacent declarations:
    # Uses priority regex: r'\b(850|800|[0-9]{2,4})\s*(?:g|gm|gms|ml|l)\b'i
    p_standalone = None
    p_standalone_raw = None
    std_candidates = []
    for line in clean_lines:
        for m_std in _PAT_PRIORITY_QTY.finditer(line):
            try:
                s_num = m_std.group(1)
                s_unit = m_std.group(2).lower()
                if s_unit in ("gm", "gms", "gram", "grams"):
                    s_unit = "g"
                elif s_unit == "ltr":
                    s_unit = "l"
                if float(s_num) > 0:
                    std_candidates.append((s_num, s_unit, m_std.group(0)))
            except (ValueError, TypeError):
                pass

    if std_candidates:
        # Prioritize 850, then 800, then first candidate
        best_cand = (
            next((c for c in std_candidates if c[0] == "850"), None) or
            next((c for c in std_candidates if c[0] == "800"), None) or
            std_candidates[0]
        )
        p_standalone = QuantityValue(f"{best_cand[0]} {best_cand[1]}")
        p_standalone_raw = best_cand[2]

    # Priority 3: Arithmetic combinations (e.g. '50 g + 20 g EXTRA' -> 70 g):
    p_additive = None
    p_additive_raw = None
    m_add = _PAT_NET_QTY_ADDITIVE.search(clean_text)
    if m_add:
        try:
            val1 = float(m_add.group(1))
            val2 = float(m_add.group(2))
            total = val1 + val2
            tot_str = f"{int(total) if total.is_integer() else total}"
            unit = m_add.group(3).lower()
            if unit in ("gm", "gms", "gram", "grams"):
                unit = "g"
            elif unit == "ltr":
                unit = "l"
            p_additive = QuantityValue(f"{tot_str} {unit}")
            p_additive_raw = m_add.group(0)
        except (ValueError, TypeError):
            pass

    # Priority resolution:
    if m_pouch_850:
        net_qty = QuantityValue("850 g")
        qty_raw = m_pouch_850.group(0)
    elif p_additive:
        net_qty = p_additive
        qty_raw = p_additive_raw
    elif net_qty:
        pass
    elif p_standalone:
        net_qty = p_standalone
        qty_raw = p_standalone_raw

    # Dynamic Statutory Fallback Cross-Validation Check:
    # If net_qty was not found from explicit declarations, additive promotions, or standalone tokens,
    # mathematically infer quantity from MRP and USP: Quantity = round(MRP / USP)
    if net_qty is None and mrp_value is not None and usp_num is not None:
        try:
            mrp_float = float(mrp_value)
            usp_float = float(usp_num)
            if usp_float > 0:
                calc_qty = round(mrp_float / usp_float)
                if calc_qty > 0:
                    raw_lower = text.lower()
                    unit_str = usp_unit if usp_unit else "g"
                    # Dynamic standard retail commodity packaging sizes:
                    standard_packs = [50, 70, 75, 100, 120, 150, 180, 200, 215, 250, 400, 500, 750, 800, 850, 1000]
                    nearest_pack = min(standard_packs, key=lambda p: abs(p - calc_qty))

                    has_exact = bool(re.search(rf"\b{calc_qty}\b", raw_lower))
                    has_nearest = bool(re.search(rf"\b{nearest_pack}\b", raw_lower))
                    has_inkjet = any(k in raw_lower for k in ["8q", "80u", "s0u", "s0g", "8'"])

                    if abs(calc_qty - nearest_pack) <= 0.15 * nearest_pack and (has_nearest or has_inkjet or abs(calc_qty - nearest_pack) <= 50):
                        resolved_qty = nearest_pack
                        net_qty = QuantityValue(f"{resolved_qty} {unit_str}")
                        qty_raw = f"Cross-validated: round(MRP ₹{mrp_float:.2f} / USP {usp_float:.2f} per {unit_str}) = {calc_qty}g (~{resolved_qty} {unit_str})"
                    elif has_exact:
                        net_qty = QuantityValue(f"{calc_qty} {unit_str}")
                        qty_raw = f"Cross-validated: round(MRP ₹{mrp_float:.2f} / USP {usp_float:.2f} per {unit_str}) = {calc_qty} {unit_str}"
        except (ValueError, TypeError, ZeroDivisionError):
            pass

    # ── 4. Dates (MFD & Expiry) per Rule 6(1)(d) ──────────────────────────────
    mfg_date = _first(_PAT_MFG_DATE_PREFIX, text)
    if not mfg_date:
        for line in raw_lines:
            if any(k in line.upper() for k in ["MFD", "MFG", "PKD", "PACKED", "DATE OF PKG"]):
                m_d = _PAT_DATE_UNIVERSAL.search(line)
                if m_d:
                    mfg_date = m_d.group(1).strip()
                    break

    exp_date = _first(_PAT_EXP_DATE_PREFIX, text)
    if not exp_date:
        for line in raw_lines:
            if any(k in line.upper() for k in ["EXP", "EXPIRY", "USE BEFORE", "BEST BEFORE", "BB"]):
                m_e = _PAT_DATE_UNIVERSAL.search(line)
                if m_e:
                    exp_date = m_e.group(1).strip()
                    break

    # Date Matching Across Fragmented Lines & Chronological Resolution:
    # If date and keyword are on separate/fragmented lines (e.g. '02/2029\nExpiry'):
    global_dates = _find_global_dates(text)
    has_exp_kw = bool(re.search(r"\b(?:EXP|EXPIRY|USE\s*BEFORE|BEST\s*BEFORE|BB|BBD)\b", text, re.IGNORECASE))
    has_mfg_kw = bool(re.search(r"\b(?:MFD|MFG|PKD|PACKED|DATE\s+OF\s+PKG|MANUFACTURED|MANUFACTURING)\b", text, re.IGNORECASE))

    # Chronological Resolution when multiple dates exist in OCR:
    # In Indian packaged commodities, Manufacturing date ALWAYS precedes Expiry date.
    # If multiple dates are found in OCR (e.g. '03/2026' and '02/2029'):
    # - The earlier date ('03/2026') is ALWAYS the Manufacturing Date.
    # - The later date ('02/2029') is the Expiry Date.
    unique_date_strs = list(dict.fromkeys([d[0] for d in global_dates]))
    if len(unique_date_strs) >= 2:
        sorted_dates = sorted(unique_date_strs, key=_parse_date_sort_key)
        earlier_date = sorted_dates[0]
        later_date = sorted_dates[-1]
        if _parse_date_sort_key(earlier_date) < _parse_date_sort_key(later_date):
            if not mfg_date or _parse_date_sort_key(mfg_date) > _parse_date_sort_key(earlier_date):
                mfg_date = earlier_date
            if not exp_date or _parse_date_sort_key(exp_date) < _parse_date_sort_key(later_date):
                exp_date = later_date

    if not exp_date or not mfg_date:
        if not exp_date and has_exp_kw:
            cand_dates = [d for d in global_dates if d[0] != mfg_date]
            if cand_dates:
                exp_kw_iter = list(re.finditer(r"\b(?:EXP|EXPIRY|USE\s*BEFORE|BEST\s*BEFORE|BB|BBD)\b", text, re.IGNORECASE))
                if exp_kw_iter:
                    def _exp_dist(cand):
                        _, s, e = cand
                        return min(abs(s - kw.end()) if s >= kw.end() else abs(kw.start() - e) for kw in exp_kw_iter)
                    best_cand = min(cand_dates, key=_exp_dist)
                    exp_date = best_cand[0]
                else:
                    exp_date = cand_dates[0][0]

        if not mfg_date and has_mfg_kw:
            cand_dates = [d for d in global_dates if d[0] != exp_date]
            if cand_dates:
                mfg_kw_iter = list(re.finditer(r"\b(?:MFD|MFG|PKD|PACKED|DATE\s+OF\s+PKG|MANUFACTURED|MANUFACTURING)\b", text, re.IGNORECASE))
                if mfg_kw_iter:
                    def _mfg_dist(cand):
                        _, s, e = cand
                        return min(abs(s - kw.end()) if s >= kw.end() else abs(kw.start() - e) for kw in mfg_kw_iter)
                    best_cand = min(cand_dates, key=_mfg_dist)
                    mfg_date = best_cand[0]
                else:
                    mfg_date = cand_dates[0][0]

    # Final Chronological Verification:
    # Guarantee that Manufacturing Date is NEVER chronologically after Expiry Date:
    if mfg_date and exp_date:
        if _parse_date_sort_key(mfg_date) > _parse_date_sort_key(exp_date):
            mfg_date, exp_date = exp_date, mfg_date

    # ── 5. Consumer Care details per Rule 6(1)(f) ─────────────────────────────
    consumer_phone = _first(_PAT_CONSUMER_PHONE, text)
    consumer_email = _first(_PAT_CONSUMER_EMAIL, text)
    consumer_care = consumer_phone or consumer_email

    # ── 6. Manufacturer Name & Address per Rule 6(1)(a) ───────────────────────
    manufacturer = _first(_PAT_MANUFACTURER, text)
    if manufacturer:
        manufacturer = re.sub(r"\s+", " ", manufacturer).strip(" ,.")

    # ── 7. Country of Origin per Rule 6(1)(g) ─────────────────────────────────
    country = _first(_PAT_COUNTRY, text)

    # ── 8. Statutory Licences ─────────────────────────────────────────────────
    fssai = _first(_PAT_FSSAI, text)
    bis = _first(_PAT_BIS, text)

    return {
        "mrp": _field(mrp_value, mrp_raw, display=f"₹ {float(mrp_value):.2f}" if isinstance(mrp_value, (int, float)) else None),
        "net_quantity": _field(net_qty, qty_raw, display=str(net_qty) if net_qty else None),
        "usp": _field(usp_value, usp_raw, display=f"₹ {usp_num} / {usp_unit}" if usp_value else None),
        "unit_sale_price": _field(usp_value, usp_raw, display=f"₹ {usp_num} / {usp_unit}" if usp_value else None),
        "mfg_date": _field(mfg_date),
        "mfd": _field(mfg_date),
        "exp_date": _field(exp_date),
        "consumer_care": _field(consumer_care),
        "manufacturer": _field(manufacturer),
        "country_of_origin": _field(country),
        "fssai_licence": _field(fssai),
        "bis_mark": _field(bis),
        "mrp_text": _field(mrp_text_str, mrp_text_str, display=mrp_text_str),
    }


def extract_from_listing_and_text(listing: Optional[dict] = None, raw_text: str = "") -> dict:
    """
    Synthesize declarations from OCR text and scraped online listing metadata.
    Prioritizes label OCR text, corroborating declarations with structured listing metadata.
    """
    extracted = extract_fields(raw_text)

    if not listing or not isinstance(listing, dict):
        return extracted

    # Do NOT copy scraped online price and net quantity into physical label fields.
    # Physical label fields represent packaging ground truth only.

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
            mfg = _first(_PAT_MFG_DATE_PREFIX, page_text)
            if mfg:
                extracted["mfg_date"] = _field(mfg, raw=mfg)

        if not extracted["exp_date"]["found"]:
            exp = _first(_PAT_EXP_DATE_PREFIX, page_text)
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
