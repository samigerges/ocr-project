from __future__ import annotations

from pathlib import Path
import json


def assemble_results(
    doc_id: str,
    pages_dir: Path,
    ocr_dir: Path,
    out_dir: Path,
) -> dict:

    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pages_out = []
    full_text_parts: list[str] = []

    base = ocr_dir.parent

    llm_dir = base / "llm"
    postprocessed_dir = base / "postprocessed"

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
                "lines": [
                    {"text": ln, "confidence": 1.0, "bbox": None}
                    for ln in text.splitlines()
                    if ln.strip()
                ],
            }

            pages_out.append(page_obj)

            if text.strip():
                full_text_parts.append(text.strip())

            continue

        # -------- PRIORITY: LLM → postprocessed → OCR --------

        llm_json = llm_dir / f"page_{page_no:04d}.json"
        post_json = postprocessed_dir / f"page_{page_no:04d}.json"
        raw_json = ocr_dir / f"page_{page_no:04d}.json"

        if llm_json.exists():
            page_json = llm_json
        elif post_json.exists():
            page_json = post_json
        else:
            page_json = raw_json

        if not page_json.exists():

            page_obj = {
                "page": page_no,
                "source": "ocr",
                "text": "",
                "lines": [],
            }

            pages_out.append(page_obj)
            continue

        page_result = json.loads(page_json.read_text(encoding="utf-8"))

        lines = page_result.get("lines", []) or []

        page_text = "\n".join(
            [
                l.get("text_after_llm")
                or l.get("text_clean")
                or l.get("text")
                or ""
                for l in lines
            ]
        ).strip()

        pages_out.append(
            {
                "page": page_no,
                "source": "ocr",
                "text": page_text,
                "lines": lines,
                "corrections": page_result.get("corrections", []),
            }
        )

        if page_text:
            full_text_parts.append(page_text)

    result = {
        "doc_id": doc_id,
        "pages": pages_out,
        "full_text": "\n\n".join(full_text_parts).strip(),
    }

    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    (out_dir / "result.txt").write_text(
        result["full_text"],
        encoding="utf-8",
    )

    return result