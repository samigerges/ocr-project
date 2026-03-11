from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional


# Tokenization: words + non-words (keep separators)
WORD_RE = re.compile(r"[A-Za-z]+|[^A-Za-z]+")


def tokenize_keep_separators(text: str) -> List[str]:
    return WORD_RE.findall(text)


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            dele = prev[j] + 1
            sub = prev[j - 1] + (ca != cb)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def is_letters_only(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z]+", token))


def looks_sensitive(token: str) -> bool:
    """
    Skip anything that could be an email/url/id/code/date/number/mixed.
    """
    if "@" in token:
        return True
    if "://" in token or token.startswith("www."):
        return True
    if re.search(r"\d", token):
        return True
    if re.search(r"[_\-#/\\]", token):
        return True
    return False


def preserve_case(original: str, corrected: str) -> str:
    if original.isupper():
        return corrected.upper()
    if original.istitle():
        return corrected.title()
    if original.islower():
        return corrected.lower()
    return corrected


@dataclass
class PostprocessConfig:
    enabled: bool = True
    max_edit_distance: int = 1
    max_word_len: int = 25
    dictionary: Optional[set[str]] = None


DEFAULT_COMMON_WORDS = {
    # starter list (expand later)
    "name", "professor", "current", "position", "my", "is", "and", "the", "a", "an",
    "email", "phone", "address", "skills", "experience", "education", "summary",
    "project", "projects", "work", "university", "engineer", "engineering",
}


def build_default_config() -> PostprocessConfig:
    return PostprocessConfig(dictionary=set(DEFAULT_COMMON_WORDS))


def best_dictionary_match(token: str, cfg: PostprocessConfig) -> Optional[str]:
    if not cfg.dictionary:
        return None

    low = token.lower()
    if low in cfg.dictionary:
        return None

    best = None
    best_dist = 10**9

    for w in cfg.dictionary:
        if abs(len(w) - len(low)) > cfg.max_edit_distance:
            continue
        d = levenshtein(low, w)
        if d < best_dist:
            best_dist = d
            best = w
            if best_dist == 0:
                break

    if best is None or best_dist > cfg.max_edit_distance:
        return None

    return preserve_case(token, best)


def postprocess_text(text: str, cfg: PostprocessConfig) -> Dict[str, Any]:
    tokens = tokenize_keep_separators(text)
    corrections = []

    for i, tok in enumerate(tokens):
        if not is_letters_only(tok):
            continue
        if looks_sensitive(tok):
            continue
        if len(tok) > cfg.max_word_len:
            continue

        new_tok = best_dictionary_match(tok, cfg) if cfg.enabled else None
        if new_tok and new_tok != tok:
            corrections.append({"from": tok, "to": new_tok, "token_index": i})
            tokens[i] = new_tok

    return {"text_out": "".join(tokens), "corrections": corrections}


def postprocess_page_result(page_result: Dict[str, Any], cfg: PostprocessConfig) -> Dict[str, Any]:
    lines = page_result.get("lines", []) or []
    out_lines = []
    page_corrections = []

    for ln in lines:
        raw = (ln.get("text") or "").strip()
        processed = postprocess_text(raw, cfg) if cfg.enabled else {"text_out": raw, "corrections": []}

        out_ln = dict(ln)
        out_ln["text_raw"] = raw
        out_ln["text_clean"] = processed["text_out"]
        out_ln["corrections"] = processed["corrections"]

        if processed["corrections"]:
            page_corrections.extend(processed["corrections"])

        out_lines.append(out_ln)

    return {"lines": out_lines, "corrections": page_corrections}


def postprocess_ocr_dir(ocr_dir: Path, out_dir: Path, cfg: Optional[PostprocessConfig] = None) -> int:
    cfg = cfg or build_default_config()
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = sorted(ocr_dir.glob("page_*.json"))
    count = 0
    for p in pages:
        page_result = json.loads(p.read_text(encoding="utf-8"))
        cleaned = postprocess_page_result(page_result, cfg)
        (out_dir / p.name).write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        count += 1
    return count