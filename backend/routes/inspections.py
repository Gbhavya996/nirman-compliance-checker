"""
inspections.py
──────────────
Blueprint: /api/inspections

POST /api/inspections/analyze
  - Accepts multipart/form-data
  - image : file   (optional when url is provided)
  - url   : str    (optional when image is provided; at least one required)
  - Runs full inspection pipeline; saves to history.

GET /api/inspections/history
  - Returns last 50 inspection summaries.

GET /api/inspections/history/<int:id>
  - Returns full result JSON for one inspection.

DELETE /api/inspections/history
  - Clears entire history.
"""

import base64
import logging
from io import BytesIO

from flask import Blueprint, request, jsonify, send_file

from services.ocr_service import run_ocr
from services.extraction_service import extract_fields, extract_from_listing_and_text
from services.rule_engine import evaluate, summary
from services.readability_service import assess_readability
from services.comparison_service import compare
from services.url_scraper_service import scrape_listing, fetch_image_bytes
from services.cross_verify_service import cross_verify
from services.history_service import save_inspection, list_inspections, get_inspection, delete_all
from services.notice_service import generate_enforcement_notice_pdf

logger = logging.getLogger(__name__)

inspections_bp = Blueprint("inspections", __name__, url_prefix="/api/inspections")

MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB


# ── Analyze ───────────────────────────────────────────────────────────────────

@inspections_bp.route("/analyze", methods=["POST"])
def analyze():
    """
    Full-pipeline analysis endpoint.

    Accepts (multipart/form-data)
    ─────────────────────────────
    mode  : str    – 'image' | 'url' | 'both' (optional, auto-detected if omitted)
    image : file   – product label image (required for 'image' and 'both')
    url   : str    – product listing URL  (required for 'url' and 'both')

    Returns 200 JSON or 400/500 error.
    """
    req_mode = (request.form.get("mode") or "").strip().lower()
    has_image = "image" in request.files and request.files["image"].filename != ""
    product_url = (request.form.get("url") or "").strip()
    has_url = bool(product_url)

    # ── Determine mode ────────────────────────────────────────────────────────
    if req_mode in ("image", "url", "both"):
        mode = req_mode
    elif has_image and has_url:
        mode = "both"
    elif has_image:
        mode = "image"
    elif has_url:
        mode = "url"
    else:
        return jsonify({"error": "Provide at least one of: an image file or a product URL."}), 400

    # Validate mode prerequisites
    if mode == "image" and not has_image:
        return jsonify({"error": "Please provide an image file for Image inspection."}), 400
    if mode == "url" and not has_url:
        return jsonify({"error": "Please provide a valid product URL for URL inspection."}), 400
    if mode == "both" and (not has_image or not has_url):
        return jsonify({"error": "Both an image file and product URL are required for Image + URL mode."}), 400

    image_bytes = None
    image_b64   = None
    image_mime  = None
    ext         = ""

    # Process uploaded image only for 'image' and 'both' modes
    if mode in ("image", "both") and has_image:
        file = request.files["image"]
        allowed_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
        ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in allowed_exts:
            return jsonify({"error": f"Unsupported file type '{ext}'."}), 400

        image_bytes = file.read()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            return jsonify({"error": f"Image too large (max {MAX_IMAGE_BYTES // (1024*1024)} MB)."}), 400

        image_b64  = base64.b64encode(image_bytes).decode("utf-8")
        image_mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png",  ".webp": "image/webp",
            ".bmp": "image/bmp",
        }.get(ext, "image/jpeg")

    is_retail_sample = (
        (request.form.get("is_retail_sample") or "").strip().lower() in ("true", "1", "yes") or
        (request.form.get("sample_type") or "").strip().lower() == "retail_sample"
    )

    try:
        # ─────────────────────────────────────────────────────────────────────
        # 1. URL-ONLY MODE
        # ─────────────────────────────────────────────────────────────────────
        if mode == "url":
            logger.info("Running URL inspection on: %s", product_url)
            listing = scrape_listing(product_url)

            # Check if site blocked automated access (anti-bot, 403, 503, CAPTCHA)
            if listing.get("blocked"):
                logger.warning("Site blocked automated access: %s", product_url)
                return jsonify({
                    "success": False,
                    "error": "This e-commerce site blocked automated access. Please upload a package image directly for compliance screening."
                }), 403

            # Check if scraping failed or was unfetchable
            if not listing.get("scraped"):
                logger.warning("Scraping was unsuccessful for %s: %s", product_url, listing.get("error"))
                return jsonify({
                    "success": False,
                    "error": listing.get("error") or "Unable to fetch product declarations from this URL. Please verify the URL or upload a package image directly."
                }), 400

            # Listing was scraped successfully!
            # If product packaging image is available, download and OCR it
            ocr_result = {
                "raw_text": "",
                "words": [],
                "page_width": 0,
                "page_height": 0,
                "ocr_engine": "none",
                "error": None,
            }
            if listing.get("image_url"):
                img_data = fetch_image_bytes(listing["image_url"])
                if img_data:
                    downloaded_bytes, downloaded_mime = img_data
                    image_b64 = base64.b64encode(downloaded_bytes).decode("utf-8")
                    image_mime = downloaded_mime
                    logger.info("Running OCR on scraped product image (%d bytes)", len(downloaded_bytes))
                    try:
                        ocr_result = run_ocr(BytesIO(downloaded_bytes))
                    except Exception as ocr_err:
                        logger.warning("OCR on downloaded image failed: %s", ocr_err)

            # Synthesize extracted fields from OCR text and scraped listing metadata
            extracted = extract_from_listing_and_text(listing, ocr_result["raw_text"])

            # Evaluate legal metrology compliance rules
            eval_text = (ocr_result["raw_text"] + "\n" + (listing.get("page_text") or "")).strip()
            violations = evaluate(extracted, eval_text)
            rule_summary = summary(violations)

            # Readability
            if ocr_result.get("words"):
                net_qty_val = (extracted.get("net_quantity") or {}).get("value")
                readability = assess_readability(
                    ocr_result["words"],
                    net_qty_str=net_qty_val,
                    page_height_px=ocr_result.get("page_height", 600),
                )
            else:
                readability = {
                    "status": "SKIP",
                    "explanation": "Font height verification skipped: high-resolution package font dimensions unavailable from web listing.",
                }

            # Price comparison with enforcement engine
            comparison = compare(extracted, listing, is_retail_sample=is_retail_sample)

            response_body = {
                "success": True,
                "mode": "url",
                "is_retail_sample": is_retail_sample,
                "ocr": ocr_result,
                "extracted": extracted,
                "violations": violations,
                "summary": rule_summary,
                "readability": readability,
                "comparison": comparison,
                "listing": listing,
                "cross_verification": None,
                "image_b64": image_b64,
                "image_mime": image_mime,
            }

            record_id = save_inspection(
                mode="url",
                result=response_body,
                url=product_url,
                image_b64=image_b64,
                image_mime=image_mime,
            )
            response_body["history_id"] = record_id
            return jsonify(response_body), 200

        # ─────────────────────────────────────────────────────────────────────
        # 2. IMAGE OR BOTH MODE
        # ─────────────────────────────────────────────────────────────────────
        logger.info("Running OCR on uploaded image '%s' (%d bytes)", file.filename, len(image_bytes))
        ocr_result = run_ocr(BytesIO(image_bytes))

        listing = None
        cross = None

        if mode == "both":
            logger.info("Scraping listing URL for cross-verification: %s", product_url)
            listing = scrape_listing(product_url)
            extracted = extract_fields(ocr_result["raw_text"])
            if listing.get("scraped"):
                cross = cross_verify(extracted, listing)
            comparison = compare(extracted, listing, is_retail_sample=is_retail_sample)
        else:
            extracted = extract_fields(ocr_result["raw_text"])
            comparison = compare(extracted, None, is_retail_sample=is_retail_sample)

        violations   = evaluate(extracted, ocr_result["raw_text"])
        rule_summary = summary(violations)

        net_qty_val = (extracted.get("net_quantity") or {}).get("value")
        readability = assess_readability(
            ocr_result["words"],
            net_qty_str=net_qty_val,
            page_height_px=ocr_result.get("page_height", 600),
        )

        response_body = {
            "success": True,
            "mode": mode,
            "is_retail_sample": is_retail_sample,
            "ocr": {
                "raw_text":   ocr_result["raw_text"],
                "words":      ocr_result["words"],
                "page_width":  ocr_result["page_width"],
                "page_height": ocr_result["page_height"],
                "ocr_engine":  ocr_result.get("ocr_engine", "unknown"),
                "error":       ocr_result.get("error"),
            },
            "extracted":         extracted,
            "violations":        violations,
            "summary":           rule_summary,
            "readability":       readability,
            "comparison":        comparison,
            "listing":           listing,
            "cross_verification": cross,
            "image_b64":         image_b64,
            "image_mime":        image_mime,
        }

        record_id = save_inspection(
            mode=mode,
            result=response_body,
            url=product_url or None,
            image_b64=image_b64,
            image_mime=image_mime,
        )
        response_body["history_id"] = record_id
        return jsonify(response_body), 200

    except Exception as exc:
        logger.exception("Pipeline error: %s", exc)
        return jsonify({"error": "Internal server error during analysis.", "detail": str(exc)}), 500


# ── History routes ────────────────────────────────────────────────────────────

@inspections_bp.route("/history", methods=["GET"])
def history_list():
    """Return the 50 most recent inspection summaries."""
    records = list_inspections(limit=50)
    return jsonify({"history": records}), 200


@inspections_bp.route("/history/<int:record_id>", methods=["GET"])
def history_get(record_id: int):
    """Return full result JSON for a single inspection."""
    record = get_inspection(record_id)
    if record is None:
        return jsonify({"error": f"Inspection #{record_id} not found."}), 404
    return jsonify(record), 200


@inspections_bp.route("/history", methods=["DELETE"])
def history_clear():
    """Clear all history records."""
    ok = delete_all()
    if ok:
        return jsonify({"message": "History cleared."}), 200
    return jsonify({"error": "Failed to clear history."}), 500


@inspections_bp.route("/generate-notice", methods=["POST"])
def generate_notice():
    """
    Generate official Legal Metrology Statutory Enforcement Notice PDF.
    Accepts JSON or multipart/form-data.
    """
    data = request.get_json(silent=True) or request.form.to_dict() or {}

    case_type = (data.get("case_type") or "CASE_A").upper()
    product_title = data.get("product_title") or "Packaged Commodity"

    def _to_float(v):
        if v is None:
            return None
        try:
            return float(str(v).replace("₹", "").replace(",", "").strip())
        except (ValueError, TypeError):
            return None

    physical_mrp = _to_float(data.get("physical_mrp"))
    online_price = _to_float(data.get("online_price"))
    delta_rupees = _to_float(data.get("delta_rupees"))
    delta_pct = _to_float(data.get("delta_pct"))

    domain_or_seller = data.get("domain_or_seller") or data.get("domain") or "E-Commerce Platform / Seller"
    retailer_name = data.get("retailer_name") or "Retail Store Premise"
    manufacturer = data.get("manufacturer") or ""
    reference_no = data.get("reference_no")

    try:
        pdf_bytes = generate_enforcement_notice_pdf(
            case_type=case_type,
            product_title=product_title,
            physical_mrp=physical_mrp,
            online_price=online_price,
            delta_rupees=delta_rupees,
            delta_pct=delta_pct,
            domain_or_seller=domain_or_seller,
            retailer_name=retailer_name,
            manufacturer=manufacturer,
            reference_no=reference_no,
        )

        filename = (
            "Platform_Show_Cause_Notice_Section_36.pdf"
            if case_type == "CASE_A"
            else "Retailer_Compound_Offence_Notice_Section_36.pdf"
        )

        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as exc:
        logger.exception("Failed to generate notice PDF: %s", exc)
        return jsonify({"error": "Failed to generate statutory notice PDF", "detail": str(exc)}), 500


@inspections_bp.route("/health", methods=["GET"])
def health():
    """Simple health check."""
    return jsonify({"status": "ok", "service": "nirman-legal-metrology"}), 200
