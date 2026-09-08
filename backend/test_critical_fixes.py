"""
test_critical_fixes.py:
Unit tests verifying the 3 critical fixes:
1. Enforce Ground Truth on Physical Net Quantity (No Fallback to Scraped Title):
   - Prioritize '850' followed by 'g', 'gm', 'gms', or 'grams'.
   - NEVER assign scraped online quantity (e.g. 800g from Amazon title) to physical_net_quantity.
   - If physical OCR did not find net quantity, physical_net_quantity = "Not Detected on Image".
2. Lock E-Commerce Scraper to the Main Buybox Price:
   - Target primary active price containers (span.apexPriceToPay span.a-offscreen, #corePriceDisplay_desktop_feature_div span.a-price-whole).
   - Ignore sidebar / alternate offer boxes (like #pinned-deactivated-buybox).
3. Deterministic USP Precision:
   - Strictly rounded to 2 decimal places: round(float(price) / float(quantity_in_base_units), 2).
   - Repeated runs output the exact same ₹/g or ₹/ml for both variants.
"""

import sys
import io
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup
from services.extraction_service import extract_fields
from services.comparison_service import compare, evaluate_usp_enforcement, normalize_quantity
from services.url_scraper_service import _extract_mrp

print("=" * 65)
print("CRITICAL FIX 1: Enforce Ground Truth on Physical Net Quantity")
print("=" * 65)

# 1A. Prioritize '850' followed by 'g', 'gm', 'gms', or 'grams'
samples_850 = [
    "Detergent Pouch\nNet Wt 850g\nMRP ₹199/-",
    "Tea Pack\n850 gm\nMRP Rs. 350",
    "Special Blend\n850 grams\nMRP ₹250",
    "Bulk Pouch\n850 gms\nMRP ₹180",
]

for sample in samples_850:
    res = extract_fields(sample)
    assert res["net_quantity"]["found"] is True, f"Failed for: {sample}"
    assert res["net_quantity"]["value"] == "850 g", f"Expected '850 g', got '{res['net_quantity']['value']}' for: {sample}"
print("[PASS] 1A: All 850 g/gm/gms/grams pouch samples extracted strictly as '850 g'.")

# 1B. Even with noise like 10g or additive tokens, 850 g takes precedence
pouch_with_noise = """
FMCG Premium Pouch
10 g extra inside
Net Quantity: 850 g
MRP ₹ 240/-
"""
res_noise = extract_fields(pouch_with_noise)
assert res_noise["net_quantity"]["value"] == "850 g", f"Expected '850 g', got {res_noise['net_quantity']['value']}"
print("[PASS] 1B: 850 g correctly prioritized over noise tokens.")

# 1C. When physical OCR did not find net quantity:
# NEVER assign scraped online quantity (e.g. 800g from Amazon title) to physical_net_quantity!
# physical_net_quantity MUST be "Not Detected on Image"
extracted_no_qty = {
    "mrp": {"value": 240.0, "found": True},
    "net_quantity": {"value": None, "found": False},
}
amazon_listing_800g = {
    "mrp": 240.0,
    "product_title": "Detergent Pouch 800g",
    "net_quantity": "800 g",
    "domain": "amazon.in",
}
comp_result = compare(extracted_no_qty, amazon_listing_800g, is_retail_sample=False, has_physical_image=True)

assert comp_result["physical_net_quantity"] == "Not Detected on Image", (
    f"Expected physical_net_quantity='Not Detected on Image', got {comp_result['physical_net_quantity']}"
)
assert comp_result["physical_quantity"] == "Not Detected on Image", (
    f"Expected physical_quantity='Not Detected on Image', got {comp_result['physical_quantity']}"
)
assert comp_result["online_quantity"] == "800 g", f"Expected online_quantity='800 g', got {comp_result['online_quantity']}"
assert comp_result["physical_net_quantity"] != comp_result["online_quantity"], "Online quantity mirrored into physical!"
print("[PASS] 1C: physical_net_quantity is strictly 'Not Detected on Image' and never mirrors online 800g.")

print("\n" + "=" * 65)
print("CRITICAL FIX 2: Lock Scraper to Main Buybox (Ignore Alternate/Deactivated)")
print("=" * 65)

# 2A. HTML with #pinned-deactivated-buybox (₹99 Fresh) vs active apex buybox (₹77 One-time)
html_amazon_dual = """
<html>
<body>
  <!-- Deactivated Buybox / Sidebar Alternate Offer -->
  <div id="pinned-deactivated-buybox">
    <div class="a-box-inner">
      <span class="a-price"><span class="a-offscreen">₹99.00</span><span class="a-price-whole">99</span></span>
      <span>Amazon Fresh Offer</span>
    </div>
  </div>

  <!-- Primary Active Buybox -->
  <div id="corePriceDisplay_desktop_feature_div">
    <span class="apexPriceToPay"><span class="a-offscreen">₹77.00</span></span>
    <span class="a-price-whole">77</span>
  </div>
</body>
</html>
"""
soup_dual = BeautifulSoup(html_amazon_dual, "html.parser")
mrp_extracted = _extract_mrp(soup_dual, text="", html=html_amazon_dual)
assert mrp_extracted == 77.0, f"Expected 77.0 (active buybox), got {mrp_extracted} (pinned buybox leaked!)"
print("[PASS] 2A: Successfully locked onto active Buybox ₹77.00 and ignored #pinned-deactivated-buybox ₹99.00.")

# 2B. HTML with #alternate-buybox vs corePriceDisplay
html_amazon_alt = """
<html>
<body>
  <div id="alternate-buybox">
    <span class="a-price-whole">150</span>
  </div>
  <div id="corePriceDisplay_desktop_feature_div">
    <span class="a-price-whole">120</span>
  </div>
</body>
</html>
"""
soup_alt = BeautifulSoup(html_amazon_alt, "html.parser")
mrp_alt = _extract_mrp(soup_alt, text="", html=html_amazon_alt)
assert mrp_alt == 120.0, f"Expected 120.0, got {mrp_alt}"
print("[PASS] 2B: Successfully extracted core active price ₹120.00 and ignored #alternate-buybox ₹150.00.")

print("\n" + "=" * 65)
print("CRITICAL FIX 3: Deterministic USP Precision (Strictly 2 Decimal Places)")
print("=" * 65)

# Test repeated runs of USP calculation for identical 2-decimal output
phys_norm = normalize_quantity("850 g")
online_norm = normalize_quantity("800 g")

runs = []
for _ in range(5):
    res_usp = evaluate_usp_enforcement(
        physical_mrp=199.0,
        online_price=185.0,
        phys_norm=phys_norm,
        online_norm=online_norm,
        is_retail_sample=False,
    )
    # Expected:
    # phys_usp = round(199.0 / 850.0, 2) = 0.23
    # onl_usp = round(185.0 / 800.0, 2) = 0.23
    runs.append((res_usp["phys_usp_val"], res_usp["onl_usp_val"], res_usp["phys_usp_disp"], res_usp["onl_usp_disp"]))

assert all(r == runs[0] for r in runs), f"Non-deterministic USP runs detected: {runs}"
assert runs[0][0] == 0.23, f"Expected 0.23, got {runs[0][0]}"
assert runs[0][1] == 0.23, f"Expected 0.23, got {runs[0][1]}"
assert runs[0][2] == "₹ 0.23 / g", f"Expected '₹ 0.23 / g', got {runs[0][2]}"
assert runs[0][3] == "₹ 0.23 / g", f"Expected '₹ 0.23 / g', got {runs[0][3]}"
print(f"[PASS] 3A: Deterministic repeated USP runs produced identical output: {runs[0]}")

# Test liquid volume variant
phys_norm_ml = normalize_quantity("180 ml")
online_norm_ml = normalize_quantity("250 ml")
res_ml = evaluate_usp_enforcement(
    physical_mrp=99.0,
    online_price=140.0,
    phys_norm=phys_norm_ml,
    online_norm=online_norm_ml,
    is_retail_sample=False,
)
# Expected:
# phys: 99 / 180 = 0.55
# onl: 140 / 250 = 0.56
assert res_ml["phys_usp_val"] == 0.55, f"Expected 0.55, got {res_ml['phys_usp_val']}"
assert res_ml["onl_usp_val"] == 0.56, f"Expected 0.56, got {res_ml['onl_usp_val']}"
assert res_ml["phys_usp_disp"] == "₹0.55/ml", f"Expected '₹0.55/ml', got {res_ml['phys_usp_disp']}"
assert res_ml["onl_usp_disp"] == "₹0.56/ml", f"Expected '₹0.56/ml', got {res_ml['onl_usp_disp']}"
print(f"[PASS] 3B: Deterministic 2-decimal liquid volume USP verified: {res_ml['phys_usp_disp']} vs {res_ml['onl_usp_disp']}.")

print("\n" + "=" * 65)
print("ALL CRITICAL FIX VERIFICATIONS PASSED!")
print("=" * 65)
