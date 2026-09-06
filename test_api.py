"""
test_api.py
-----------
Quick end-to-end test for the Nirman compliance API.
Sends backend/uploads/sample_label.jpg to POST /api/inspections/analyze
and prints a formatted summary of the response.

Usage:
    python test_api.py
"""

import json
import os
import sys
import urllib.request

# Force UTF-8 output on Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_URL = "http://localhost:5000/api/inspections/analyze"
SAMPLE_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "uploads", "sample_label.jpg")

def hr(title=""):
    line = "=" * 60
    if title:
        print(f"\n  {title}")
        print("  " + "-" * 56)
    else:
        print(line)

def main():
    if not os.path.exists(SAMPLE_IMAGE):
        print(f"[ERROR] Sample image not found at: {SAMPLE_IMAGE}")
        sys.exit(1)

    print("=" * 60)
    print("  NIRMAN - Legal Metrology Compliance API - E2E Test")
    print("=" * 60)
    print(f"  Endpoint : {API_URL}")
    print(f"  Image    : {SAMPLE_IMAGE}")
    print()

    boundary = "----NirmanTestBoundary7a3b9c"
    with open(SAMPLE_IMAGE, "rb") as f:
        img_data = f.read()

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="sample_label.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    print("  Sending request... ", end="", flush=True)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.URLError as e:
        print(f"\n[NETWORK ERROR] {e}")
        print("  -> Make sure the Flask backend is running on port 5000.")
        sys.exit(1)

    print(f"HTTP {status} OK")
    data = json.loads(raw)

    # -- Summary ---
    hr("COMPLIANCE SUMMARY")
    s = data.get("summary", {})
    overall = s.get("overall", "UNKNOWN")
    icon = {"COMPLIANT": "[PASS]", "NON_COMPLIANT": "[FAIL]", "NEEDS_REVIEW": "[WARN]"}.get(overall, "[?]")
    print(f"  Overall : {icon} {overall}")
    print(f"  Checks  : {s.get('total_checks', '?')} total  |  "
          f"PASS: {s.get('pass_count', 0)}  |  "
          f"FAIL: {s.get('fail_count', 0)}  |  "
          f"WARN: {s.get('warning_count', 0)}")

    # -- Extracted fields ---
    hr("EXTRACTED DECLARATIONS")
    extracted = data.get("extracted", {})
    for field, info in extracted.items():
        status_sym = "[OK]" if info.get("found") else "[--]"
        value = info.get("value", "-")
        print(f"  {status_sym}  {field:<25} {value}")

    # -- Readability ---
    hr("READABILITY RISK")
    rd = data.get("readability", {})
    rd_status = rd.get("status", "UNKNOWN")
    rd_icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARNING": "[WARN]", "SKIP": "[SKIP]"}.get(rd_status, "[?]")
    print(f"  {rd_icon} Status          : {rd_status}")
    print(f"    Min required  : {rd.get('min_required_mm', '-')} mm")
    print(f"    Est. min font : {rd.get('estimated_min_mm', '-')} mm")
    if rd.get("explanation"):
        print(f"    Note          : {rd['explanation']}")

    # -- Rule violations ---
    violations = data.get("violations", [])
    hr(f"RULE VIOLATIONS ({len(violations)} checks)")
    for v in violations:
        icon_map = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARNING": "[WARN]", "SKIP": "[SKIP]"}
        vi = icon_map.get(v.get("status", "SKIP"), "[?]")
        print(f"  {vi}  {v.get('field','?'):<25}  {v.get('rule_ref','')}")
        if v.get("explanation") and v.get("status") in ("FAIL", "WARNING"):
            print(f"           -> {v['explanation']}")

    # -- Price comparison ---
    hr("PRICE COMPARISON")
    cmp = data.get("comparison", {})
    cmp_icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "WARNING": "[WARN]", "SKIP": "[SKIP]"}.get(
        cmp.get("status", "SKIP"), "[?]"
    )
    print(f"  {cmp_icon} Status          : {cmp.get('status', '-')}")
    print(f"    Physical MRP  : {cmp.get('physical_mrp', '-')}")
    print(f"    Online price  : {cmp.get('online_price', '-')}")
    print(f"    Delta         : {cmp.get('delta_pct', '-')} %")
    if cmp.get("explanation"):
        print(f"    Note          : {cmp['explanation']}")

    print()
    print("=" * 60)
    print("  END-TO-END TEST COMPLETE. Full JSON saved to test_output.json")
    print("=" * 60)
    with open("test_output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    main()
