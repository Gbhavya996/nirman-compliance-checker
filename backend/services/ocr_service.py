"""
ocr_service.py
──────────────
Preprocesses product-label images and runs OCR.

OCR engine priority
-------------------
1. Tesseract (pytesseract) – preferred if installed on the system PATH.
2. EasyOCR             – used automatically when Tesseract is unavailable.
3. Empty result        – returned if both engines fail; NEVER fake/mock data.

Returns
-------
{
    "raw_text": str,
    "words": [{"text": str, "x": int, "y": int, "w": int, "h": int, "conf": float}],
    "page_width": int,
    "page_height": int,
    "ocr_engine": str,   # "tesseract" | "easyocr" | "none"
    "error": str | None,
}
"""

import io
import logging

# pyrefly: ignore [missing-import]
import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tesseract availability check (done once at import time)
# ---------------------------------------------------------------------------

_TESSERACT_OK = False
try:
    import pytesseract

    # Common Windows installation paths
    import os, sys
    _TESS_WINDOWS_PATHS = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]
    for _p in _TESS_WINDOWS_PATHS:
        if os.path.isfile(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            logger.info("Tesseract found at: %s", _p)
            break

    pytesseract.get_tesseract_version()   # raises if not found
    _TESSERACT_OK = True
    logger.info("Tesseract OCR is available.")
except Exception as _e:
    logger.warning("Tesseract not available (%s). Will use EasyOCR.", _e)

# ---------------------------------------------------------------------------
# EasyOCR – lazy-loaded so startup is not blocked when unused
# ---------------------------------------------------------------------------

_easyocr_reader = None


def _get_easyocr():
    global _easyocr_reader
    if _easyocr_reader is None:
        try:
            import easyocr  # noqa: PLC0415
            logger.info("Loading EasyOCR model (English) – first run may take a moment…")
            _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            logger.info("EasyOCR ready.")
        except ImportError:
            logger.error(
                "EasyOCR is not installed. "
                "Run: pip install easyocr"
            )
        except Exception as exc:
            logger.error("EasyOCR failed to initialise: %s", exc, exc_info=True)
    return _easyocr_reader


# ---------------------------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------------------------

def _to_numpy(image_input) -> np.ndarray:
    """Accept file path, bytes, file-like object, or PIL Image → BGR ndarray."""
    if isinstance(image_input, np.ndarray):
        return image_input
    if isinstance(image_input, Image.Image):
        return cv2.cvtColor(np.array(image_input), cv2.COLOR_RGB2BGR)
    if isinstance(image_input, (bytes, bytearray)):
        arr = np.frombuffer(image_input, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if hasattr(image_input, "read"):
        data = image_input.read()
        arr = np.frombuffer(data, np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
    # assume file path
    return cv2.imread(str(image_input))


def preprocess(image_input) -> np.ndarray:
    """
    Preprocessing pipeline tuned for printed product labels:
    1. Convert to grayscale
    2. Upscale small images (OCR accuracy degrades below ~300 DPI)
    3. CLAHE contrast enhancement
    4. Adaptive thresholding (handles uneven lighting / shadows)
    5. Mild morphological cleanup
    """
    img = _to_numpy(image_input)
    if img is None:
        raise ValueError("Could not decode image – unsupported format or corrupt data.")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Upscale if too small
    h, w = gray.shape
    if max(h, w) < 1200:
        scale = 1200 / max(h, w)
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )

    # Denoise
    kernel = np.ones((1, 1), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    return binary


# ---------------------------------------------------------------------------
# OCR engines
# ---------------------------------------------------------------------------

_TESS_CONFIG = (
    r"--oem 3 --psm 6 "
    r"-c tessedit_char_whitelist="
    r"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,/:@₹%()-+\\ "
)


def _run_tesseract(processed: np.ndarray, lang: str) -> dict:
    """Run Tesseract on a pre-processed binary image."""
    pil_img = Image.fromarray(processed)

    raw_text: str = pytesseract.image_to_string(pil_img, lang=lang, config=_TESS_CONFIG)

    data = pytesseract.image_to_data(
        pil_img, lang=lang, config=_TESS_CONFIG,
        output_type=pytesseract.Output.DICT,
    )

    words = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue
        conf = float(data["conf"][i])
        if conf < 0:
            continue
        words.append({
            "text": text,
            "x": int(data["left"][i]),
            "y": int(data["top"][i]),
            "w": int(data["width"][i]),
            "h": int(data["height"][i]),
            "conf": round(conf, 2),
        })

    page_height, page_width = processed.shape[:2]
    return {
        "raw_text": raw_text,
        "words": words,
        "page_width": page_width,
        "page_height": page_height,
        "ocr_engine": "tesseract",
        "error": None,
    }


def _run_easyocr(image_input) -> dict:
    """Run EasyOCR on the original (colour) image for best accuracy."""
    reader = _get_easyocr()
    if reader is None:
        raise RuntimeError("EasyOCR reader could not be initialised.")

    img_bgr = _to_numpy(image_input)
    if img_bgr is None:
        raise ValueError("Could not decode image for EasyOCR.")

    # EasyOCR accepts BGR ndarray directly
    results = reader.readtext(img_bgr, detail=1, paragraph=False)

    words = []
    lines_text = []
    for (bbox, text, conf) in results:
        text = text.strip()
        if not text:
            continue
        # bbox = [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        xs = [pt[0] for pt in bbox]
        ys = [pt[1] for pt in bbox]
        x, y = int(min(xs)), int(min(ys))
        w, h = int(max(xs) - min(xs)), int(max(ys) - min(ys))
        words.append({
            "text": text,
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "conf": round(float(conf) * 100, 2),
        })
        lines_text.append(text)

    raw_text = "\n".join(lines_text) + ("\n" if lines_text else "")
    h_img, w_img = img_bgr.shape[:2]

    return {
        "raw_text": raw_text,
        "words": words,
        "page_width": w_img,
        "page_height": h_img,
        "ocr_engine": "easyocr",
        "error": None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_ocr(image_input, lang: str = "eng") -> dict:
    """
    Run OCR on *image_input* and return structured results.

    Tries Tesseract first; falls back to EasyOCR if Tesseract is not
    installed. Never returns fake / hardcoded data.

    Parameters
    ----------
    image_input : path / bytes / file-like / PIL.Image / ndarray
    lang        : Tesseract language code (ignored by EasyOCR)

    Returns
    -------
    dict with keys: raw_text, words, page_width, page_height, ocr_engine, error
    """
    # ── 1. Try Tesseract ──────────────────────────────────────────────────────
    if _TESSERACT_OK:
        try:
            processed = preprocess(image_input)
            return _run_tesseract(processed, lang)
        except Exception as exc:
            logger.warning("Tesseract failed: %s. Falling back to EasyOCR.", exc)

    # ── 2. Try EasyOCR ────────────────────────────────────────────────────────
    try:
        # Re-read image_input bytes if it was a file-like (may have been consumed)
        if hasattr(image_input, "seek"):
            image_input.seek(0)
        return _run_easyocr(image_input)
    except Exception as exc:
        logger.error("EasyOCR failed: %s", exc, exc_info=True)

    # ── 3. Both engines failed – return empty result, never mock data ─────────
    logger.error("All OCR engines failed. Returning empty result.")
    return {
        "raw_text": "",
        "words": [],
        "page_width": 0,
        "page_height": 0,
        "ocr_engine": "none",
        "error": (
            "OCR could not extract any text from this image. "
            "Please ensure the image is clear and well-lit, "
            "or install Tesseract for best results."
        ),
    }
