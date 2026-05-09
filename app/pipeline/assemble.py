from __future__ import annotations

from pathlib import Path
import json


def _line_text(line: dict) -> str:
    return (line.get("text_clean") or line.get("text") or "").strip()


def _bbox_bounds(line: dict) -> tuple[float, float, float, float] | None:
    bbox = line.get("bbox")
    if not bbox:
        return None

    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def assemble_page_text(lines: list[dict]) -> str:
    paragraphs: list[str] = []
    current_parts: list[str] = []
    prev_bounds: tuple[float, float, float, float] | None = None

    for line in lines:
        text = _line_text(line)
        if not text:
            continue

        bounds = _bbox_bounds(line)

        if not current_parts:
            current_parts.append(text)
            prev_bounds = bounds
            continue

        new_paragraph = False
        if bounds and prev_bounds:
            prev_left, prev_top, _, prev_bottom = prev_bounds
            curr_left, curr_top, _, curr_bottom = bounds

            prev_height = max(prev_bottom - prev_top, 1.0)
            curr_height = max(curr_bottom - curr_top, 1.0)
            line_gap = curr_top - prev_bottom
            indent_shift = curr_left - prev_left

            new_paragraph = (
                line_gap > max(prev_height, curr_height) * 1.8
                or indent_shift > max(28.0, prev_height * 1.5)
            )

        if new_paragraph:
            paragraphs.append(" ".join(current_parts).strip())
            current_parts = [text]
        else:
            current_parts.append(text)

        prev_bounds = bounds or prev_bounds

    if current_parts:
        paragraphs.append(" ".join(current_parts).strip())

    return "\n\n".join(paragraphs).strip()


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
                    {"text": line, "confidence": 1.0, "bbox": None}
                    for line in text.splitlines()
                    if line.strip()
                ],
            }

            pages_out.append(page_obj)
            if text.strip():
                full_text_parts.append(text.strip())
            continue

        page_json = ocr_dir / f"page_{page_no:04d}.json"

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
        page_text = assemble_page_text(lines)

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
    return result
