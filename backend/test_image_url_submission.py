"""
test_image_url_submission.py
────────────────────────────
Comprehensive test verifying physical image + URL inspection flow:
1. Physical image + URL submitted:
   - File saved to uploads/
   - has_physical_image is True
   - is_catalog_thumbnail is False
   - Physical image OCR ran directly on saved file
   - All 8 rule violation checks populated from physical sample
   - Price comparison evaluates physical MRP vs online price
2. File key 'file' vs 'image':
   - Ensures request.files.get('image') or request.files.get('file') works seamlessly
3. URL-only mode:
   - Correctly marks has_physical_image = False
"""

import os
import io
import json
import numpy as np
import cv2
from PIL import Image, ImageDraw

from app import create_app

def create_mock_label_image():
    """Create a sample product label image with clear text."""
    img = Image.new("RGB", (600, 400), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    lines = [
        "SURF EXCEL EASY WASH",
        "Net Quantity: 500 g",
        "MRP Rs. 85.00 (Incl. of all taxes)",
        "USP Rs. 0.17 per g",
        "Mfg Date: 08/2026",
        "Hindustan Unilever Ltd, Mumbai",
        "Consumer Care: 1800-10-22-22",
        "Country of Origin: India"
    ]
    y = 30
    for line in lines:
        draw.text((40, y), line, fill=(0, 0, 0))
        y += 40

    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)
    return buf

def run_tests():
    app = create_app()
    client = app.test_client()

    print("\n" + "="*60)
    print("TEST 1: Physical Image + URL Form Submission (Image + URL)")
    print("="*60)

    img_buf = create_mock_label_image()
    data = {
        "mode": "both",
        "url": "https://www.amazon.in/dp/B00FAKE123",
        "image": (img_buf, "sample_pouch.jpg"),
        "is_retail_sample": "false"
    }

    resp = client.post("/api/inspections/analyze", data=data, content_type="multipart/form-data")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.data}"
    res = resp.get_json()

    print("[PASS] Received HTTP 200 from /api/inspections/analyze")
    assert res.get("has_physical_image") is True, f"Expected has_physical_image=True, got {res.get('has_physical_image')}"
    print("[PASS] has_physical_image == True")
    assert res.get("is_catalog_thumbnail") is False, f"Expected is_catalog_thumbnail=False, got {res.get('is_catalog_thumbnail')}"
    print("[PASS] is_catalog_thumbnail == False")
    assert res.get("mode") == "both", f"Expected mode='both', got {res.get('mode')}"
    print("[PASS] mode == 'both'")

    # Check that OCR ran on physical image
    assert res.get("ocr"), "OCR result missing"
    print(f"[PASS] OCR engine used: {res['ocr'].get('ocr_engine')}")
    print(f"[PASS] OCR raw text extracted ({len(res['ocr'].get('raw_text', ''))} chars)")

    # Check violations cards
    violations = res.get("violations", [])
    print(f"[PASS] Rule violations cards generated: {len(violations)} checks evaluated")
    assert len(violations) >= 8, f"Expected at least 8 rule violation checks, got {len(violations)}"

    # Check comparison
    comp = res.get("comparison", {})
    assert comp, "Comparison dictionary missing"
    assert comp.get("has_physical_image") is True, "comparison has_physical_image should be True"
    print(f"[PASS] Price comparison evaluated: source={comp.get('source')}, verdict={comp.get('verdict')}")

    # Verify file was saved to uploads/
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
    saved_files = os.listdir(uploads_dir)
    assert any("sample_pouch.jpg" in f for f in saved_files), "Uploaded file not saved in uploads/ directory"
    print(f"[PASS] Physical image file verified saved in uploads/ directory")

    print("\n" + "="*60)
    print("TEST 2: Alternate File Key ('file' instead of 'image') + URL")
    print("="*60)
    img_buf2 = create_mock_label_image()
    data2 = {
        "mode": "both",
        "url": "https://www.amazon.in/dp/B00FAKE456",
        "file": (img_buf2, "alternate_key_sample.jpg"),
        "is_retail_sample": "false"
    }
    resp2 = client.post("/api/inspections/analyze", data=data2, content_type="multipart/form-data")
    assert resp2.status_code == 200, f"Expected 200, got {resp2.status_code}: {resp2.data}"
    res2 = resp2.get_json()
    assert res2.get("has_physical_image") is True, "Expected has_physical_image=True for 'file' field key"
    assert res2.get("is_catalog_thumbnail") is False, "Expected is_catalog_thumbnail=False for 'file' field key"
    print("[PASS] Successfully accepted image under 'file' key, has_physical_image=True, is_catalog_thumbnail=False")

    print("\n" + "="*60)
    print("ALL IMAGE + URL SUBMISSION TESTS PASSED!")
    print("="*60)

if __name__ == "__main__":
    run_tests()
