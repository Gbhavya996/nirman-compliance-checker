import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

print("=" * 60)
print("TEST 1: Regex & Field Extraction")
print("=" * 60)
from services.extraction_service import extract_fields
from services.rule_engine import evaluate

label_text = """
NIRMAN
Net Wt. When Packed 75g
₹ 38.00 / Incl. of all taxes
Manufacturer: Nirman FMCG Ltd, New Delhi 110020
Consumer Care: 1800-111-2222
"""

fields = extract_fields(label_text)
print("Net Quantity:", fields["net_quantity"])
print("Physical MRP:", fields["mrp"])
print("Mfg Date:", fields["mfg_date"])

assert fields["net_quantity"]["value"] == "75g", f"Expected 75g, got {fields['net_quantity']['value']}"
assert fields["net_quantity"]["found"] is True
assert fields["mrp"]["value"] == 38.0, f"Expected 38.0, got {fields['mrp']['value']}"
assert fields["mrp"]["found"] is True
assert fields["mfg_date"]["value"] is None, f"Expected None for mfg_date, got {fields['mfg_date']['value']}"
print("[PASS] Net Quantity extracted correctly as: 75g")
print("[PASS] Physical MRP extracted correctly as: 38.00")
print("[PASS] Mfg Date correctly ignored 75 and set to: None")

violations = evaluate(fields, label_text)
for v in violations:
    if v["field"] == "Net Quantity":
        assert v["status"] == "PASS", f"Net Quantity failed: {v}"
        print("[PASS] Net Quantity Rule Engine status: PASS")
    if v["field"] == "MRP":
        assert v["status"] == "PASS", f"MRP failed: {v}"
        print("[PASS] MRP Rule Engine status: PASS")

print("\n" + "=" * 60)
print("TEST 2: Comparison Enforcement Engine")
print("=" * 60)
from services.comparison_service import compare

# Case A: Online Price (49) > Physical MRP (38) with matching 75g quantity
res_a = compare(fields, {"mrp": 49.0, "domain": "amazon.in", "net_quantity": "75g"}, is_retail_sample=False)
assert res_a["status"] == "FAIL"
assert res_a["case"] == "CASE_A"
assert "VIOLATION" in res_a["verdict"]
assert res_a["notice_type"] == "PLATFORM_SHOW_CAUSE"
assert "Show-Cause" in res_a["notice_button_label"]
print("[PASS] Case A (Online Fraud) evaluated:")
print("       Status:", res_a["status"])
print("       Verdict:", res_a["verdict"])
print("       Delta:", res_a["delta_str"])
print("       Action Directive:", res_a["action"])
print("       Button Label:", res_a["notice_button_label"])

# Case B: Physical MRP (49) > Online Price (38) with is_retail_sample=True
fields_b = dict(fields)
fields_b["mrp"] = {"value": 49.0, "found": True}
res_b = compare(fields_b, {"mrp": 38.0, "domain": "catalog.brand.com", "net_quantity": "75g"}, is_retail_sample=True)
assert res_b["status"] == "FAIL"
assert res_b["case"] == "CASE_B"
assert "TAMPERING" in res_b["verdict"]
assert res_b["notice_type"] == "RETAILER_COMPOUND_OFFENCE"
assert "Retailer" in res_b["notice_button_label"]
print("\n[PASS] Case B (Retail Store Tampering) evaluated:")
print("       Status:", res_b["status"])
print("       Verdict:", res_b["verdict"])
print("       Delta:", res_b["delta_str"])
print("       Action Directive:", res_b["action"])
print("       Button Label:", res_b["notice_button_label"])

# Case C: Online Price <= Physical MRP
res_c = compare(fields, {"mrp": 35.0, "domain": "amazon.in", "net_quantity": "75g"}, is_retail_sample=False)
assert res_c["status"] == "PASS"
assert res_c["case"] == "CASE_C"
print("\n[PASS] Case C (Compliant Pass) evaluated:")
print("       Status:", res_c["status"])
print("       Verdict:", res_c["verdict"])

print("\n" + "=" * 60)
print("TEST 2B: Rule 6(11) Unit Sale Price (USP) Variant Comparison")
print("=" * 60)
fields_pouch = {
    "mrp": {"value": 10.0, "found": True},
    "net_quantity": {"value": "10 ml", "found": True},
    "manufacturer": {"value": "Head & Shoulders", "found": True},
}
# 10 ml @ ₹10 (₹1.00/ml) vs 180 ml @ ₹150 (₹0.83/ml) -> Should PASS (Compliant bulk pricing)
res_usp_pass = compare(fields_pouch, {"mrp": 150.0, "net_quantity": "180 ml", "domain": "amazon.in"}, is_retail_sample=False)
assert res_usp_pass["status"] == "PASS", f"Expected PASS, got {res_usp_pass['status']}"
assert res_usp_pass["quantities_match"] is False
assert "RULE 6(11) COMPLIANT" in res_usp_pass["verdict"]
assert res_usp_pass["physical_usp"] == 1.0
assert res_usp_pass["online_usp"] == 0.83
print("[PASS] 10 ml @ ₹10 vs 180 ml @ ₹150 evaluates to Rule 6(11) PASS:")
print("       Verdict:", res_usp_pass["verdict"])
print("       USP Comparison:", res_usp_pass["usp_comparison"])
print("       Delta:", res_usp_pass["delta_str"])

# 10 ml @ ₹10 (₹1.00/ml) vs 180 ml @ ₹220 (₹1.22/ml) -> Should FAIL (Unit rate overcharging)
res_usp_fail = compare(fields_pouch, {"mrp": 220.0, "net_quantity": "180 ml", "domain": "amazon.in"}, is_retail_sample=False)
assert res_usp_fail["status"] == "FAIL", f"Expected FAIL, got {res_usp_fail['status']}"
assert "RULE 6(11) VIOLATION" in res_usp_fail["verdict"]
assert res_usp_fail["notice_type"] == "PLATFORM_SHOW_CAUSE"
print("\n[PASS] 10 ml @ ₹10 vs 180 ml @ ₹220 evaluates to Rule 6(11) FAIL:")
print("       Verdict:", res_usp_fail["verdict"])
print("       USP Comparison:", res_usp_fail["usp_comparison"])
print("       Delta:", res_usp_fail["delta_str"])

print("\n" + "=" * 60)
print("TEST 2C: SKU / Variant Mismatch Protection")
print("=" * 60)
# Incompatible units: 10 ml vs 100 g
res_mismatch_units = compare(fields_pouch, {"mrp": 90.0, "net_quantity": "100 g", "domain": "amazon.in"}, is_retail_sample=False)
assert res_mismatch_units["status"] == "VARIANT_MISMATCH"
assert res_mismatch_units["is_variant_mismatch"] is True
assert res_mismatch_units["action"] is None
assert "SKU / VARIANT MISMATCH" in res_mismatch_units["verdict"]
print("[PASS] Incompatible units (10 ml vs 100 g) caught as VARIANT_MISMATCH (no false Over-MRP):")
print("       Status:", res_mismatch_units["status"])
print("       Verdict:", res_mismatch_units["verdict"])

# Unparsed online quantity
res_unparsed = compare(fields_pouch, {"mrp": 90.0, "net_quantity": None, "domain": "amazon.in"}, is_retail_sample=False)
assert res_unparsed["status"] == "VARIANT_MISMATCH"
assert res_unparsed["is_variant_mismatch"] is True
print("\n[PASS] Missing/unparsed online quantity caught as VARIANT_MISMATCH (no false Over-MRP):")
print("       Status:", res_unparsed["status"])
print("       Verdict:", res_unparsed["verdict"])

print("\n" + "=" * 60)
print("TEST 2D: Surf Excel Per-Gram (1g) Normalization & Noise Cleanup")
print("=" * 60)
surf_text = """
Surf Excel Quick Wash Detergent Powder
50 g + 20 g EXTRA**
MRP ? 10,00
USP ? 0.20 per g
00l
"""
surf_fields = extract_fields(surf_text)
assert surf_fields["mrp"]["value"] == 10.0, f"Expected 10.0, got {surf_fields['mrp']['value']}"
assert surf_fields["net_quantity"]["value"] == "70 g", f"Expected '70 g', got {surf_fields['net_quantity']['value']}"
assert surf_fields["usp"]["value"] == "0.20 per g", f"Expected '0.20 per g', got {surf_fields['usp']['value']}"
print("[PASS] Surf Excel MRP extracted strictly as 10.00 from 'MRP ? 10,00'")
print("[PASS] Surf Excel Net Quantity computed as 70 g from '50 g + 20 g EXTRA**' (noise '00l' cleaned)")
print("[PASS] Surf Excel USP extracted as '0.20 per g' from 'USP ? 0.20 per g'")

surf_listing = {
    "mrp": 312.0,
    "net_quantity": "2 kg",
    "product_title": "Surf Excel Quick Wash Detergent Powder 2 kg",
    "domain": "amazon.in"
}
res_surf = compare(surf_fields, surf_listing, is_retail_sample=False)
assert res_surf["status"] == "PASS", f"Expected PASS, got {res_surf['status']}"
assert res_surf["physical_mrp"] == "₹ 10.00", f"Expected '₹ 10.00', got {res_surf['physical_mrp']}"
assert res_surf["online_price"] == "₹ 312.00", f"Expected '₹ 312.00', got {res_surf['online_price']}"
assert res_surf["physical_usp"] == "₹ 0.14 / g", f"Expected '₹ 0.14 / g', got {res_surf['physical_usp']}"
assert res_surf["online_usp"] in ("₹ 0.16 / g", "₹ 0.156 / g"), f"Expected '₹ 0.16 / g', got {res_surf['online_usp']}"
assert res_surf["delta_str"] in ("+₹0.02 / g", "+₹0.013 / g"), f"Expected '+₹0.02 / g', got {res_surf['delta_str']}"
assert res_surf["is_variant_mismatch"] is False, "Expected is_variant_mismatch to be False"
assert "RULE 6(11) COMPLIANT: Unit Sale Price normalized per gram for SKU variation." in res_surf["verdict"]
print("[PASS] Physical MRP: ₹ 10.00")
print("[PASS] Online Price: ₹ 312.00")
print("[PASS] Physical USP:", res_surf["physical_usp"])
print("[PASS] Online USP:", res_surf["online_usp"])
print("[PASS] Regulatory Finding:", res_surf["verdict"])
print("[PASS] Status:", res_surf["status"])

print("\n" + "=" * 60)
print("TEST 2E: Vim Dishwash Gel MRP & Net Quantity Extraction")
print("=" * 60)
vim_text = """
TEASPOON CLEANS A SINK FULL
USE AS SHOWN BELOW
Take 1 tsp (3.75 ml) of Vim gel
Mix it in one bowl of water (40 ml)
Dip the scrubber; squeeze to get powerful lather
CONCENTRATED GEL
VIM DISHWASH LIQUID GEL
0034980-08-444CHi004264821732
*MRP ₹ 20.00  ₹ 15.00 (Incl. of all taxes)
FOR USP, NET VOL 120 ml
MFD & Batch No: See Top Seal
#120 ml
Hindustan Unilever Ltd
Country of Origin: India
"""

vim_fields = extract_fields(vim_text)
print("Vim Extracted MRP:", vim_fields["mrp"])
print("Vim Extracted Net Quantity:", vim_fields["net_quantity"])
print("Vim Extracted MRP Text:", vim_fields["mrp_text"])

# 1. Verify Erroneous MRP Detection (₹34980 False Match) is prevented
assert vim_fields["mrp"]["value"] != 34980.0, "MRP incorrectly matched internal serial code 34980"
assert vim_fields["mrp"] == "15.00", f"Expected '15.00', got {vim_fields['mrp']}"
assert vim_fields["mrp"]["value"] == 15.0, f"Expected 15.0, got {vim_fields['mrp']['value']}"
print("[PASS] Vim dual/promotional MRP correctly extracted lower price: ₹15.00 (batch code 34980 discarded)")

# 2. Verify Net Quantity ignores usage instructions (3.75 ml / 40 ml) and matches 120 ml
assert vim_fields["net_quantity"]["value"] != "3.75 ml" and vim_fields["net_quantity"]["value"] != "3.75ml", "Net quantity grabbed usage instruction 3.75 ml"
assert vim_fields["net_quantity"]["value"] != "40 ml" and vim_fields["net_quantity"]["value"] != "40ml", "Net quantity grabbed dilution instruction 40 ml"
assert vim_fields["net_quantity"] == "120 ml", f"Expected '120 ml', got {vim_fields['net_quantity']}"
assert vim_fields["net_quantity"]["value"] == "120 ml", f"Expected '120 ml', got {vim_fields['net_quantity']['value']}"
print("[PASS] Vim Net Quantity correctly extracted as '120 ml' (usage instruction 3.75 ml ignored)")

# 3. Verify MRP Text Output
assert vim_fields["mrp_text"] == "₹ 15.00 (Incl. of all taxes)", f"Expected '₹ 15.00 (Incl. of all taxes)', got {vim_fields['mrp_text']}"
print("[PASS] Vim MRP Text correctly set to '₹ 15.00 (Incl. of all taxes)'")

# Fallback test with single statutory MRP format
vim_fallback_text = """
VIM DISHWASH LIQUID GEL
Take 1 tsp (3.75 ml) of Vim gel
MRP ₹ 15.00 (INCL. OF ALL TAXES)
#120 ml
"""
vim_fb_fields = extract_fields(vim_fallback_text)
assert vim_fb_fields["mrp"] == "15.00"
assert vim_fb_fields["net_quantity"] == "120 ml"
print("[PASS] Vim fallback statutory MRP & seal net quantity extraction verified: ₹15.00, 120 ml")

print("\n" + "=" * 60)
print("TEST 2F: Fab Detergent Powder & Consolidated Validation")
print("=" * 60)
fab_sample_text = """
how to use fab?
Take 1 cap (40 ml) for bucket wash
45caps (60 ml) for medium machine wash
Manufactured by: Rama Krishna Packaging Private Limited
Net Quantity 800g
*MRP ₹ 99/-
USP ₹ 0.12 / g
MFD: 08/2026
(Incl. of all taxes)
Country of Origin: India
"""

fab_fields = extract_fields(fab_sample_text)
print("Fab Extracted MRP:", fab_fields["mrp"])
print("Fab Extracted Net Quantity:", fab_fields["net_quantity"])
print("Fab Extracted USP:", fab_fields["usp"])
print("Fab Extracted MFD:", fab_fields["mfg_date"])

# Verify Fab parsing
assert fab_fields["mrp"] == 99.0 or fab_fields["mrp"] == "99.00", f"Expected 99.00, got {fab_fields['mrp']}"
assert fab_fields["net_quantity"] == "800 g", f"Expected '800 g', got {fab_fields['net_quantity']}"
assert fab_fields["usp"] == "0.12 per g" or fab_fields["usp"] == "₹0.12/g", f"Expected '0.12 per g', got {fab_fields['usp']}"
assert fab_fields["mfg_date"] == "08/2026" or fab_fields["mfd"] == "08/2026", f"Expected '08/2026', got {fab_fields['mfg_date']}"
print("[PASS] Fab: MRP ₹99.00, Net Qty 800 g, USP ₹0.12/g, MFD 08/2026")

# Test 2G: Multi-Line / Split Token & Fallback Cross-Validation
# Case 1: EasyOCR splits "Net Quantity :" and "800g" onto separate lines
fab_split_text = """
*MRP ₹ 99/-
USP ₹ 0.12 / g
Net Quantity :
800g
MFD: 08/2026
"""
split_fields = extract_fields(fab_split_text)
assert split_fields["net_quantity"] == "800 g", f"Expected 800 g for split lines, got {split_fields['net_quantity']}"
print("[PASS] Multi-Line split token 'Net Quantity :\\n800g' extracted as '800 g'")

# Case 2: Standalone weight adjacent to USP line
fab_adjacent_text = """
*MRP ₹ 99/-
USP ₹ 0.12/g
800 g
MFD: 08/2026
"""
adj_fields = extract_fields(fab_adjacent_text)
assert adj_fields["net_quantity"] == "800 g", f"Expected 800 g for adjacent weight, got {adj_fields['net_quantity']}"
print("[PASS] Standalone weight '800 g' adjacent to USP line extracted as '800 g'")

# Case 3: Fallback Cross-Validation Check (round(99 / 0.12) = 825 ~ 800g with faint inkjet dot-matrix token)
fab_cv_text = """
*MRP ₹ 99/-
USP 20.12/g
Net Quanti
8Q
MFD: 08/2026
"""
cv_fields = extract_fields(fab_cv_text)
assert cv_fields["net_quantity"] == "800 g", f"Expected 800 g for fallback cross-validation, got {cv_fields['net_quantity']}"
print("[PASS] Fallback Cross-Validation round(MRP 99 / USP 0.12) = 825g correctly prioritized '800 g'")

# Consolidated multi-sample validation across all three FMCG products:
# 1. Surf Excel
assert surf_fields["mrp"] == 10.0, f"Surf Excel MRP expected 10.0, got {surf_fields['mrp']}"
assert surf_fields["net_quantity"] == "70 g", f"Surf Excel Net Qty expected '70 g', got {surf_fields['net_quantity']}"
print("[PASS] Surf Excel: MRP ₹10.00, Net Qty 70 g")

# 2. Vim
assert vim_fields["mrp"] == "15.00", f"Vim MRP expected 15.00, got {vim_fields['mrp']}"
assert vim_fields["net_quantity"] == "120 ml", f"Vim Net Qty expected '120 ml', got {vim_fields['net_quantity']}"
print("[PASS] Vim: MRP ₹15.00, Net Qty 120 ml")

# 3. Fab
assert fab_fields["mrp"] == "99.00" or fab_fields["mrp"] == 99.0
assert fab_fields["net_quantity"] == "800 g"
print("[PASS] Consolidated validation across Surf Excel, Vim, and Fab fully verified!")

print("\n" + "=" * 60)
print("TEST 2H: Dove Soap Bar & Multi-Panel Composite Extraction")
print("=" * 60)
dove_sample_text = """
DOVE BEAUTY BAR
NET WT. 100 g
₹ 62/- , 0.62 / g
PKD: 17.08.26
USE BEFORE: 12.02.29
Hindustan Unilever Ltd
"""
dove_fields = extract_fields(dove_sample_text)
assert dove_fields["mrp"] == 62.0 or dove_fields["mrp"] == "62.00", f"Expected 62.00, got {dove_fields['mrp']}"
assert dove_fields["net_quantity"] == "100 g", f"Expected 100 g, got {dove_fields['net_quantity']}"
assert dove_fields["usp"] == "0.62 per g", f"Expected '0.62 per g', got {dove_fields['usp']}"
assert dove_fields["mfg_date"] == "17.08.26", f"Expected '17.08.26', got {dove_fields['mfg_date']}"
assert dove_fields["exp_date"] == "12.02.29", f"Expected '12.02.29', got {dove_fields['exp_date']}"
print("[PASS] Dove: MRP ₹62.00, Net Qty 100 g, USP ₹0.62/g, PKD 17.08.26, EXP 12.02.29")

print("\n" + "=" * 60)
print("TEST 2I: OCR Dot-Matrix Slash-Dash MRP & USP Extraction")
print("=" * 60)
dot_matrix_sample = """
Net Quantity : 215 g
$I * /20/-,.70.09/9
"""
dm_fields = extract_fields(dot_matrix_sample)
assert dm_fields["mrp"] == 20.0 or dm_fields["mrp"] == "20.00", f"Expected MRP 20.00, got {dm_fields['mrp']}"
assert dm_fields["net_quantity"] == "215 g", f"Expected Net Qty '215 g', got {dm_fields['net_quantity']}"
assert dm_fields["usp"] == "0.70 per g", f"Expected USP '0.70 per g', got {dm_fields['usp']}"
print(f"[PASS] Dot-Matrix Sample: MRP ₹{dm_fields['mrp']}, Net Qty {dm_fields['net_quantity']}, USP {dm_fields['usp']}")

print("\n" + "=" * 60)
print("TEST 2J: Multi-Line Split OCR Output, Chronological Dates & Case-Insensitive Net Qty")
print("=" * 60)
from services.rule_engine import evaluate
split_ocr_sample = "MRP ?:\nsfdry Ye 4Q\n(Inclusive of all taxes)\nMfg: Date\nASIBZO 12\n03/2026\n02/2029\nExpiry\n10G"
split_res = extract_fields(split_ocr_sample)
split_eval = evaluate(split_res, split_ocr_sample)

assert split_res["mrp"]["value"] == 40.0, f"Expected MRP 40.0, got {split_res['mrp']['value']}"
assert split_res["mrp"]["display"] == "₹ 40.00", f"Expected '₹ 40.00', got {split_res['mrp']['display']}"
assert split_res["mrp_text"]["value"] == "₹ 40.00 (Incl. of all taxes)", f"Expected formatted mrp_text, got {split_res['mrp_text']['value']}"
assert split_res["net_quantity"]["value"] == "10 g", f"Expected Net Qty '10 g', got {split_res['net_quantity']['value']}"
assert split_res["mfg_date"]["value"] == "03/2026", f"Expected Mfg Date '03/2026', got {split_res['mfg_date']['value']}"
assert split_res["exp_date"]["value"] == "02/2029", f"Expected Expiry '02/2029', got {split_res['exp_date']['value']}"

mfg_status = next((r["status"] for r in split_eval if r["field"] == "Manufacturing Date"), None)
qty_status = next((r["status"] for r in split_eval if r["field"] == "Net Quantity"), None)
assert mfg_status == "PASS", f"Expected Manufacturing Date PASS, got {mfg_status}"
assert qty_status == "PASS", f"Expected Net Quantity PASS, got {qty_status}"

# Verify 100g variant
sample_100g = "MRP ?:\nsfdry Ye 4Q\n(Inclusive of all taxes)\nMfg: Date\nASIBZO 12\n03/2026\n02/2029\nExpiry\n100g"
res_100g = extract_fields(sample_100g)
assert res_100g["net_quantity"]["value"] == "100 g", f"Expected Net Qty '100 g', got {res_100g['net_quantity']['value']}"

print("[PASS] Split OCR Sample: MRP ₹40.00, Net Qty 10 g (PASS) & 100 g, Mfg Date 03/2026 (PASS), EXP 02/2029")

print("\n" + "=" * 60)
print("TEST 3: Statutory PDF Notice Generation")
print("=" * 60)
from services.notice_service import generate_enforcement_notice_pdf
pdf_a = generate_enforcement_notice_pdf("CASE_A", product_title="Packaged Biscuit 75g", physical_mrp=38.0, online_price=49.0, delta_rupees=11.0, delta_pct=28.9, domain_or_seller="amazon.in")
assert len(pdf_a) > 2000
print(f"[PASS] Generated Case A Platform Show-Cause Notice PDF ({len(pdf_a)} bytes)")

pdf_b = generate_enforcement_notice_pdf("CASE_B", product_title="Packaged Biscuit 75g", physical_mrp=49.0, online_price=38.0, delta_rupees=11.0, delta_pct=28.9, retailer_name="Metro Retail Mart")
assert len(pdf_b) > 2000
print(f"[PASS] Generated Case B Retailer Compounding Offence Notice PDF ({len(pdf_b)} bytes)")

print("\n" + "=" * 60)
print("TEST 4: URL-Only Audit & Rule 6(10) Compliance (No Mirroring)")
print("=" * 60)
from services.extraction_service import extract_from_listing_and_text

# 4A. Verify extract_from_listing_and_text does NOT copy online mrp or net_quantity
test_listing = {
    "product_title": "Sample Packaged Commodity 500g",
    "mrp": 199.0,
    "net_quantity": "500 g",
    "country_of_origin": "India",
    "usp": "₹ 0.40 / g",
    "domain": "amazon.in",
}
syn_extracted = extract_from_listing_and_text(test_listing, raw_text="No physical sample image uploaded. Showing E-Commerce Listing Audit only.")
assert syn_extracted["mrp"]["found"] is False, f"Expected mrp found=False, got {syn_extracted['mrp']}"
assert syn_extracted["mrp"]["value"] is None, f"Expected mrp value=None, got {syn_extracted['mrp']}"
assert syn_extracted["net_quantity"]["found"] is False, f"Expected net_quantity found=False, got {syn_extracted['net_quantity']}"
assert syn_extracted["net_quantity"]["value"] is None, f"Expected net_quantity value=None, got {syn_extracted['net_quantity']}"
print("[PASS] 4A: Online MRP & Net Quantity are NOT mirrored into physical extracted fields.")

# 4B. Full digital disclosures present on online listing -> Pending Physical Ground Truth Verification
res_url_complete = compare(syn_extracted, test_listing, is_retail_sample=False)
assert res_url_complete["physical_mrp"] is None, f"Expected physical_mrp=None, got {res_url_complete['physical_mrp']}"
assert res_url_complete["physical_quantity"] is None, f"Expected physical_quantity=None, got {res_url_complete['physical_quantity']}"
assert res_url_complete["physical_usp"] is None, f"Expected physical_usp=None, got {res_url_complete['physical_usp']}"
assert res_url_complete["delta_pct"] is None, f"Expected delta_pct=None, got {res_url_complete['delta_pct']}"
assert res_url_complete["delta_rupees"] is None, f"Expected delta_rupees=None, got {res_url_complete['delta_rupees']}"
assert res_url_complete["delta_str"] == "N/A", f"Expected delta_str='N/A', got {res_url_complete['delta_str']}"
assert res_url_complete["status"] in ("Physical Sample Required for Comparison", "E-Commerce Declarations Available (Pending Physical Ground Truth Verification)"), f"Got status: {res_url_complete['status']}"
assert res_url_complete["verdict"] == "E-Commerce Declarations Available (Pending Physical Ground Truth Verification)"
assert "RULE 18 COMPLIANT" not in res_url_complete["verdict"]
print("[PASS] 4B: Full disclosures online evaluate to: E-Commerce Declarations Available (Pending Physical Ground Truth Verification)")
print("       Status:", res_url_complete["status"])
print("       Delta:", res_url_complete["delta_str"])
print("       Physical MRP:", res_url_complete["physical_mrp"])

# 4C. Missing Country of Origin -> Rule 6(10) Violation
listing_no_country = dict(test_listing)
listing_no_country["country_of_origin"] = None
res_missing_country = compare(syn_extracted, listing_no_country, is_retail_sample=False)
assert res_missing_country["status"] == "FAIL"
assert res_missing_country["is_violation"] is True
assert "Rule 6(10) Violation" in res_missing_country["verdict"]
assert "Country of Origin" in res_missing_country["explanation"]
print("\n[PASS] 4C: Missing Country of Origin triggers Rule 6(10) Violation:")
print("       Verdict:", res_missing_country["verdict"])
print("       Explanation:", res_missing_country["explanation"])

# 4D. Missing USP -> Rule 6(10) Violation
listing_no_usp = dict(test_listing)
listing_no_usp["usp"] = None
listing_no_usp["page_text"] = ""
res_missing_usp = compare(syn_extracted, listing_no_usp, is_retail_sample=False)
assert res_missing_usp["status"] == "FAIL"
assert res_missing_usp["is_violation"] is True
assert "Rule 6(10) Violation" in res_missing_usp["verdict"]
assert "USP" in res_missing_usp["explanation"]
print("\n[PASS] 4D: Missing USP triggers Rule 6(10) Violation:")
print("       Verdict:", res_missing_usp["verdict"])
print("       Explanation:", res_missing_usp["explanation"])

print("\n" + "=" * 60)
print("ALL TESTS COMPLETED SUCCESSFULLY!")
print("=" * 60)
