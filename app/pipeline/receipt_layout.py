from __future__ import annotations

import json
import re
from pathlib import Path


def bbox_bounds(line: dict) -> tuple[float, float, float, float] | None:
    bbox = line.get("bbox")
    if not bbox:
        return None
    if len(bbox) == 4 and all(isinstance(value, (int, float)) for value in bbox):
        x1, y1, x2, y2 = bbox
        return float(x1), float(y1), float(x2), float(y2)
    xs = [float(point[0]) for point in bbox]
    ys = [float(point[1]) for point in bbox]
    return min(xs), min(ys), max(xs), max(ys)


def normalize_ocr_lines(ocr_dir: Path) -> list[dict]:
    lines: list[dict] = []
    for page_path in sorted(ocr_dir.glob("page_*.json")):
        payload = json.loads(page_path.read_text(encoding="utf-8"))
        page_match = re.search(r"page_(\d+)\.json", page_path.name)
        page_no = int(page_match.group(1)) if page_match else 1
        for index, line in enumerate(payload.get("lines", []) or [], start=1):
            text = (line.get("text_clean") or line.get("text") or "").strip()
            if not text:
                continue
            normalized = dict(line)
            normalized["text"] = text
            normalized["page"] = int(line.get("page") or page_no)
            normalized["line_id"] = line.get("line_id") or f"p{page_no:04d}_l{index:04d}"
            bounds = bbox_bounds(normalized)
            normalized["bounds"] = list(bounds) if bounds else None
            lines.append(normalized)
    return lines


def _section_for_line(text: str, y_ratio: float | None) -> str:
    lowered = text.lower()
    if re.search(r"barcode|qr", lowered):
        return "barcode"
    if re.search(r"cashier|salesperson|doc(?:ument)?\s*no|date|time|gst\s*id", lowered):
        return "document_metadata"
    if re.search(r"code/?desc|\bitem\b.*\bqty\b|\bqty\b.*\bamount\b|s/price", lowered):
        return "items_table"
    if re.search(r"total\s+sales|rounded\s+total|\btotal\b|cash|change|rounding|discount|subtotal", lowered):
        return "totals_payment"
    if re.search(r"tel|fax|@|jalan|taman|johor|address", lowered):
        return "merchant_contact"
    if re.search(r"thank|goods sold|return|exchange", lowered):
        return "footer_notes"
    if y_ratio is not None and y_ratio < 0.22:
        return "header_company"
    if y_ratio is not None and y_ratio > 0.86:
        return "footer_notes"
    return "items_table"


def group_receipt_sections(lines: list[dict]) -> dict:
    max_bottom = max((line.get("bounds") or [0, 0, 0, 0])[3] for line in lines) if lines else 0
    sections: dict[str, list[dict]] = {
        "header_company": [],
        "merchant_contact": [],
        "document_metadata": [],
        "items_table": [],
        "totals_payment": [],
        "footer_notes": [],
        "handwritten_area": [],
        "barcode": [],
    }
    in_items = False
    in_totals = False
    for line in lines:
        text = line.get("text", "")
        bounds = line.get("bounds")
        y_ratio = (bounds[1] / max_bottom) if bounds and max_bottom else None
        section = _section_for_line(text, y_ratio)
        if section == "items_table":
            in_items = True
        if section == "totals_payment":
            in_totals = True
            in_items = False
        if in_items and section == "header_company":
            section = "items_table"
        if in_totals and section == "items_table" and not re.match(r"^\d{3,}\b", text):
            section = "footer_notes"
        sections[section].append(line)
    return {name: {"lines": value} for name, value in sections.items()}


def build_receipt_layout(ocr_dir: Path, layout_dir: Path) -> dict:
    lines = normalize_ocr_lines(ocr_dir)
    sections = group_receipt_sections(lines)
    payload = {"lines": lines, "sections": sections}
    layout_dir.mkdir(parents=True, exist_ok=True)
    (layout_dir / "sections.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
