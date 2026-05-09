from __future__ import annotations

import json
from pathlib import Path
from statistics import mean

import cv2
import numpy as np


BLUR_WARNING_THRESHOLD = 80.0
BRIGHTNESS_DARK_THRESHOLD = 70.0
BRIGHTNESS_LIGHT_THRESHOLD = 235.0
MIN_TEXT_DENSITY = 0.01
MAX_TEXT_DENSITY = 0.55


def _safe_float(value: float) -> float:
    if np.isnan(value) or np.isinf(value):
        return 0.0
    return round(float(value), 4)


def estimate_skew_angle(gray: np.ndarray) -> float:
    """Estimate document skew angle from foreground pixels in a grayscale image."""
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return 0.0

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle
    if abs(angle) > 45:
        return 0.0
    return _safe_float(angle)


def estimate_text_density(gray: np.ndarray) -> float:
    """Approximate foreground/text density after Otsu thresholding."""
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    foreground = cv2.countNonZero(thresh)
    total = gray.shape[0] * gray.shape[1]
    return _safe_float(foreground / float(total or 1))


def detect_orientation(width: int, height: int) -> str:
    if width == height:
        return "square"
    return "landscape" if width > height else "portrait"


def assess_image_quality(image_path: Path) -> dict:
    """Calculate OCR quality hints for one rendered page or uploaded image."""
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image for quality assessment: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    blur_score = _safe_float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = _safe_float(float(np.mean(gray)))
    skew_angle = estimate_skew_angle(gray)
    text_density = estimate_text_density(gray)

    warnings: list[str] = []
    if blur_score < BLUR_WARNING_THRESHOLD:
        warnings.append("image_is_blurry")
    if brightness < BRIGHTNESS_DARK_THRESHOLD:
        warnings.append("image_is_dark")
    if brightness > BRIGHTNESS_LIGHT_THRESHOLD:
        warnings.append("image_is_too_light")
    if text_density < MIN_TEXT_DENSITY:
        warnings.append("low_text_density")
    if text_density > MAX_TEXT_DENSITY:
        warnings.append("high_foreground_density")
    if abs(skew_angle) > 3.0:
        warnings.append("receipt_may_be_skewed")

    return {
        "image": image_path.name,
        "width": int(width),
        "height": int(height),
        "orientation": detect_orientation(width, height),
        "blur_score": blur_score,
        "brightness": brightness,
        "skew_angle": skew_angle,
        "text_density": text_density,
        "warnings": warnings,
        "status": "low_quality" if warnings else "ok",
        "message": "Image quality may reduce extraction confidence." if warnings else "Image quality looks suitable for OCR.",
    }


def assess_pages_from_manifest(pages_dir: Path, quality_dir: Path) -> dict:
    """Assess OCR-rendered image pages and persist storage/<doc_id>/quality/report.json."""
    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages: list[dict] = []
    for item in manifest:
        if item.get("source") != "ocr":
            continue
        page_path = pages_dir / item["artifact"]
        if page_path.exists():
            page_report = assess_image_quality(page_path)
            page_report["page"] = int(item["page"])
            pages.append(page_report)

    all_warnings = sorted({warning for page in pages for warning in page["warnings"]})
    report = {
        "status": "low_quality" if all_warnings else "ok",
        "message": "One or more pages may produce low-confidence OCR." if all_warnings else "All assessed pages look suitable for OCR.",
        "page_count": len(pages),
        "average_blur_score": _safe_float(mean([p["blur_score"] for p in pages])) if pages else 0.0,
        "average_brightness": _safe_float(mean([p["brightness"] for p in pages])) if pages else 0.0,
        "warnings": all_warnings,
        "pages": pages,
    }
    quality_dir.mkdir(parents=True, exist_ok=True)
    (quality_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
