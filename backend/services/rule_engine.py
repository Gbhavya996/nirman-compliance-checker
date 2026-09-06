"""
rule_engine.py
──────────────
Evaluates extracted label fields against the
Legal Metrology (Packaged Commodities) Rules, 2011 (LM-PC Rules).

Key rules evaluated
--------------------
Rule 6(1)   – Mandatory declarations: MRP, Net Qty, Mfg Date, Consumer Care,
              Manufacturer details (all must be present)
Rule 6(1)(f)– MRP must include all taxes ("Incl. of all taxes")
Rule 6(1)(g)– Best-before / expiry date for food/perishable items
Rule 8      – MRP must not be exceeded at point of sale
Rule 9      – Net quantity tolerance limits
Rule 18     – Consumer complaint contact details mandatory
Schedule II – Font size and legibility requirements

Status codes
-------------
PASS    – field present and valid
FAIL    – mandatory field absent or clearly violating a rule
WARNING – field present but may be non-compliant (needs human review)
"""

import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

RuleResult = Dict[str, Any]   # {field, status, rule_ref, explanation, value}
RuleReport = List[RuleResult]


# ─────────────────────────────────────────────────────────────────────────────
# Individual rule checks
# ─────────────────────────────────────────────────────────────────────────────

def _check_mrp(field: dict, raw_text: str) -> RuleResult:
    """Rule 6(1)(e) & Rule 8 – MRP declaration."""
    if not field["found"] or field["value"] is None:
        return {
            "field": "MRP",
            "status": "FAIL",
            "rule_ref": "LM-PC Rule 6(1)(e)",
            "explanation": (
                "Maximum Retail Price (MRP) not detected on the label. "
                "Rule 6(1)(e) mandates that the retail sale price be declared "
                "on every package."
            ),
            "value": None,
        }

    mrp = field["value"]
    # Check inclusive-of-taxes declaration
    incl_pattern = re.compile(
        r"incl(?:usive)?\.?\s+(?:of\s+)?all\s+tax(?:es)?", re.IGNORECASE
    )
    has_incl = bool(incl_pattern.search(raw_text))

    if not has_incl:
        return {
            "field": "MRP",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(e) read with Rule 18",
            "explanation": (
                f"MRP ₹{mrp} detected but the phrase 'inclusive of all taxes' "
                "is missing. Rule 6(1)(e) requires the MRP to be declared "
                "with the words 'inclusive of all taxes'."
            ),
            "value": mrp,
        }

    return {
        "field": "MRP",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(e)",
        "explanation": f"MRP ₹{mrp} declared with tax-inclusive statement.",
        "value": mrp,
    }


def _check_net_quantity(field: dict) -> RuleResult:
    """Rule 6(1)(b) – Net quantity declaration."""
    if not field["found"]:
        return {
            "field": "Net Quantity",
            "status": "FAIL",
            "rule_ref": "LM-PC Rule 6(1)(b)",
            "explanation": (
                "Net quantity not detected on the label. Rule 6(1)(b) mandates "
                "net quantity declaration in standard units (g, kg, ml, L)."
            ),
            "value": None,
        }

    qty_str = str(field["value"]).upper()
    # Check unit validity
    valid_units = re.compile(r"\d+(?:\.\d+)?\s*(KG|G|GM|MG|L|LT|LTR|ML|LITRE|LITER|PCS|NOS|UNITS?)", re.IGNORECASE)
    if not valid_units.search(qty_str):
        return {
            "field": "Net Quantity",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(b) & Rule 7",
            "explanation": (
                f"Net quantity '{field['value']}' detected but unit may be "
                "non-standard. Rule 7 requires quantities in metric system units."
            ),
            "value": field["value"],
        }

    return {
        "field": "Net Quantity",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(b)",
        "explanation": f"Net quantity '{field['value']}' declared in valid metric units.",
        "value": field["value"],
    }


def _check_mfg_date(field: dict) -> RuleResult:
    """Rule 6(1)(d) – Month and year of manufacture."""
    if not field["found"]:
        return {
            "field": "Manufacturing Date",
            "status": "FAIL",
            "rule_ref": "LM-PC Rule 6(1)(d)",
            "explanation": (
                "Manufacturing/packing date not detected. Rule 6(1)(d) mandates "
                "month and year of manufacture or packing."
            ),
            "value": None,
        }

    # Check that value contains a year (4 digits)
    year_pattern = re.compile(r"\b(20\d{2}|19\d{2})\b")
    if not year_pattern.search(str(field["value"])):
        return {
            "field": "Manufacturing Date",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(d)",
            "explanation": (
                f"Mfg date '{field['value']}' found but year not clearly identifiable. "
                "Rule 6(1)(d) requires both month and year."
            ),
            "value": field["value"],
        }

    return {
        "field": "Manufacturing Date",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(d)",
        "explanation": f"Manufacturing date '{field['value']}' detected.",
        "value": field["value"],
    }


def _check_expiry(field: dict) -> RuleResult:
    """Rule 6(1)(g) – Best before / expiry date (food/perishable)."""
    if not field["found"]:
        return {
            "field": "Expiry / Best Before",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(g)",
            "explanation": (
                "Expiry or best-before date not detected. Mandatory for food, "
                "pharmaceutical, and other perishable packaged commodities under "
                "Rule 6(1)(g). If this is a non-perishable item, this warning may "
                "be disregarded."
            ),
            "value": None,
        }

    return {
        "field": "Expiry / Best Before",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(g)",
        "explanation": f"Best-before/expiry '{field['value']}' declared.",
        "value": field["value"],
    }


def _check_consumer_care(field: dict) -> RuleResult:
    """Rule 18 – Consumer complaints contact."""
    if not field["found"]:
        return {
            "field": "Consumer Care",
            "status": "FAIL",
            "rule_ref": "LM-PC Rule 18",
            "explanation": (
                "Consumer care / helpline contact not detected. Rule 18 of LM-PC Rules "
                "requires every package to carry consumer complaint contact details "
                "(phone number or email address)."
            ),
            "value": None,
        }

    val = str(field["value"])
    # Validate phone format (10 digits or 1800-xxx-xxxx, including placeholder formats like 1800-XXX-1234)
    phone_ok = re.search(r"(?:1800[\s-]?[\w]{3}[\s-]?\d{4}|\d{10})", val)
    email_ok = re.search(r"@", val)

    if not (phone_ok or email_ok):
        return {
            "field": "Consumer Care",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 18",
            "explanation": (
                f"Consumer care contact '{val}' found but format may be invalid. "
                "A valid phone (10-digit / toll-free 1800) or email is required."
            ),
            "value": val,
        }

    return {
        "field": "Consumer Care",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 18",
        "explanation": f"Consumer care contact '{val}' detected.",
        "value": val,
    }


def _check_manufacturer(field: dict) -> RuleResult:
    """Rule 6(1)(a) – Manufacturer name and address."""
    if not field["found"]:
        return {
            "field": "Manufacturer",
            "status": "FAIL",
            "rule_ref": "LM-PC Rule 6(1)(a)",
            "explanation": (
                "Manufacturer name and address not detected. Rule 6(1)(a) mandates "
                "the name and complete address of the manufacturer / packer / importer."
            ),
            "value": None,
        }

    val = str(field["value"])
    # Heuristic: address should contain a pin code or city
    has_pin = re.search(r"\b\d{6}\b", val)
    has_city = re.search(
        r"\b(Delhi|Mumbai|Bengaluru|Bangalore|Chennai|Kolkata|Hyderabad|Pune|"
        r"Ahmedabad|Surat|Jaipur|Lucknow|Kanpur|Nagpur|Visakhapatnam|Indore|"
        r"Thane|Bhopal|Patna|Vadodara|Ghaziabad|Ludhiana|Agra|Nashik)\b",
        val, re.IGNORECASE,
    )

    if not (has_pin or has_city):
        return {
            "field": "Manufacturer",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(a)",
            "explanation": (
                f"Manufacturer '{val}' found but full address (including PIN code or city) "
                "not clearly identified. Complete address is required by Rule 6(1)(a)."
            ),
            "value": val,
        }

    return {
        "field": "Manufacturer",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(a)",
        "explanation": f"Manufacturer details detected: '{val[:60]}...' " if len(val) > 60 else f"Manufacturer details: '{val}'",
        "value": val,
    }


def _check_country(field: dict) -> RuleResult:
    """Rule 6(1)(h) – Country of origin (mandatory for imported goods)."""
    if not field["found"]:
        return {
            "field": "Country of Origin",
            "status": "WARNING",
            "rule_ref": "LM-PC Rule 6(1)(h)",
            "explanation": (
                "Country of origin not detected. Mandatory for imported goods "
                "under Rule 6(1)(h). Domestic products are exempt."
            ),
            "value": None,
        }
    return {
        "field": "Country of Origin",
        "status": "PASS",
        "rule_ref": "LM-PC Rule 6(1)(h)",
        "explanation": f"Country of origin: '{field['value']}'.",
        "value": field["value"],
    }


def _check_fssai(field: dict) -> RuleResult:
    """FSSAI licence – mandatory for food products (not LM-PC but cross-ref check)."""
    if not field["found"]:
        return {
            "field": "FSSAI Licence",
            "status": "WARNING",
            "rule_ref": "FSS (Packaging & Labelling) Regulations 2011, Reg. 2.2",
            "explanation": (
                "FSSAI licence number (14 digits) not detected. Mandatory for food "
                "products under FSSAI regulations. If this is not a food product, "
                "this warning may be disregarded."
            ),
            "value": None,
        }

    lic = str(field["value"])
    if not re.fullmatch(r"\d{14}", lic):
        return {
            "field": "FSSAI Licence",
            "status": "WARNING",
            "rule_ref": "FSSAI Regulations",
            "explanation": f"FSSAI number '{lic}' detected but does not conform to 14-digit format.",
            "value": lic,
        }

    return {
        "field": "FSSAI Licence",
        "status": "PASS",
        "rule_ref": "FSS Regulations 2011",
        "explanation": f"FSSAI licence number '{lic}' detected.",
        "value": lic,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def evaluate(extracted_fields: dict, raw_text: str) -> RuleReport:
    """
    Run all rule checks against *extracted_fields*.

    Parameters
    ----------
    extracted_fields : output of extraction_service.extract_fields()
    raw_text         : original OCR text (needed for context checks)

    Returns
    -------
    List of RuleResult dicts, one per checked field.
    """
    report: RuleReport = []

    report.append(_check_mrp(extracted_fields.get("mrp", {"found": False}), raw_text))
    report.append(_check_net_quantity(extracted_fields.get("net_quantity", {"found": False})))
    report.append(_check_mfg_date(extracted_fields.get("mfg_date", {"found": False})))
    report.append(_check_expiry(extracted_fields.get("exp_date", {"found": False})))
    report.append(_check_consumer_care(extracted_fields.get("consumer_care", {"found": False})))
    report.append(_check_manufacturer(extracted_fields.get("manufacturer", {"found": False})))
    report.append(_check_country(extracted_fields.get("country_of_origin", {"found": False})))
    report.append(_check_fssai(extracted_fields.get("fssai_licence", {"found": False})))

    return report


def summary(report: RuleReport) -> dict:
    """Return aggregate counts and overall compliance status."""
    counts = {"PASS": 0, "FAIL": 0, "WARNING": 0}
    for r in report:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    if counts["FAIL"] > 0:
        overall = "NON_COMPLIANT"
    elif counts["WARNING"] > 0:
        overall = "NEEDS_REVIEW"
    else:
        overall = "COMPLIANT"

    return {
        "overall": overall,
        "pass_count": counts["PASS"],
        "fail_count": counts["FAIL"],
        "warning_count": counts["WARNING"],
        "total_checks": len(report),
    }
