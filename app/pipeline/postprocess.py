from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Dict, List, Any


# -------------------------------------------------
# Character normalization
# -------------------------------------------------

CHAR_REPLACEMENTS = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "—": "-",
    "–": "-",
}


def normalize_text(text: str) -> str:
    for k, v in CHAR_REPLACEMENTS.items():
        text = text.replace(k, v)

    text = re.sub(r"\s+", " ", text)
    return text.strip()


# -------------------------------------------------
# Layout sorting
# -------------------------------------------------

def sort_lines_by_layout(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort lines using bounding box coordinates.
    """
    def key_fn(line):
        bbox = line.get("bbox")
        if not bbox:
            return (0, 0)

        x = bbox[0][0]
        y = bbox[0][1]

        return (y, x)

    return sorted(lines, key=key_fn)


# -------------------------------------------------
# Garbage filtering
# -------------------------------------------------

def is_garbage(text: str) -> bool:
    if not text:
        return True

    letters = sum(c.isalpha() for c in text)
    symbols = sum(not c.isalnum() for c in text)

    if letters == 0 and symbols > 3:
        return True

    if symbols > letters * 2:
        return True

    return False


def remove_garbage_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []

    for l in lines:
        text = (l.get("text") or "").strip()

        if is_garbage(text):
            continue

        cleaned.append(l)

    return cleaned


# -------------------------------------------------
# Hyphen merge
# -------------------------------------------------

def merge_hyphenated_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged = []
    i = 0

    while i < len(lines):
        current = lines[i]
        text = current.get("text", "")

        if text.endswith("-") and i + 1 < len(lines):
            nxt = lines[i + 1]
            merged_text = text[:-1] + nxt.get("text", "")

            new_line = dict(current)
            new_line["text"] = merged_text

            merged.append(new_line)

            i += 2
        else:
            merged.append(current)
            i += 1

    return merged


# -------------------------------------------------
# Main postprocess
# -------------------------------------------------

def postprocess_page_result(page_result: Dict[str, Any]) -> Dict[str, Any]:

    lines = page_result.get("lines", []) or []

    lines = sort_lines_by_layout(lines)

    lines = remove_garbage_lines(lines)

    lines = merge_hyphenated_lines(lines)

    out_lines = []

    for ln in lines:
        raw = (ln.get("text") or "").strip()

        clean = normalize_text(raw)

        new_ln = dict(ln)
        new_ln["text_raw"] = raw
        new_ln["text_clean"] = clean

        out_lines.append(new_ln)

    return {
        "lines": out_lines
    }


# -------------------------------------------------
# Directory processor
# -------------------------------------------------

def postprocess_ocr_dir(ocr_dir: Path, out_dir: Path) -> int:

    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))

    count = 0

    for p in pages:
        page_result = json.loads(p.read_text(encoding="utf-8"))

        cleaned = postprocess_page_result(page_result)

        out_path = out_dir / p.name

        out_path.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        count += 1

    return count