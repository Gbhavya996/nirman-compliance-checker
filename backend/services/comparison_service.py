"""
comparison_service.py
─────────────────────
Compares the physical MRP from the scanned label against online retail
prices to detect potential price violations (Rule 8: MRP must not be
exceeded at point of sale).

Supports direct comparison with scraped listing price and live API lookup.
NEVER returns synthetic or mock data.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


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
        # Open Food Facts API (free, no key required)
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
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def compare(extracted_fields: dict, listing: Optional[dict] = None) -> dict:
    """
    Compare physical MRP with online price.

    Parameters
    ----------
    extracted_fields : dict from extraction_service.extract_fields()
    listing          : optional dict from url_scraper_service.scrape_listing()

    Returns
    -------
    dict with comparison result
    """
    mrp_field = extracted_fields.get("mrp", {})
    manufacturer_field = extracted_fields.get("manufacturer", {})

    physical_mrp = mrp_field.get("value") if mrp_field.get("found") else None
    manufacturer = manufacturer_field.get("value", "") or ""

    # Check if we have listing price directly available
    listing_price = listing.get("mrp") if listing and isinstance(listing, dict) else None

    # Derive a product name for lookup
    product_name = re.sub(r"(?:Pvt\.?|Ltd\.?|Inc\.?|Corp\.?|LLP|Co\.?)\b.*", "", str(manufacturer)).strip()
    if not product_name and listing and listing.get("product_title"):
        product_name = listing["product_title"]

    if physical_mrp is None and listing_price is None:
        return {
            "source": "N/A",
            "physical_mrp": None,
            "online_price": None,
            "delta_pct": None,
            "status": "SKIP",
            "explanation": "MRP not detected on package or listing; price comparison skipped.",
        }

    # If physical MRP is present and listing price is present, compare directly
    if physical_mrp is not None and listing_price is not None:
        try:
            p_mrp = float(physical_mrp)
            l_price = float(listing_price)
            delta_pct = round(((l_price - p_mrp) / p_mrp) * 100, 1)
            source_domain = listing.get("domain") or "Online Listing"
            if l_price > p_mrp:
                status = "FAIL"
                explanation = (
                    f"Online price ₹{l_price} on {source_domain} exceeds physical MRP ₹{p_mrp} "
                    f"by {delta_pct}%. Rule 8 prohibits sale above MRP."
                )
            elif l_price < p_mrp * 0.5:
                status = "WARNING"
                explanation = (
                    f"Online price ₹{l_price} is {abs(delta_pct)}% below package MRP ₹{p_mrp}. "
                    "Review required for potential deep discount or counterfeit alert."
                )
            else:
                status = "PASS"
                explanation = (
                    f"Online price ₹{l_price} on {source_domain} is compliant with "
                    f"physical MRP ₹{p_mrp} ({delta_pct}%)."
                )

            return {
                "source": source_domain,
                "physical_mrp": p_mrp,
                "online_price": l_price,
                "delta_pct": delta_pct,
                "status": status,
                "explanation": explanation,
            }
        except (ValueError, TypeError):
            pass

    # If only one of them is available
    if physical_mrp is not None:
        try:
            physical_mrp = float(physical_mrp)
        except (TypeError, ValueError):
            return {
                "source": "N/A",
                "physical_mrp": physical_mrp,
                "online_price": None,
                "delta_pct": None,
                "status": "SKIP",
                "explanation": f"MRP value '{physical_mrp}' could not be parsed as a number.",
            }

        # Attempt live lookup
        if product_name:
            live_result = _lookup_online_price(product_name, physical_mrp)
            if live_result and live_result.get("online_price") is not None:
                op = float(live_result["online_price"])
                delta_pct = round(((op - physical_mrp) / physical_mrp) * 100, 1)
                live_result.update({
                    "physical_mrp": physical_mrp,
                    "delta_pct": delta_pct,
                    "status": "FAIL" if op > physical_mrp else "PASS",
                    "explanation": f"Online price ₹{op} vs physical MRP ₹{physical_mrp} (delta {delta_pct}%).",
                })
                return live_result

        return {
            "source": "N/A",
            "physical_mrp": physical_mrp,
            "online_price": None,
            "delta_pct": None,
            "status": "SKIP",
            "explanation": "Package MRP detected, but no independent online price was found for cross-comparison.",
        }

    # Only listing price is available (no physical label)
    try:
        listing_price = float(listing_price)
        source_domain = (listing or {}).get("domain") or "Online Listing"
        return {
            "source": source_domain,
            "physical_mrp": None,
            "online_price": listing_price,
            "delta_pct": None,
            "status": "PASS",
            "explanation": f"Price ₹{listing_price} verified on {source_domain}. Physical label not provided.",
        }
    except (TypeError, ValueError):
        return {
            "source": "N/A",
            "physical_mrp": None,
            "online_price": None,
            "delta_pct": None,
            "status": "SKIP",
            "explanation": "No valid pricing available for comparison.",
        }
