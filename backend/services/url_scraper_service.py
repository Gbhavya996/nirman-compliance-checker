"""
url_scraper_service.py
──────────────────────
Fetches a product listing URL and dynamically extracts product fields
(Title, Price/MRP, Net Quantity, Brand/Manufacturer, Country of Origin, Product Image)
for Legal Metrology compliance verification.

Handles anti-bot detection cleanly (Amazon, Flipkart, Cloudflare, 403, 503, CAPTCHA)
without substituting hardcoded or mock data.
"""

import json
import logging
import re
from typing import Optional, Tuple
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP fetch helper with realistic browser headers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HTTP fetch helper with realistic browser headers
# ---------------------------------------------------------------------------

_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-IN,en-GB;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

BOT_BLOCK_ERROR = "This e-commerce site blocked automated access. Please upload a package image directly for compliance screening."


def _is_anti_bot(html: str, status_code: int) -> bool:
    """Detect automated bot challenge / CAPTCHA blocks (HTTP 403, 503, CAPTCHA)."""
    if status_code in (403, 429, 503):
        return True

    text_lower = html.lower()

    # Amazon bot / CAPTCHA signatures
    if "api-services-support@amazon.com" in text_lower:
        return True
    if "validatecaptcha" in text_lower or "robot check" in text_lower:
        return True
    if ("captcha" in text_lower or "type the characters" in text_lower) and "amazon" in text_lower:
        return True

    # Cloudflare / DDOS-Guard signatures
    if "attention required! | cloudflare" in text_lower or "cf-browser-verification" in text_lower:
        return True
    if "just a moment..." in text_lower and "cloudflare" in text_lower:
        return True

    # Flipkart / PerimeterX / Access Denied
    if "access denied" in text_lower and ("blocked" in text_lower or "perimeterx" in text_lower or "flipkart" in text_lower):
        return True

    return False


def _fetch_html_via_curl(url: str, timeout: int = 12) -> Tuple[Optional[str], Optional[int], Optional[str], str]:
    """Fallback fetcher using Windows curl.exe to bypass TLS fingerprinting blocks on Amazon."""
    import shutil
    import subprocess

    curl_bin = shutil.which("curl") or shutil.which("curl.exe")
    if not curl_bin:
        return None, None, "curl not available", url

    try:
        cmd = [
            curl_bin, "-s", "-L",
            "-A", _HEADERS['User-Agent'],
            "-H", f"Accept: {_HEADERS['Accept']}",
            "-H", f"Accept-Language: {_HEADERS['Accept-Language']}",
            "-H", f"Sec-Ch-Ua: {_HEADERS['Sec-Ch-Ua']}",
            "-H", f"Sec-Ch-Ua-Mobile: {_HEADERS['Sec-Ch-Ua-Mobile']}",
            "-H", f"Sec-Ch-Ua-Platform: {_HEADERS['Sec-Ch-Ua-Platform']}",
            "-H", f"Sec-Fetch-Dest: {_HEADERS['Sec-Fetch-Dest']}",
            "-H", f"Sec-Fetch-Mode: {_HEADERS['Sec-Fetch-Mode']}",
            "-H", f"Sec-Fetch-Site: {_HEADERS['Sec-Fetch-Site']}",
            "-H", f"Sec-Fetch-User: {_HEADERS['Sec-Fetch-User']}",
            "-H", f"Upgrade-Insecure-Requests: {_HEADERS['Upgrade-Insecure-Requests']}",
            "--max-time", str(timeout),
            "-w", "\n__FINAL_URL__:%{url_effective}",
            url,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="ignore")
        if res.returncode == 0 and res.stdout:
            parts = res.stdout.rsplit("\n__FINAL_URL__:", 1)
            curl_html = parts[0]
            final_url = parts[1].strip() if len(parts) > 1 and parts[1].strip() else url
            if not _is_anti_bot(curl_html, 200) and len(curl_html) > 5000:
                logger.info("Successfully fetched %s via curl fallback (%d bytes)", url, len(curl_html))
                return curl_html, 200, None, final_url
            return curl_html, 200, BOT_BLOCK_ERROR if _is_anti_bot(curl_html, 200) else None, final_url
    except Exception as exc:
        logger.debug("curl fallback failed: %s", exc)

    return None, None, "curl execution failed", url


def _fetch_html(url: str, timeout: int = 10) -> Tuple[Optional[str], Optional[int], Optional[str], str]:
    """
    Fetch URL with requests.Session() and allow_redirects=True (handles amzn.in and Amazon redirect links).
    Returns (html_text, status_code, error_message, final_url).
    """
    is_amazon = "amazon." in url.lower() or "amzn.in" in url.lower()

    try:
        import requests
        session = requests.Session()
        session.headers.update(_HEADERS)

        resp = session.get(url, timeout=timeout, allow_redirects=True)
        final_url = resp.url
        html_text = resp.text
        status_code = resp.status_code

        # If requests got challenged by anti-bot on Amazon or returned small challenge stub
        if _is_anti_bot(html_text, status_code) or (is_amazon and len(html_text) < 15000):
            logger.info("requests.Session hit anti-bot challenge on %s (len: %d). Trying curl fallback...", url, len(html_text))
            curl_html, curl_status, curl_err, curl_url = _fetch_html_via_curl(url, timeout=timeout)
            if curl_html and not _is_anti_bot(curl_html, 200) and len(curl_html) > 5000:
                return curl_html, 200, None, curl_url or final_url
            # If curl also was challenged, return curl_html or resp.text for regex/meta fallback parsing
            return curl_html or html_text, curl_status or status_code, BOT_BLOCK_ERROR, curl_url or final_url

        if status_code == 200:
            return html_text, 200, None, final_url

        logger.warning("URL fetch returned HTTP %d for %s", status_code, url)
        return html_text, status_code, f"Server returned HTTP {status_code}.", final_url
    except Exception as exc:
        logger.warning("URL fetch via requests failed for %s: %s. Trying curl fallback...", url, exc)
        curl_html, curl_status, curl_err, curl_url = _fetch_html_via_curl(url, timeout=timeout)
        if curl_html:
            return curl_html, curl_status or 200, curl_err, curl_url
        return None, None, f"Network connection failed: {exc}", url


def fetch_image_bytes(image_url: str, timeout: int = 10) -> Optional[Tuple[bytes, str]]:
    """
    Download product packaging image bytes from URL.
    Returns (bytes, mime_type) or None.
    """
    if not image_url or not image_url.startswith("http"):
        return None

    try:
        import requests
        resp = requests.get(image_url, headers=_HEADERS, timeout=timeout)
        if resp.status_code == 200 and len(resp.content) > 1024:
            content_type = resp.headers.get("Content-Type", "").lower()
            mime = "image/jpeg"
            if "png" in content_type:
                mime = "image/png"
            elif "webp" in content_type:
                mime = "image/webp"
            elif "gif" in content_type:
                return None  # Skip GIF animations
            return resp.content, mime
    except Exception as exc:
        logger.warning("Failed to fetch product image at %s: %s", image_url, exc)

    return None


def _get_domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

def _extract_title(soup, text: str) -> Optional[str]:
    """
    Extract product title.
    Checks: <meta property="og:title">, <title>, or <h1>.
    """
    # 1. OpenGraph title
    og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
    if og_title and og_title.get("content"):
        t = og_title["content"].strip()
        if t and len(t) < 200:
            # Strip site suffixes
            cleaned = re.sub(r"\s*[-|–•]\s*(BigBasket|Blinkit|JioMart|Amazon|Flipkart|Nykaa|Open Food Facts).*$", "", t, flags=re.I).strip()
            if cleaned:
                return cleaned

    # 2. Schema.org title
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                data = data[0]
            name = data.get("name")
            if name and isinstance(name, str):
                return name.strip()
        except Exception:
            pass

    # 3. <h1> tag
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(strip=True)
        if t and len(t) < 200:
            return re.sub(r"\s*[-|–•]\s*(BigBasket|Blinkit|JioMart|Amazon|Flipkart|Nykaa).*$", "", t, flags=re.I).strip()

    # 4. <title> tag
    title_tag = soup.find("title")
    if title_tag:
        t = title_tag.get_text(strip=True)
        if t:
            cleaned = re.sub(r"\s*[-|–•]\s*(BigBasket|Blinkit|JioMart|Amazon|Flipkart|Nykaa|Open Food Facts).*$", "", t, flags=re.I).strip()
            if cleaned:
                return cleaned

    return None


def _is_inside_ignored_offer_box(element) -> bool:
    """
    Check if an element resides inside an inactive buybox, sidebar, or alternate offer card.
    Specifically ignores #pinned-deactivated-buybox, #alternate-buybox, and alternate offers.
    """
    if not element:
        return False
    curr = element
    ignored_tokens = (
        "pinned-deactivated-buybox",
        "alternate-buybox",
        "dynamic-aod-ingress-box",
        "all-offers-display",
        "aod-alternate-offer",
        "desktop-dp-sims",
        "a-carousel",
    )
    while curr:
        if hasattr(curr, "get"):
            c_id = str(curr.get("id") or "")
            c_class = " ".join(curr.get("class") or [])
            combined = f"{c_id} {c_class}".lower()
            if any(tok in combined for tok in ignored_tokens):
                return True
        curr = curr.parent
    return False


def _extract_mrp(soup, text: str, html: str = "") -> Optional[float]:
    """
    Extract Price / MRP.
    Prioritizes the primary active Buybox price:
      1. Primary active apex price container: span.apexPriceToPay span.a-offscreen
      2. Primary core price container: #corePriceDisplay_desktop_feature_div span.a-price-whole
      3. Desktop core price feature: #corePrice_desktop span.apexPriceToPay span.a-offscreen
      4. Standard buybox priceblock IDs (#priceblock_ourprice, #priceblock_dealprice)
      5. Filtered span.a-price span.a-offscreen (ignoring alternate / deactivated offer cards)
      6. JSON-LD metadata, Schema.org microdata, Open Graph tags
      7. Fallback regex on text/html
    Ignores sidebar and alternate offer boxes (e.g. #pinned-deactivated-buybox).
    """
    raw_html = html or (str(soup) if soup else "")

    if soup:
        # 1. Target ONLY the primary active price container: span.apexPriceToPay span.a-offscreen
        for apex in soup.select("span.apexPriceToPay span.a-offscreen"):
            if not _is_inside_ignored_offer_box(apex):
                raw = re.sub(r"[^\d.]", "", apex.get_text(strip=True))
                if raw:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except ValueError:
                        pass

        # 2. Target core active price: #corePriceDisplay_desktop_feature_div span.a-price-whole
        for core in soup.select("#corePriceDisplay_desktop_feature_div span.a-price-whole"):
            if not _is_inside_ignored_offer_box(core):
                raw = re.sub(r"[^\d.]", "", core.get_text(strip=True))
                if raw:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except ValueError:
                        pass

        # 3. Target #corePrice_desktop active containers
        for core_d in soup.select("#corePrice_desktop span.apexPriceToPay span.a-offscreen, #corePrice_desktop span.a-price-whole"):
            if not _is_inside_ignored_offer_box(core_d):
                raw = re.sub(r"[^\d.]", "", core_d.get_text(strip=True))
                if raw:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except ValueError:
                        pass

        # 4. Standard buybox price blocks
        for bb in soup.select("#priceblock_ourprice, #priceblock_dealprice, #priceblock_saleprice"):
            if not _is_inside_ignored_offer_box(bb):
                raw = re.sub(r"[^\d.]", "", bb.get_text(strip=True))
                if raw:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except ValueError:
                        pass

        # 5. General span.a-price span.a-offscreen (strictly filtered against inactive/alternate cards)
        for off in soup.select("span.a-price span.a-offscreen"):
            if not _is_inside_ignored_offer_box(off):
                raw = re.sub(r"[^\d.]", "", off.get_text(strip=True))
                if raw:
                    try:
                        val = float(raw)
                        if val > 0:
                            return val
                    except ValueError:
                        pass

    # 3. Secondary pattern: r'₹\s*([0-9,]+(?:\.[0-9]{2})?)'
    rupee_pat = re.compile(r"₹\s*([0-9,]+(?:\.[0-9]{2})?)")
    for src in [text, raw_html]:
        if src:
            m = rupee_pat.search(src)
            if m:
                try:
                    val = float(m.group(1).replace(",", ""))
                    if val > 0:
                        return val
                except ValueError:
                    pass

    # 4. JSON-LD metadata embedded in script tags (<script type="application/ld+json">) containing "price": "..."
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            content = tag.string or tag.get_text() or ""
            if not content.strip():
                continue
            data = json.loads(content)
            if isinstance(data, list):
                data = data[0] if data else {}
            offers = data.get("offers", data.get("Offers", {}))
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = offers.get("price") or offers.get("Price")
            if price is not None:
                val = float(str(price).replace(",", "").strip())
                if val > 0:
                    return val
        except Exception:
            pass

    if raw_html:
        json_price_match = re.search(r'"price"\s*:\s*"?([0-9,]+(?:\.[0-9]{2})?)"?', raw_html)
        if json_price_match:
            try:
                val = float(json_price_match.group(1).replace(",", ""))
                if val > 0:
                    return val
            except ValueError:
                pass

    # 5. Schema.org microdata meta itemprop="price" or itemprop="price"
    micro_price = soup.find("meta", attrs={"itemprop": "price"}) or soup.find(attrs={"itemprop": "price"})
    if micro_price:
        val = micro_price.get("content") or micro_price.get_text(strip=True)
        if val:
            raw = re.sub(r"[^\d.]", "", str(val))
            if raw:
                try:
                    p = float(raw)
                    if p > 0:
                        return p
                except ValueError:
                    pass

    # 6. Open Graph price
    og_price = soup.find("meta", property="product:price:amount") or soup.find("meta", attrs={"name": "price"})
    if og_price and og_price.get("content"):
        try:
            p = float(og_price["content"].replace(",", ""))
            if p > 0:
                return p
        except ValueError:
            pass

    # 7. Common CSS classes
    price_classes = [
        "price", "mrp", "selling-price", "sp", "offer-price",
        "product-price", "Price", "finalPrice", "pdp-price", "css-1vsd37c",
    ]
    for cls in price_classes:
        tag = soup.find(class_=re.compile(cls, re.I)) or soup.find(id=re.compile(cls, re.I))
        if tag:
            raw = re.sub(r"[^\d.]", "", tag.get_text())
            if raw:
                try:
                    p = float(raw)
                    if p > 0:
                        return p
                except ValueError:
                    pass

    # 8. Regex on raw text
    mrp_pat = re.compile(
        r"(?:MRP|M\.R\.P\.?|Maximum\s+Retail\s+Price)[^₹Rs\d]*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.[0-9]{1,2})?)",
        re.IGNORECASE,
    )
    m = mrp_pat.search(text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    # 9. Any ₹ / Rs. / INR price pattern
    price_pat = re.compile(r"(?:₹|Rs\.?|INR)[\s]*([\d,]+(?:\.[0-9]{1,2})?)", re.IGNORECASE)
    m = price_pat.search(text[:4000])
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass

    return None


def _extract_quantity(soup, text: str) -> Optional[str]:
    """
    Extract Net Quantity / Weight.
    Extracts text from <meta name="description">, product specifications, or title.
    """
    qty_pat = re.compile(
        r"([\d]+(?:[.,][\d]+)?)\s*(kg|g|gm|gram|mg|l|lt|ltr|litre|liter|ml|millilitre|units?|pcs?|nos?|pieces?|pack(?:\s+of\s+\d+)?)",
        re.IGNORECASE,
    )

    # 1. Product specification container
    spec_container = soup.find(class_=re.compile(r"spec|detail|nutrition|pack", re.I)) or \
                     soup.find(id=re.compile(r"spec|detail|nutrition|pack", re.I))
    if spec_container:
        m = qty_pat.search(spec_container.get_text())
        if m:
            return f"{m.group(1)} {m.group(2).upper()}"

    # 2. Title / h1
    title_tag = soup.find("h1") or soup.find("title")
    if title_tag:
        m = qty_pat.search(title_tag.get_text())
        if m:
            return f"{m.group(1)} {m.group(2).upper()}"

    # 3. Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"}) or \
                soup.find("meta", property="og:description")
    if meta_desc and meta_desc.get("content"):
        m = qty_pat.search(meta_desc["content"])
        if m:
            return f"{m.group(1)} {m.group(2).upper()}"

    # 4. Fallback on page text
    m = qty_pat.search(text[:4000])
    if m:
        return f"{m.group(1)} {m.group(2).upper()}"

    return None


def _extract_brand(soup, text: str) -> Optional[str]:
    """Extract brand / manufacturer."""
    # 1. JSON-LD brand
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                data = data[0]
            brand = data.get("brand", {})
            if isinstance(brand, dict):
                brand = brand.get("name", "")
            if brand:
                return str(brand).strip()
        except Exception:
            pass

    # 2. Meta brand
    for attr in [{"property": "og:brand"}, {"name": "brand"}, {"itemprop": "brand"}]:
        tag = soup.find("meta", attrs=attr)
        if tag and tag.get("content"):
            return tag["content"].strip()

    # 3. Common selectors
    brand_classes = ["brand", "Brand", "manufacturer", "vendor", "seller-name"]
    for cls in brand_classes:
        tag = soup.find(class_=re.compile(cls, re.I)) or soup.find(attrs={"itemprop": "brand"})
        if tag:
            val = tag.get_text(strip=True)
            if val and len(val) < 100:
                return val

    # 4. Regex
    brand_pat = re.compile(r"(?:Brand|Manufacturer|Sold\s+by)[:\s]+([A-Za-z0-9 &.,'-]{2,60})", re.IGNORECASE)
    m = brand_pat.search(text[:5000])
    if m:
        return m.group(1).strip()

    return None


def _extract_country(soup, text: str) -> Optional[str]:
    """Extract country of origin from listing."""
    for tr in soup.find_all(["tr", "li", "div"]):
        t = tr.get_text()
        if "country of origin" in t.lower() or "made in" in t.lower():
            m = re.search(r"(?:Country of Origin|Made in)[:\s]+([A-Za-z ]{2,30})", t, re.I)
            if m:
                val = m.group(1).strip()
                if len(val) < 30 and not any(w in val.lower() for w in ["unknown", "n/a", "see"]):
                    return val

    m = re.search(r"(?:Country\s+of\s+Origin|Made\s+in)[\s:]*([A-Za-z ]{2,30})", text[:8000], re.I)
    if m:
        val = m.group(1).strip()
        if len(val) < 30:
            return val

    return None


def _extract_usp(soup, text: str) -> Optional[str]:
    """
    Extract Unit Sale Price (USP) declared on e-commerce listing under Rule 6(10)/6(11).
    e.g. '(₹0.20 / g)', '₹15.00 / 100 g', 'USP: ₹0.30 per ml', '₹1.50 / count'
    """
    # 1. Look in specific HTML elements/classes
    usp_selectors = [
        {"class_": re.compile(r"price-per-unit|unit-price|a-price-unit|UnitSalePrice", re.I)},
        {"class_": "a-size-small a-color-price"},
        {"attrs": {"itemprop": "unitPrice"}},
    ]
    for sel in usp_selectors:
        tag = soup.find(**sel)
        if tag:
            t = tag.get_text(strip=True)
            if re.search(r"(?:₹|Rs\.?|INR|\/|per)", t, re.I):
                return t

    # 2. Look for (₹... / unit) pattern in text (classic Amazon format)
    m = re.search(r"\((?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d+)?\s*/\s*[A-Za-z0-9 ]+\)", text)
    if m:
        return m.group(0).strip("()")

    # 3. Look for explicit USP / Unit Price pattern
    m = re.search(r"(?:USP|Unit\s+(?:Sale\s+)?Price)[\s:]*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)\s*([A-Za-z0-9 ]{1,20})", text, re.I)
    if m:
        return f"₹ {m.group(1)} / {m.group(2).strip()}"

    # 4. Look for price per standard weight/volume/count pattern
    m = re.search(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)\s*(?:/|per)\s*(100\s*g|100\s*ml|kg|g|gm|l|lt|litre|liter|ml|count|piece|unit|pack)\b", text, re.I)
    if m:
        return f"₹ {m.group(1)} / {m.group(2)}"

    return None


def _extract_image_url(soup, base_url: str) -> Optional[str]:
    """
    Extract primary product packaging/photo URL.
    Checks: <meta property="og:image"> or primary <img> src.
    """
    # 1. Open Graph image (skip generic logos / placeholder previews)
    og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
    if og_img and og_img.get("content"):
        c = og_img["content"].strip()
        if not c.endswith(".svg") and not any(bad in c.lower() for bad in ["logo", "icon", "placeholder", "badge"]):
            return urljoin(base_url, c)

    # 2. Schema.org JSON-LD image
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
            if isinstance(data, list):
                data = data[0]
            img = data.get("image")
            if isinstance(img, list) and img:
                img = img[0]
            if isinstance(img, dict):
                img = img.get("url")
            if isinstance(img, str) and img.startswith("http"):
                return img
        except Exception:
            pass

    # 3. Specific product packaging image tags (Open Food Facts, Amazon, BigBasket, etc.)
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        src = src.strip()
        if not src or src.endswith(".svg") or src.endswith(".gif"):
            continue
        if any(bad in src.lower() for bad in ["logo", "icon", "banner", "badge", "tracker", "avatar"]):
            continue
        # Check packaging indicators
        if any(ind in src.lower() for ind in ["front_", "images/products", "bbassets", "uploads/p/", "product", "item", "pdp", "landingimage"]):
            if "bbassets.com" in src and "/p/s/" in src:
                src = src.replace("/p/s/", "/p/l/")
            return urljoin(base_url, src)

    # 4. Generic primary image
    img_tag = soup.find("img", class_=re.compile(r"product.*image|pdp.*image|main.*image", re.I)) or \
              soup.find("img", id=re.compile(r"product.*image|pdp.*image|landingImage", re.I)) or \
              soup.find("img", attrs={"itemprop": "image"})
    if img_tag:
        src = img_tag.get("src") or img_tag.get("data-src") or ""
        if src and not src.endswith(".svg") and "logo" not in src.lower():
            return urljoin(base_url, src.strip())

    return None


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def scrape_listing(url: str) -> dict:
    """
    Scrape a product listing URL and return extracted fields.
    NEVER substitutes hardcoded or mock data.
    """
    domain = _get_domain(url)
    base = {
        "scraped": False,
        "blocked": False,
        "url": url,
        "domain": domain,
        "product_title": None,
        "mrp": None,
        "net_quantity": None,
        "usp": None,
        "manufacturer": None,
        "country_of_origin": None,
        "image_url": None,
        "page_text": None,
        "error": None,
    }

    if not url or not url.startswith("http"):
        base["error"] = "Invalid URL — must start with http:// or https://"
        return base

    logger.info("Scraping listing URL: %s", url)
    html, status_code, err, final_url = _fetch_html(url)
    if final_url and final_url != url:
        base["url"] = final_url
        domain = _get_domain(final_url)
        base["domain"] = domain

    if not html:
        base["error"] = err or f"Could not fetch the page from {domain}."
        if err == BOT_BLOCK_ERROR or (err and "blocked" in err.lower()):
            base["blocked"] = True
        return base

    is_blocked_status = (err == BOT_BLOCK_ERROR) or (status_code in (403, 429, 503))

    try:
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator="\n", strip=True)

        fields = {
            "product_title": _extract_title(soup, text),
            "mrp": _extract_mrp(soup, text, html=html),
            "net_quantity": _extract_quantity(soup, text),
            "usp": _extract_usp(soup, text),
            "manufacturer": _extract_brand(soup, text),
            "country_of_origin": _extract_country(soup, text),
            "image_url": _extract_image_url(soup, final_url or url),
        }

        # Fallback price extraction on entire HTML if mrp is still None
        if not fields["mrp"] and html:
            m_amz = re.search(r'class="a-price-whole">([0-9,]+)', html)
            if m_amz:
                try:
                    fields["mrp"] = float(m_amz.group(1).replace(",", "").strip())
                except ValueError:
                    pass
            if not fields["mrp"]:
                m_rupee = re.search(r'₹\s*([0-9,]+(?:\.[0-9]{2})?)', html)
                if m_rupee:
                    try:
                        fields["mrp"] = float(m_rupee.group(1).replace(",", "").strip())
                    except ValueError:
                        pass
            if not fields["mrp"]:
                m_json = re.search(r'"price"\s*:\s*"?([0-9,]+(?:\.[0-9]{2})?)"?', html)
                if m_json:
                    try:
                        fields["mrp"] = float(m_json.group(1).replace(",", "").strip())
                    except ValueError:
                        pass

        # If blocked (403/503), parse meta tags (<meta property="og:description"> or title) as fallback
        if is_blocked_status:
            meta_desc = (
                soup.find("meta", property="og:description") or
                soup.find("meta", attrs={"name": "description"}) or
                soup.find("meta", attrs={"name": "twitter:description"})
            )
            desc_content = meta_desc.get("content") if meta_desc else ""

            # Fallback for title
            if not fields["product_title"]:
                title_tag = soup.find("title")
                if title_tag and title_tag.get_text(strip=True):
                    fields["product_title"] = title_tag.get_text(strip=True)

            # Fallback for MRP from og:description or title
            if not fields["mrp"] and desc_content:
                m_price = re.search(r"₹\s*([0-9,]+(?:\.[0-9]{2})?)", desc_content) or re.search(r"(?:Rs\.?|INR)\s*([0-9,]+(?:\.[0-9]{2})?)", desc_content)
                if m_price:
                    try:
                        fields["mrp"] = float(m_price.group(1).replace(",", ""))
                    except ValueError:
                        pass

            # Fallback for quantity from og:description
            if not fields["net_quantity"] and desc_content:
                m_qty = re.search(r"(\d+(?:\.\d+)?)\s*(g|gm|gms|kg|ml|l)\b", desc_content, re.I)
                if m_qty:
                    fields["net_quantity"] = f"{m_qty.group(1)}{m_qty.group(2).lower()}"

        base.update(fields)
        base["page_text"] = text[:5000]
        base["scraped"] = any(v is not None for v in [fields["product_title"], fields["mrp"], fields["net_quantity"], fields["manufacturer"]])

        if not base["scraped"] and is_blocked_status:
            base["blocked"] = True
            base["error"] = BOT_BLOCK_ERROR
        elif not base["scraped"]:
            base["error"] = (
                f"Page was fetched from {domain} but product declarations could not be extracted. "
                "The site layout may not be supported or requires JavaScript rendering."
            )

        logger.info(
            "Scrape result for %s — Title: %s, MRP: %s, Qty: %s, Brand: %s, Img: %s",
            domain, base["product_title"], base["mrp"], base["net_quantity"], base["manufacturer"], bool(base["image_url"]),
        )
    except Exception as exc:
        logger.error("Scraping parse error: %s", exc, exc_info=True)
        base["error"] = f"Parse error while extracting product info: {exc}"
        if is_blocked_status:
            base["blocked"] = True

    return base
