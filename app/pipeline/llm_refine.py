from __future__ import annotations

from pathlib import Path
import json
import requests
from typing import List, Dict, Any

# ------------------------------
# Configuration
# ------------------------------

CONFIDENCE_THRESHOLD = 0.95

OLLAMA_URL = "http://host.docker.internal:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"


# ------------------------------
# Prompts
# ------------------------------

CORRECTION_PROMPT = """
You are correcting OCR spelling mistakes.

Rules:
- Fix only spelling errors caused by OCR.
- Preserve the meaning exactly.
- Do NOT invent information.
- Do NOT modify numbers, emails, URLs, IDs, or dates.

Text:
{text}

Return the corrected text only.
"""


REORDER_PROMPT = """
You are reconstructing the correct reading order of OCR text.

The text lines are already corrected but may be in the wrong order.

Your task:
- Reorder them into the correct reading order.
- Merge lines if they belong to the same sentence.

Rules:
- Do NOT invent information.
- Do NOT change the content.
- Only reorder or merge lines.

Lines:
{lines}

Return the reconstructed text.
"""


# ------------------------------
# LLM Call
# ------------------------------

def _call_llm(prompt: str) -> str:

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    r = requests.post(OLLAMA_URL, json=payload)
    r.raise_for_status()

    data = r.json()

    return data["response"].strip()


# ------------------------------
# Spelling correction
# ------------------------------

def spelling_correction(text: str) -> str:

    if not text.strip():
        return text

    prompt = CORRECTION_PROMPT.format(text=text)

    try:
        return _call_llm(prompt)
    except Exception:
        # fallback if LLM fails
        return text


# ------------------------------
# Semantic reorder
# ------------------------------

def semantic_reorder(lines: List[str]) -> str:

    if not lines:
        return ""

    # numbering improves LLM reasoning
    numbered_lines = "\n".join(
        f"{i+1}. {line}" for i, line in enumerate(lines) if line.strip()
    )

    prompt = REORDER_PROMPT.format(lines=numbered_lines)

    try:
        return _call_llm(prompt)
    except Exception:
        # fallback if LLM fails
        return "\n".join(lines)


# ------------------------------
# Page refinement
# ------------------------------

def refine_page(page_result: Dict[str, Any]) -> Dict[str, Any]:

    lines = page_result.get("lines", [])

    corrected_lines = []

    output_lines = []

    for ln in lines:

        text = ln.get("text_clean") or ln.get("text") or ""
        confidence = ln.get("confidence", 1.0)

        new_ln = dict(ln)

        new_ln["text_before_llm"] = text

        # correct only low confidence
        if confidence < CONFIDENCE_THRESHOLD:

            corrected = spelling_correction(text)

            new_ln["text_after_llm"] = corrected
            new_ln["llm_corrected"] = True

        else:

            corrected = text

            new_ln["text_after_llm"] = corrected
            new_ln["llm_corrected"] = False

        corrected_lines.append(corrected)
        output_lines.append(new_ln)

    # reorder after correction
    reordered_text = semantic_reorder(corrected_lines)

    return {
        "lines": output_lines,
        "reordered_text": reordered_text
    }


# ------------------------------
# Directory refinement
# ------------------------------

def refine_ocr_dir(ocr_dir: Path, out_dir: Path) -> int:

    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))

    count = 0

    for p in pages:

        page_result = json.loads(
            p.read_text(encoding="utf-8")
        )

        refined = refine_page(page_result)

        (out_dir / p.name).write_text(
            json.dumps(refined, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        count += 1

    return count