import os

# More stable CPU execution on some Windows setups
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_new_executor"] = "0"

from pathlib import Path
import json
from typing import Optional, Dict, Any

from paddleocr import PaddleOCR

# Lazy singleton (important: prevents uvicorn reload crashes on model download)
_OCR_ENGINE: Optional[PaddleOCR] = None
_OCR_LANG: Optional[str] = None


def get_ocr_engine(lang: str = "en") -> PaddleOCR:
    """
    Lazily create and cache the PaddleOCR engine.
    This avoids downloading/extracting models during import time.
    """
    global _OCR_ENGINE, _OCR_LANG

    if _OCR_ENGINE is None or _OCR_LANG != lang:
        # If you later add Arabic/mixed routing, you can re-init with lang="ar" etc.
        _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
        _OCR_LANG = lang

    return _OCR_ENGINE

def page_average_confidence(page_result: dict) -> float:
    lines = page_result.get("lines", []) or []
    if not lines:
        return 0.0
    vals = [float(l.get("confidence", 0.0) or 0.0) for l in lines]
    return sum(vals) / len(vals)

def choose_better_result(result_a: dict, result_b: dict) -> tuple[str, dict]:
    """
    Compare two OCR page results and return:
      (winner_name, winner_result)
    """
    conf_a = page_average_confidence(result_a)
    conf_b = page_average_confidence(result_b)

    if conf_b > conf_a:
        return "strong", result_b
    return "basic", result_a

def run_ocr_with_retry_for_page(
    page_no: int,
    image_name: str,
    processed_dir: Path,
    confidence_threshold: float = 0.90,
    lang: str = "en",
) -> tuple[dict, dict]:
    """
    OCR a page using:
    1) basic preprocess first
    2) if avg confidence < threshold, retry with strong preprocess

    Returns:
      final_page_result, metadata
    """
    basic_img = processed_dir / "basic" / image_name
    if not basic_img.exists():
        raise FileNotFoundError(f"Missing basic preprocessed image: {basic_img}")

    basic_result = run_ocr_on_image(basic_img, lang=lang)
    basic_conf = page_average_confidence(basic_result)

    meta = {
        "page": page_no,
        "basic_confidence": basic_conf,
        "retry_used": False,
        "selected_mode": "basic",
    }

    if basic_conf >= confidence_threshold:
        return basic_result, meta

    strong_img = processed_dir / "strong" / image_name
    if not strong_img.exists():
        # no retry image available, keep basic
        return basic_result, meta

    strong_result = run_ocr_on_image(strong_img, lang=lang)
    strong_conf = page_average_confidence(strong_result)

    winner_name, winner_result = choose_better_result(basic_result, strong_result)

    meta.update({
        "retry_used": True,
        "strong_confidence": strong_conf,
        "selected_mode": winner_name,
    })

    return winner_result, meta

def run_ocr_on_image(image_path: Path, lang: str = "en") -> dict:
    """
    Run PaddleOCR on a single image and return structured result.
    Output: {"lines": [{"text": str, "confidence": float, "bbox": list}, ...]}
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found for OCR: {image_path}")

    engine = get_ocr_engine(lang=lang)

    # Some PaddleOCR versions accept extra args; keep it minimal
    result = engine.ocr(str(image_path))

    # PaddleOCR returns various nested formats across versions.
    # We normalize it into a list of items: [ [box, (text, conf)], ... ]
    if not result:
        return {"lines": []}

    page = result[0] if isinstance(result, list) else result
    if not page:
        return {"lines": []}

    lines = []
    for item in page:
        
        try:
            box, text_conf = item
            text, conf = text_conf
        except Exception:
            
            continue

        lines.append(
            {
                "text": str(text),
                "confidence": float(conf),
                "bbox": box,  
            }
        )

    return {"lines": lines}

def run_ocr_from_manifest(
    pages_dir: Path,
    processed_dir: Path,
    ocr_dir: Path,
    lang: str = "en",
    confidence_threshold: float = 0.90,
):
    """
    Read manifest.json.
    OCR only pages with source == 'ocr'.

    Uses:
      processed/basic/page_XXXX.png first
      then retries with processed/strong/page_XXXX.png if needed

    Saves chosen per-page OCR JSON into ocr_dir.
    """
    manifest_path = pages_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    ocr_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    for item in manifest:
        page_no = item["page"]

        if item["source"] == "native":
            native_path = pages_dir / item["artifact"]
            text = native_path.read_text(encoding="utf-8")

            results[page_no] = {
                "source": "native",
                "lines": [
                    {"text": line, "confidence": 1.0, "bbox": None}
                    for line in text.splitlines()
                    if line.strip()
                ],
            }

        else:
            image_name = item["artifact"]

            page_result, retry_meta = run_ocr_with_retry_for_page(
                page_no=page_no,
                image_name=image_name,
                processed_dir=processed_dir,
                confidence_threshold=confidence_threshold,
                lang=lang,
            )

            final_payload = {
                "lines": page_result["lines"],
                "retry_meta": retry_meta,
            }

            out_json = ocr_dir / f"page_{page_no:04d}.json"
            out_json.write_text(
                json.dumps(final_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            results[page_no] = {
                "source": "ocr",
                "lines": page_result["lines"],
                "retry_meta": retry_meta,
            }

    return results