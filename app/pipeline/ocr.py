import os

# More stable CPU execution on some Windows setups
os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["FLAGS_enable_pir_api"] = "0"
os.environ["FLAGS_use_new_executor"] = "0"

from pathlib import Path
import tarfile
import json
import re
from typing import Optional

from paddleocr import PaddleOCR

from app.pipeline.paddle_cache import remove_corrupt_paddleocr_archives

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
        remove_corrupt_paddleocr_archives()
        try:
            _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
        except tarfile.TarError:
            # A model download can be interrupted after the pre-flight cache scan.
            # PaddleOCR treats the partial .tar as cached, so remove it and retry
            # once to force a clean download.
            removed = remove_corrupt_paddleocr_archives()
            if not removed:
                raise
            _OCR_ENGINE = PaddleOCR(use_angle_cls=True, lang=lang)
        _OCR_LANG = lang

    return _OCR_ENGINE


def page_average_confidence(page_result: dict) -> float:
    lines = page_result.get("lines", []) or []
    if not lines:
        return 0.0

    values = [float(line.get("confidence", 0.0) or 0.0) for line in lines]
    return sum(values) / len(values)


def line_has_suspicious_ocr(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False

    if any(ch in stripped for ch in ("~", "|", "\u00a6", "`")):
        return True

    if re.search(r"\b[Il]\d{2,}\b", stripped):
        return True

    if re.search(r"\b\d{2,}[Il]\b", stripped):
        return True

    if re.search(r"\b[Il]\d{2}[Il]\b", stripped):
        return True

    if re.search(r"[A-Za-z]{3,}[~\-]$", stripped):
        return True

    odd_punctuation = sum(1 for ch in stripped if ch in f"~|\u00a6`")
    return odd_punctuation > 0


def page_suspicious_line_count(page_result: dict) -> int:
    lines = page_result.get("lines", []) or []
    return sum(1 for line in lines if line_has_suspicious_ocr(line.get("text", "")))


def page_quality_score(page_result: dict) -> float:
    lines = page_result.get("lines", []) or []
    if not lines:
        return 0.0

    avg_conf = page_average_confidence(page_result)
    suspicious_lines = page_suspicious_line_count(page_result)
    short_orphan_lines = sum(
        1 for line in lines if len((line.get("text") or "").strip()) <= 3
    )

    return (
        avg_conf
        - (0.015 * suspicious_lines)
        - (0.01 * short_orphan_lines)
    )


def should_retry_page(page_result: dict, confidence_threshold: float) -> bool:
    avg_conf = page_average_confidence(page_result)
    suspicious_lines = page_suspicious_line_count(page_result)

    if avg_conf < confidence_threshold:
        return True

    # High-confidence pages often only contain harmless artifacts such as
    # margin numbers or hyphenated wraps, so don't force a destructive retry.
    if avg_conf < (confidence_threshold + 0.03) and suspicious_lines >= 2:
        return True

    return False


def choose_better_result(result_a: dict, result_b: dict, *, name_a: str = "basic", name_b: str = "strong") -> tuple[str, dict]:
    """
    Compare two OCR page results and return:
      (winner_name, winner_result)
    """
    conf_a = page_average_confidence(result_a)
    conf_b = page_average_confidence(result_b)
    score_a = page_quality_score(result_a)
    score_b = page_quality_score(result_b)

    if conf_b >= conf_a + 0.01:
        return name_b, result_b

    if conf_b >= conf_a - 0.005 and score_b > score_a + 0.02:
        return name_b, result_b

    return name_a, result_a


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
    2) retry with receipt, sorie, and strong preprocess variants when confidence or text heuristics look weak

    Returns:
      final_page_result, metadata
    """
    basic_img = processed_dir / "basic" / image_name
    if not basic_img.exists():
        raise FileNotFoundError(f"Missing basic preprocessed image: {basic_img}")

    basic_result = run_ocr_on_image(basic_img, lang=lang, page_no=page_no)
    basic_conf = page_average_confidence(basic_result)

    meta = {
        "page": page_no,
        "basic_confidence": basic_conf,
        "basic_quality_score": page_quality_score(basic_result),
        "basic_suspicious_lines": page_suspicious_line_count(basic_result),
        "retry_used": False,
        "selected_mode": "basic",
    }

    if not should_retry_page(basic_result, confidence_threshold):
        return basic_result, meta

    winner_name = "basic"
    winner_result = basic_result
    meta["retry_used"] = True

    for mode in ("receipt", "sorie", "strong"):
        retry_img = processed_dir / mode / image_name
        if not retry_img.exists():
            continue

        retry_result = run_ocr_on_image(retry_img, lang=lang, page_no=page_no)
        retry_conf = page_average_confidence(retry_result)
        meta.update(
            {
                f"{mode}_confidence": retry_conf,
                f"{mode}_quality_score": page_quality_score(retry_result),
                f"{mode}_suspicious_lines": page_suspicious_line_count(retry_result),
            }
        )
        winner_name, winner_result = choose_better_result(
            winner_result,
            retry_result,
            name_a=winner_name,
            name_b=mode,
        )

    meta["selected_mode"] = winner_name
    return winner_result, meta


def run_ocr_on_image(image_path: Path, lang: str = "en", page_no: int = 1) -> dict:
    """
    Run PaddleOCR on a single image and return structured result.
    Output: {"lines": [{"text": str, "confidence": float, "bbox": list}, ...]}
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found for OCR: {image_path}")

    engine = get_ocr_engine(lang=lang)
    result = engine.ocr(str(image_path))

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
                "page": page_no,
                "line_id": f"p{page_no:04d}_l{len(lines) + 1:04d}",
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
      then retries with processed/receipt, processed/sorie, and processed/strong variants if needed

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
                    {
                        "text": line,
                        "confidence": 1.0,
                        "bbox": None,
                        "page": page_no,
                        "line_id": f"p{page_no:04d}_l{index:04d}",
                    }
                    for index, line in enumerate(text.splitlines(), start=1)
                    if line.strip()
                ],
            }
            continue

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
