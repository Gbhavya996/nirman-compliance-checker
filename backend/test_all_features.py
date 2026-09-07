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
assert res_surf["online_usp"] == "₹ 0.156 / g", f"Expected '₹ 0.156 / g', got {res_surf['online_usp']}"
assert res_surf["delta_str"] == "+₹0.013 / g", f"Expected '+₹0.013 / g', got {res_surf['delta_str']}"
assert res_surf["is_variant_mismatch"] is False, "Expected is_variant_mismatch to be False"
assert "RULE 6(11) COMPLIANT: Unit Sale Price normalized per gram for SKU variation." in res_surf["verdict"]
print("[PASS] Physical MRP: ₹ 10.00")
print("[PASS] Online Price: ₹ 312.00")
print("[PASS] Physical USP: ₹ 0.14 / g")
print("[PASS] Online USP: ₹ 0.156 / g")
print("[PASS] Normalized Delta: +₹0.013 / g")
print("[PASS] Regulatory Finding:", res_surf["verdict"])
print("[PASS] Status:", res_surf["status"])

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
print("ALL TESTS COMPLETED SUCCESSFULLY!")
print("=" * 60)
