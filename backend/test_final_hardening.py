"""
backend/test_final_hardening.py
-------------------------------
Comprehensive verification script for final master hardening:
1. Rule 6(11) Mathematical Integrity Check (USP vs MRP/Qty)
2. E-Commerce & Missing Physical Sample Handling (Rule 6(10) No Mirroring)
3. Section 36 PDF Notice Generation with full citations and compounding fine bracket
4. Inspection API endpoints (/generate-notice, /history)
"""

import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app import create_app
app = create_app()
from services.rule_engine import evaluate
from services.comparison_service import compare
from services.notice_service import generate_enforcement_notice_pdf

def test_rule_6_11_mathematical_integrity():
    print("\n--- Testing Rule 6(11) Mathematical Integrity Check ---")
    
    # Matching USP: MRP 100, Net Qty 500g -> Computed USP = 0.20/g. Declared = "0.20 per g"
    fields_match = {
        "mrp": {"found": True, "value": 100.0},
        "net_quantity": {"found": True, "value": "500 g"},
        "usp": {"found": True, "value": "₹ 0.20 per g"},
        "mfg_date": {"found": True, "value": "01/2026"},
        "exp_date": {"found": False, "value": None},
        "consumer_care": {"found": True, "value": "care@example.com"},
        "manufacturer": {"found": True, "value": "Test FMCG Ltd"},
        "country_of_origin": {"found": True, "value": "India"},
        "fssai_licence": {"found": False, "value": None},
    }
    report_match = evaluate(fields_match, "MRP Rs 100 Net Qty 500g USP Rs 0.20 per g")
    usp_results = [r for r in report_match if r["field"] == "Unit Sale Price (USP)"]
    assert len(usp_results) == 1, f"Expected 1 USP result, got {len(usp_results)}"
    assert usp_results[0]["status"] == "PASS", f"Expected PASS, got {usp_results[0]}"
    print("[PASS] Matched USP correctly evaluated to PASS:", usp_results[0]["explanation"])

    # Mismatched USP: MRP 100, Net Qty 500g -> Computed USP = 0.20/g. Declared = "0.35 per g" (> 5% discrepancy)
    fields_mismatch = {
        "mrp": {"found": True, "value": 100.0},
        "net_quantity": {"found": True, "value": "500 g"},
        "usp": {"found": True, "value": "₹ 0.35 per g"},
        "mfg_date": {"found": True, "value": "01/2026"},
        "exp_date": {"found": False, "value": None},
        "consumer_care": {"found": True, "value": "care@example.com"},
        "manufacturer": {"found": True, "value": "Test FMCG Ltd"},
        "country_of_origin": {"found": True, "value": "India"},
        "fssai_licence": {"found": False, "value": None},
    }
    report_mismatch = evaluate(fields_mismatch, "MRP Rs 100 Net Qty 500g USP Rs 0.35 per g")
    usp_mismatch = [r for r in report_mismatch if r["field"] == "Unit Sale Price (USP)"][0]
    assert usp_mismatch["status"] == "WARNING", f"Expected WARNING, got {usp_mismatch}"
    assert "Rule 6(11) Mismatch: Declared USP does not match computed unit rate." in usp_mismatch["explanation"]
    print("[PASS] Mismatched USP correctly triggered Rule 6(11) WARNING:", usp_mismatch["explanation"])

def test_missing_physical_sample_handling():
    print("\n--- Testing Missing Physical Sample Handling ---")
    extracted_none = {
        "mrp": {"found": False, "value": None},
        "net_quantity": {"found": False, "value": None},
        "usp": {"found": False, "value": None},
    }
    listing = {
        "product_title": "Premium Coffee 200g",
        "mrp": 350.0,
        "net_quantity": "200 g",
        "country_of_origin": "India",
        "usp": "₹ 1.75 / g",
        "domain": "blinkit.com",
    }
    comp = compare(extracted_none, listing, is_retail_sample=False)
    assert comp["physical_mrp"] is None
    assert comp["physical_quantity"] is None
    assert comp["physical_usp"] is None
    assert comp["status"] in ("Physical Sample Required for Comparison", "E-Commerce Declarations Available (Pending Physical Ground Truth Verification)")
    assert comp["is_violation"] is False
    print("[PASS] Scraped online data is NOT mirrored into physical fields when sample is missing.")
    print("       Status:", comp["status"])

def test_statutory_notice_generation():
    print("\n--- Testing Section 36 Legal Notice Generation ---")
    pdf_bytes = generate_enforcement_notice_pdf(
        case_type="CASE_A",
        product_title="Super Dishwash Gel 500ml",
        physical_mrp=99.0,
        online_price=125.0,
        delta_rupees=26.0,
        delta_pct=26.26,
        domain_or_seller="BigRetail Platform",
        manufacturer="FMCG Industries India",
        reference_no="LM-ENF/2026/0908001",
        breaches=[
            "Rule 18(2) LM-PC Rules (Sale above declared Maximum Retail Price)",
            "Rule 6(10) LM-PC Rules (E-Commerce Mandatory Digital Declarations)",
            "Section 36(1) LM Act, 2009 (Penalty for Statutory Non-Compliance)",
        ]
    )
    assert len(pdf_bytes) > 2000
    assert pdf_bytes.startswith(b"%PDF")
    print(f"[PASS] Successfully generated Case A Section 36 Notice PDF ({len(pdf_bytes)} bytes)")

    # Test via Flask test client
    with app.test_client() as client:
        resp = client.post(
            "/api/inspections/generate-notice",
            json={
                "case_type": "CASE_A",
                "product_title": "Super Dishwash Gel 500ml",
                "physical_mrp": 99.0,
                "online_price": 125.0,
                "delta_rupees": 26.0,
                "delta_pct": 26.26,
                "domain_or_seller": "BigRetail Platform",
            }
        )
        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/pdf"
        print("[PASS] Flask /api/inspections/generate-notice returned HTTP 200 with PDF payload.")

        # Test history endpoint
        hist_resp = client.get("/api/inspections/history")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.get_json()
        assert "history" in hist_data
        print(f"[PASS] Flask /api/inspections/history returned HTTP 200 ({len(hist_data['history'])} records).")

if __name__ == "__main__":
    test_rule_6_11_mathematical_integrity()
    test_missing_physical_sample_handling()
    test_statutory_notice_generation()
    print("\n============================================================")
    print("ALL FINAL HARDENING VERIFICATION CHECKS PASSED!")
    print("============================================================")
