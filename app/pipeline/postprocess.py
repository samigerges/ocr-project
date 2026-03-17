from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Dict, List, Any


# -------------------------------------------------
# Character normalization
# -------------------------------------------------

CHAR_REPLACEMENTS = {
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\u2014": "-",
    "\u2013": "-",
}

COMMON_OCR_WORD_REPLACEMENTS = {
    r"\bCoumittee\b": "Committee",
    r"\bmathenatics\b": "mathematics",
    r"\bIearned\b": "learned",
}

WORD_JOIN_MARKERS = ("-", "~", "\u00ac")
MID_SENTENCE_FUNCTION_WORDS = (
    "a",
    "an",
    "and",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
)


def normalize_punctuation(text: str) -> str:
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r",\.(?=\s|$)", ",", text)
    text = re.sub(r"\.,(?=\s|$)", ".", text)
    text = re.sub(r"\.{2,}", ".", text)

    function_words = "|".join(MID_SENTENCE_FUNCTION_WORDS)
    text = re.sub(
        rf"\b({function_words})\.\s+(?=[A-Z][a-z])",
        lambda match: f"{match.group(1)} ",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(r"([A-Za-z]),\.(?=\s|$)", r"\1,", text)
    text = re.sub(r"([A-Za-z])\.(?=\s+[a-z])", r"\1", text)

    return text


def normalize_text(text: str) -> str:
    for k, v in CHAR_REPLACEMENTS.items():
        text = text.replace(k, v)

    for pattern, replacement in COMMON_OCR_WORD_REPLACEMENTS.items():
        text = re.sub(pattern, replacement, text)

    text = re.sub(r"\b[Il](\d{2})[Il]\b", lambda match: f"1{match.group(1)}1", text)
    text = re.sub(r"\b[Il](\d{3})\b", lambda match: f"1{match.group(1)}", text)
    text = re.sub(r"\b(\d{3})[Il]\b", lambda match: f"{match.group(1)}1", text)
    text = re.sub(r"(?<=\w)~(?=\w|$)", "", text)
    text = normalize_punctuation(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# -------------------------------------------------
# Layout sorting
# -------------------------------------------------

def sort_lines_by_layout(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort lines using bounding box coordinates.
    """

    def key_fn(line: Dict[str, Any]) -> tuple[float, float]:
        bbox = line.get("bbox")
        if not bbox:
            return (0.0, 0.0)

        x = bbox[0][0]
        y = bbox[0][1]

        return (float(y), float(x))

    return sorted(lines, key=key_fn)


def _bbox_bounds(line: Dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = line.get("bbox")
    if not bbox:
        return None

    xs = [point[0] for point in bbox]
    ys = [point[1] for point in bbox]

    return min(xs), min(ys), max(xs), max(ys)


def _merge_bboxes(
    bbox_a: List[List[float]] | None,
    bbox_b: List[List[float]] | None,
) -> List[List[float]] | None:
    if not bbox_a:
        return bbox_b
    if not bbox_b:
        return bbox_a

    xs = [point[0] for point in bbox_a] + [point[0] for point in bbox_b]
    ys = [point[1] for point in bbox_a] + [point[1] for point in bbox_b]

    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)

    return [
        [left, top],
        [right, top],
        [right, bottom],
        [left, bottom],
    ]


def _should_merge_inline_fragments(
    previous: Dict[str, Any],
    current: Dict[str, Any],
) -> bool:
    prev_bounds = _bbox_bounds(previous)
    curr_bounds = _bbox_bounds(current)

    if not prev_bounds or not curr_bounds:
        return False

    _, prev_top, prev_right, prev_bottom = prev_bounds
    curr_left, curr_top, _, curr_bottom = curr_bounds

    prev_height = max(prev_bottom - prev_top, 1.0)
    curr_height = max(curr_bottom - curr_top, 1.0)
    center_y_gap = abs(((prev_top + prev_bottom) / 2.0) - ((curr_top + curr_bottom) / 2.0))
    horizontal_gap = curr_left - prev_right

    return (
        center_y_gap <= max(prev_height, curr_height) * 0.6
        and horizontal_gap <= max(24.0, max(prev_height, curr_height) * 2.5)
    )


def merge_inline_fragments(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []

    for line in lines:
        if not merged:
            merged.append(line)
            continue

        previous = merged[-1]
        if not _should_merge_inline_fragments(previous, line):
            merged.append(line)
            continue

        prev_text = (previous.get("text") or "").rstrip()
        curr_text = (line.get("text") or "").lstrip()

        if not prev_text or not curr_text:
            merged.append(line)
            continue

        joiner = ""
        if prev_text.endswith(WORD_JOIN_MARKERS):
            prev_text = prev_text[:-1]
        elif not curr_text.startswith((",", ".", ";", ":", "?", "!")):
            joiner = " "

        merged_line = dict(previous)
        merged_line["text"] = f"{prev_text}{joiner}{curr_text}"
        merged_line["bbox"] = _merge_bboxes(previous.get("bbox"), line.get("bbox"))

        prev_conf = float(previous.get("confidence", 0.0) or 0.0)
        curr_conf = float(line.get("confidence", 0.0) or 0.0)
        merged_line["confidence"] = max(prev_conf, curr_conf)

        merged[-1] = merged_line

    return merged


# -------------------------------------------------
# Vertical text filtering
# -------------------------------------------------

def is_vertical_text(line: Dict[str, Any], ratio_threshold: float = 4.0) -> bool:
    """
    Detect vertical text using bbox aspect ratio.
    Removes margin numbers and rotated text.
    """

    bbox = line.get("bbox")

    if not bbox or len(bbox) < 4:
        return False

    try:
        x0, y0 = bbox[0]
        x1, y1 = bbox[1]
        x2, y2 = bbox[2]

        width = abs(x1 - x0)
        height = abs(y2 - y1)

        if width == 0:
            return True

        ratio = height / width

        return ratio > ratio_threshold

    except Exception:
        return False


def remove_vertical_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []

    for line in lines:
        if is_vertical_text(line):
            continue

        cleaned.append(line)

    return cleaned


# -------------------------------------------------
# Garbage filtering
# -------------------------------------------------

def is_garbage(text: str) -> bool:
    if not text:
        return True

    letters = sum(c.isalpha() for c in text)
    symbols = sum(not c.isalnum() and not c.isspace() for c in text)

    if letters == 0 and symbols > 3:
        return True

    if letters > 0 and symbols > letters * 2:
        return True

    return False


def remove_garbage_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned = []

    for line in lines:
        text = (line.get("text") or "").strip()

        if is_garbage(text):
            continue

        cleaned.append(line)

    return cleaned


def is_edge_noise(line: Dict[str, Any]) -> bool:
    text = (line.get("text") or "").strip()
    if len(text) > 2:
        return False

    confidence = float(line.get("confidence", 1.0) or 1.0)
    if confidence >= 0.8:
        return False

    bounds = _bbox_bounds(line)
    if not bounds:
        return False

    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    area = width * height

    return (
        area < 2000
        and (
            top < 160
            or left < 80
        )
    )


def remove_edge_noise_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [line for line in lines if not is_edge_noise(line)]


# -------------------------------------------------
# Hyphen merge
# -------------------------------------------------

def merge_hyphenated_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge lines like:
        includ-
        ing

    -> including
    """

    merged = []
    i = 0

    while i < len(lines):
        current = lines[i]
        text = (current.get("text") or "").rstrip()

        if text.endswith(WORD_JOIN_MARKERS) and i + 1 < len(lines):
            nxt = lines[i + 1]
            next_text = (nxt.get("text") or "").lstrip()

            merged_text = text[:-1] + next_text

            new_line = dict(current)
            new_line["text"] = merged_text
            new_line["bbox"] = _merge_bboxes(current.get("bbox"), nxt.get("bbox"))

            curr_conf = float(current.get("confidence", 0.0) or 0.0)
            next_conf = float(nxt.get("confidence", 0.0) or 0.0)
            new_line["confidence"] = max(curr_conf, next_conf)

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
    lines = remove_vertical_lines(lines)
    lines = remove_garbage_lines(lines)
    lines = remove_edge_noise_lines(lines)
    lines = merge_inline_fragments(lines)
    lines = merge_hyphenated_lines(lines)

    out_lines = []

    for line in lines:
        raw = (line.get("text") or "").strip()
        clean = normalize_text(raw)

        new_line = dict(line)
        new_line["text_raw"] = raw
        new_line["text_clean"] = clean
        out_lines.append(new_line)

    return {"lines": out_lines}


# -------------------------------------------------
# Directory processor
# -------------------------------------------------

def postprocess_ocr_dir(ocr_dir: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))
    count = 0

    for page_path in pages:
        page_result = json.loads(page_path.read_text(encoding="utf-8"))
        cleaned = postprocess_page_result(page_result)

        out_path = out_dir / page_path.name
        out_path.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        count += 1

    return count
