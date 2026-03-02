import string


def _is_reasonable_char(ch: str) -> bool:
    """
    Treat ASCII printable + Arabic ranges as 'reasonable'.
    Helps detect 'garbage' text layers.
    """
    if ch in string.printable:
        return True

    code = ord(ch)
    # Arabic blocks
    if 0x0600 <= code <= 0x06FF:
        return True
    if 0x0750 <= code <= 0x077F:
        return True
    if 0x08A0 <= code <= 0x08FF:
        return True
    return False


def text_quality(text: str) -> dict:
    t = (text or "").strip()
    if not t:
        return {"char_count": 0, "word_count": 0, "printable_ratio": 0.0}

    chars = list(t)
    char_count = len(chars)
    word_count = len(t.split())

    reasonable = sum(1 for c in chars if _is_reasonable_char(c))
    printable_ratio = reasonable / max(1, char_count)

    return {
        "char_count": char_count,
        "word_count": word_count,
        "printable_ratio": float(printable_ratio),
    }


def should_use_native_text(extracted_text: str) -> bool:
    """
    Decide whether native PDF text is good enough to skip OCR.
    Tunable thresholds.
    """
    q = text_quality(extracted_text)
    return (
        q["char_count"] >= 50
        and q["word_count"] >= 5
        and q["printable_ratio"] >= 0.85
    )