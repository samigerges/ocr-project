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
) -> Dict[int, Dict[str, Any]]:
    """
    Read pages_dir/manifest.json
    - If source == 'native': load page_XXXX.native.txt
    - If source == 'ocr': run OCR on processed_dir/page_XXXX.png
    Save OCR JSON per page into ocr_dir/page_XXXX.json

    Returns: dict keyed by page_no
    """
    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest.json: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ocr_dir.mkdir(parents=True, exist_ok=True)

    results: Dict[int, Dict[str, Any]] = {}

    for item in manifest:
        page_no = int(item["page"])
        source = item.get("source")
        artifact = item.get("artifact")

        if source == "native":
            native_path = pages_dir / artifact
            if not native_path.exists():
                raise FileNotFoundError(f"Native text file missing: {native_path}")

            text = native_path.read_text(encoding="utf-8", errors="replace")

            results[page_no] = {
                "source": "native",
                "lines": [
                    {"text": line, "confidence": 1.0, "bbox": None}
                    for line in text.splitlines()
                    if line.strip()
                ],
            }

        elif source == "ocr":
            img_path = processed_dir / artifact
            page_result = run_ocr_on_image(img_path, lang=lang)

            out_json = ocr_dir / f"page_{page_no:04d}.json"
            out_json.write_text(
                json.dumps(page_result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            results[page_no] = {
                "source": "ocr",
                "lines": page_result["lines"],
            }

        else:
            raise ValueError(f"Unknown source in manifest for page {page_no}: {source}")

    return results