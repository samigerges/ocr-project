from __future__ import annotations

from pathlib import Path
import json
import requests

CONFIDENCE_THRESHOLD = 0.96

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:7b"


PROMPT_TEMPLATE = """
You are correcting OCR output.

Rules:
- Fix spelling mistakes caused by OCR.
- Do NOT invent information.
- Do NOT change numbers, emails, URLs, or IDs.
- Keep the meaning exactly the same.

Return ONLY the corrected line.

OCR line:
{line}
"""


def refine_line_with_llm(text: str) -> str:

    prompt = PROMPT_TEMPLATE.format(line=text)

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    r = requests.post(OLLAMA_URL, json=payload)
    r.raise_for_status()

    data = r.json()

    return data["response"].strip()


def refine_page(page_result: dict) -> dict:

    lines = page_result.get("lines", [])

    new_lines = []
    refined_count = 0

    for ln in lines:

        text = ln.get("text_clean") or ln.get("text") or ""
        confidence = ln.get("confidence", 1.0)

        new_ln = dict(ln)

        new_ln["text_before_llm"] = text

        if confidence < CONFIDENCE_THRESHOLD and text.strip():

            try:
                refined = refine_line_with_llm(text)

                new_ln["text_after_llm"] = refined
                new_ln["llm_used"] = True

                refined_count += 1

            except Exception:
                new_ln["text_after_llm"] = text
                new_ln["llm_used"] = False

        else:

            new_ln["text_after_llm"] = text
            new_ln["llm_used"] = False

        new_lines.append(new_ln)

    return {
        "lines": new_lines,
        "refined_lines": refined_count
    }


def refine_ocr_dir(ocr_dir: Path, out_dir: Path) -> int:

    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))

    count = 0

    for p in pages:

        page_result = json.loads(p.read_text(encoding="utf-8"))

        refined = refine_page(page_result)

        (out_dir / p.name).write_text(
            json.dumps(refined, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        count += 1

    return count