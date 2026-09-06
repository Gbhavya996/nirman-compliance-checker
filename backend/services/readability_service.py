"""
readability_service.py
──────────────────────
Assesses font height ratios against LM-PC Schedule II requirements.

LM-PC Schedule II specifies minimum height of numerals and letters for
the mandatory declarations based on net quantity / package size:

  Net quantity          Minimum height of numerals / letters
  ──────────────────────────────────────────────────────────
  ≤ 5 g or 5 ml        1 mm
  > 5 g/ml to 50 g/ml  2 mm
  > 50 g/ml to 200 g   4 mm
  > 200 g to 1 kg/L    6 mm
  > 1 kg / 1 L         10 mm

The service estimates physical mm from pixel heights using a nominal
300 DPI assumption (1 mm ≈ 11.8 px).
"""

import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

NOMINAL_DPI = 300
PX_PER_MM = NOMINAL_DPI / 25.4  # ≈ 11.81 px per mm

# ─────────────────────────────────────────────────────────────────────────────
# Schedule II thresholds
# ─────────────────────────────────────────────────────────────────────────────

def _min_height_mm(net_qty_str: str | None) -> float:
    """Return the minimum letter height (mm) per Schedule II for a given net quantity."""
    if not net_qty_str:
        return 2.0  # default / unknown

    # Parse quantity value + unit
    m = re.search(r"([\d.]+)\s*(kg|g|gm|mg|l|lt|ltr|ml)", net_qty_str, re.IGNORECASE)
    if not m:
        return 2.0

    qty = float(m.group(1))
    unit = m.group(2).lower()

    # Normalise to grams or ml
    if unit == "kg":
        qty_g = qty * 1000
    elif unit in ("l", "lt", "ltr"):
        qty_g = qty * 1000  # treat litre == ml for threshold purposes
    elif unit == "mg":
        qty_g = qty / 1000
    else:
        qty_g = qty  # g or ml already

    if qty_g <= 5:
        return 1.0
    elif qty_g <= 50:
        return 2.0
    elif qty_g <= 200:
        return 4.0
    elif qty_g <= 1000:
        return 6.0
    else:
        return 10.0


# ─────────────────────────────────────────────────────────────────────────────
# Main assessment
# ─────────────────────────────────────────────────────────────────────────────

def assess_readability(
    words: List[Dict[str, Any]],
    net_qty_str: str | None = None,
    page_height_px: int = 600,
) -> Dict[str, Any]:
    """
    Assess label readability.

    Parameters
    ----------
    words          : list of word dicts from ocr_service (with 'h' key = pixel height)
    net_qty_str    : e.g. "100 G" – used to select Schedule II threshold
    page_height_px : total image height in pixels

    Returns
    -------
    dict: {
        "min_required_mm": float,
        "estimated_min_mm": float,
        "estimated_avg_mm": float,
        "flagged_words": list,
        "status": "PASS" | "FAIL" | "WARNING",
        "explanation": str,
    }
    """
    min_req_mm = _min_height_mm(net_qty_str)
    min_req_px = min_req_mm * PX_PER_MM

    if not words:
        return {
            "min_required_mm": min_req_mm,
            "estimated_min_mm": None,
            "estimated_avg_mm": None,
            "flagged_words": [],
            "status": "WARNING",
            "explanation": "No word bounding boxes available; readability cannot be assessed.",
        }

    heights_px = [w["h"] for w in words if w.get("h", 0) > 0]
    if not heights_px:
        return {
            "min_required_mm": min_req_mm,
            "estimated_min_mm": None,
            "estimated_avg_mm": None,
            "flagged_words": [],
            "status": "WARNING",
            "explanation": "Word heights could not be extracted; readability cannot be assessed.",
        }

    min_px = min(heights_px)
    avg_px = sum(heights_px) / len(heights_px)

    min_mm = round(min_px / PX_PER_MM, 2)
    avg_mm = round(avg_px / PX_PER_MM, 2)

    # Identify individual words below threshold
    flagged = [
        {
            "text": w["text"],
            "height_px": w["h"],
            "height_mm": round(w["h"] / PX_PER_MM, 2),
        }
        for w in words
        if 0 < w.get("h", 0) < min_req_px
    ]

    if min_mm < min_req_mm * 0.7:
        status = "FAIL"
        explanation = (
            f"Estimated minimum font height {min_mm} mm is well below the "
            f"Schedule II minimum of {min_req_mm} mm for this package size. "
            f"{len(flagged)} word(s) flagged as potentially unreadable."
        )
    elif min_mm < min_req_mm:
        status = "WARNING"
        explanation = (
            f"Estimated minimum font height {min_mm} mm is below Schedule II "
            f"requirement of {min_req_mm} mm. {len(flagged)} word(s) may be "
            "difficult to read."
        )
    else:
        status = "PASS"
        flagged = []
        explanation = (
            f"Minimum font height {min_mm} mm meets Schedule II requirement "
            f"of {min_req_mm} mm."
        )

    return {
        "min_required_mm": min_req_mm,
        "estimated_min_mm": min_mm,
        "estimated_avg_mm": avg_mm,
        "flagged_words": flagged[:20],  # cap at 20 to keep payload small
        "status": status,
        "explanation": explanation,
    }
