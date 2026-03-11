from __future__ import annotations

from pathlib import Path
import json


def assemble_results(
    doc_id: str,
    pages_dir: Path,
    ocr_dir: Path,
    out_dir: Path,
) -> dict:
    """
    Assemble final outputs from:
      - pages_dir/manifest.json
      - native text artifacts in pages_dir (for source == "native")
      - OCR artifacts in:
          storage/<doc_id>/postprocessed/page_XXXX.json (preferred)
          fallback to ocr_dir/page_XXXX.json
    Writes:
      - out_dir/result.json
      - out_dir/result.txt
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pages_out = []
    full_text_parts: list[str] = []

    # Preferred postprocessed dir (sibling of ocr_dir, created by postprocess step)
    postprocessed_dir = ocr_dir.parent / "postprocessed"

    for item in manifest:
        page_no = int(item["page"])
        source = item["source"]

        if source == "native":
            native_path = pages_dir / item["artifact"]
            text = native_path.read_text(encoding="utf-8") if native_path.exists() else ""

            page_obj = {
                "page": page_no,
                "source": "native",
                "text": text,
                "lines": [{"text": ln, "confidence": 1.0, "bbox": None}
                          for ln in text.splitlines() if ln.strip()],
            }
            pages_out.append(page_obj)
            if text.strip():
                full_text_parts.append(text.strip())
            continue

        # OCR page JSON: prefer postprocessed, fallback to raw ocr
        candidate = postprocessed_dir / f"page_{page_no:04d}.json"
        ocr_json = candidate if candidate.exists() else (ocr_dir / f"page_{page_no:04d}.json")

        if not ocr_json.exists():
            page_obj = {"page": page_no, "source": "ocr", "text": "", "lines": []}
            pages_out.append(page_obj)
            continue

        page_result = json.loads(ocr_json.read_text(encoding="utf-8"))
        lines = page_result.get("lines", []) or []

        # Build text from cleaned text if available, otherwise raw text
        page_text = "\n".join([
            ((l.get("text_clean") or l.get("text") or "")).strip()
            for l in lines
            if ((l.get("text_clean") or l.get("text") or "")).strip()
        ]).strip()

        # Store per-page lines; keep compatibility whether postprocessed or raw
        pages_out.append({
            "page": page_no,
            "source": "ocr",
            "text": page_text,
            "lines": lines,
            # Optional extra metadata if postprocessed file contains it
            "corrections": page_result.get("corrections", []),
        })

        if page_text:
            full_text_parts.append(page_text)

    result = {
        "doc_id": doc_id,
        "pages": pages_out,
        "full_text": "\n\n".join(full_text_parts).strip(),
    }

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    (out_dir / "result.txt").write_text(result["full_text"], encoding="utf-8")

    return result