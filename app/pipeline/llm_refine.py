from __future__ import annotations

from pathlib import Path
import json
import re
import requests
from typing import List, Dict, Any
from difflib import SequenceMatcher


# ------------------------------
# Configuration
# ------------------------------

CONFIDENCE_THRESHOLD = 0.985
MAX_CHANGED_TOKENS = 4

SUSPICIOUS_LINE_PATTERNS = (
    r",\.",
    r"\.\.",
    r"\b(?:a|an|and|at|by|for|from|in|of|on|or|the|to|with)\.\s+[A-Z][a-z]",
    r"\b[Il]\d{2,}[Il]?\b",
    r"\b\d{2,}[Il]\b",
    r"[~|`]",
)

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"


# ------------------------------
# Prompts
# ------------------------------

CORRECTION_PROMPT = """
You are correcting OCR spelling and punctuation mistakes.

STRICT RULES:
- Fix ONLY clear OCR spelling and punctuation errors.
- Do NOT change names, organizations, journals, or locations.
- Do NOT change numbers, emails, URLs, IDs, or dates.
- Do NOT rewrite sentences.
- Do NOT replace words with synonyms.
- If the text is already correct, return it unchanged.

Text:
{text}

Return ONLY the corrected text.
"""


# ------------------------------
# LLM Call
# ------------------------------

def _call_llm(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    response = requests.post(OLLAMA_URL, json=payload)
    response.raise_for_status()

    data = response.json()
    return data["response"].strip()


# ------------------------------
# Safety guard
# ------------------------------

def tokenize_text(text: str) -> List[str]:
    return re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)


def changed_token_count(original: str, corrected: str) -> int:
    original_tokens = tokenize_text(original)
    corrected_tokens = tokenize_text(corrected)
    matcher = SequenceMatcher(None, original_tokens, corrected_tokens)

    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += max(i2 - i1, j2 - j1)

    return changed


def numbers_preserved(original: str, corrected: str) -> bool:
    return re.findall(r"\d+", original) == re.findall(r"\d+", corrected)


def is_safe_correction(original: str, corrected: str, threshold: float = 0.90) -> bool:
    """
    Prevent large semantic changes from the LLM.
    """
    if not numbers_preserved(original, corrected):
        return False

    ratio = SequenceMatcher(None, original, corrected).ratio()
    if ratio < threshold:
        return False

    if abs(len(corrected) - len(original)) > max(12, int(len(original) * 0.2)):
        return False

    max_changed = max(MAX_CHANGED_TOKENS, len(tokenize_text(original)) // 4)
    return changed_token_count(original, corrected) <= max_changed


def line_needs_refinement(text: str, confidence: float) -> bool:
    stripped = text.strip()
    if not stripped:
        return False

    if confidence < CONFIDENCE_THRESHOLD:
        return True

    return any(re.search(pattern, stripped) for pattern in SUSPICIOUS_LINE_PATTERNS)


# ------------------------------
# Spelling correction
# ------------------------------

def spelling_correction(text: str) -> str:
    if not text.strip():
        return text

    if len(text.split()) <= 2:
        return text

    prompt = CORRECTION_PROMPT.format(text=text)

    try:
        corrected = _call_llm(prompt)

        if not is_safe_correction(text, corrected):
            return text

        return corrected

    except Exception:
        return text


# ------------------------------
# Page refinement
# ------------------------------

def refine_page(page_result: Dict[str, Any]) -> Dict[str, Any]:
    lines = page_result.get("lines", [])

    corrected_lines = []
    output_lines = []

    for line in lines:
        text = line.get("text_clean") or line.get("text") or ""
        confidence = float(line.get("confidence", 1.0) or 1.0)

        new_line = dict(line)
        new_line["text_before_llm"] = text

        if line_needs_refinement(text, confidence):
            corrected = spelling_correction(text)
            new_line["text_after_llm"] = corrected
            new_line["llm_corrected"] = corrected != text
        else:
            corrected = text
            new_line["text_after_llm"] = corrected
            new_line["llm_corrected"] = False

        corrected_lines.append(corrected)
        output_lines.append(new_line)

    reordered_text = "\n".join(corrected_lines)

    return {
        "lines": output_lines,
        "reordered_text": reordered_text,
    }


# ------------------------------
# Directory refinement
# ------------------------------

def refine_ocr_dir(ocr_dir: Path, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))
    count = 0

    for page_path in pages:
        page_result = json.loads(page_path.read_text(encoding="utf-8"))
        refined = refine_page(page_result)

        (out_dir / page_path.name).write_text(
            json.dumps(refined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        count += 1

    return count
