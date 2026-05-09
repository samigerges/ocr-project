from __future__ import annotations

import re

from app.pipeline.invoice_extract import AMOUNT_TOKEN, parse_amount
from app.pipeline.receipt_schema import ReceiptLineItem


def _to_quantity(value: float | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def _line_confidence(lines: list[dict]) -> float:
    values = [float(line.get("confidence", 0.0) or 0.0) for line in lines]
    return round(sum(values) / len(values), 2) if values else 0.0


def _append_description(item: ReceiptLineItem, text: str, line_id: str) -> None:
    if item.description and item.description != item.item_code:
        item.description = f"{item.description} {text}".strip()
    else:
        item.description = text
    if line_id not in item.source_line_ids:
        item.source_line_ids.append(line_id)


def parse_line_items_from_ocr_lines(lines: list[dict]) -> list[ReceiptLineItem]:
    """Parse weak/borderless receipt item tables from OCR lines and line positions."""
    items: list[ReceiptLineItem] = []
    pending: ReceiptLineItem | None = None
    pending_conf_lines: list[dict] = []
    in_table = False
    header_pattern = re.compile(r"\b(item|code/?desc|description)\b.*\b(qty|price|amount|disc|s/price)\b", re.I)
    stop_pattern = re.compile(r"\b(total\s+qty|total\s+sales|rounded\s+total|\btotal\b|cash|change|rounding|discount|subtotal)\b", re.I)

    def finalize() -> None:
        nonlocal pending, pending_conf_lines
        if pending and pending.description:
            pending.confidence = _line_confidence(pending_conf_lines)
            items.append(pending)
        pending = None
        pending_conf_lines = []

    for line in lines:
        text = (line.get("text") or "").strip()
        if not text:
            continue
        if header_pattern.search(text):
            in_table = True
            continue
        if in_table and stop_pattern.search(text):
            finalize()
            break
        if not in_table:
            continue

        line_id = str(line.get("line_id") or "")
        parts = text.split()
        code_row = len(parts) >= 4 and re.fullmatch(r"\d{3,}", parts[0] or "")
        if code_row:
            numeric_values = [parse_amount(part) for part in parts[1:]]
            numeric_values = [value for value in numeric_values if value is not None]
            if len(numeric_values) >= 3:
                finalize()
                pending = ReceiptLineItem(
                    item_code=parts[0],
                    description=parts[0],
                    qty=_to_quantity(numeric_values[0]),
                    unit_price=numeric_values[1],
                    discount=0.0 if len(numeric_values) >= 4 else None,
                    amount=numeric_values[-1],
                    source_line_ids=[line_id] if line_id else [],
                )
                pending_conf_lines = [line]
                continue

        if pending:
            amounts = [parse_amount(amount) for amount in re.findall(AMOUNT_TOKEN, text)]
            amounts = [amount for amount in amounts if amount is not None]
            if len(amounts) < 2:
                _append_description(pending, text, line_id)
                pending_conf_lines.append(line)
                continue

        amounts = [parse_amount(amount) for amount in re.findall(AMOUNT_TOKEN, text)]
        amounts = [amount for amount in amounts if amount is not None]
        if amounts:
            description = re.sub(AMOUNT_TOKEN + r"\s*$", "", text).strip(" -|\t")
            if description:
                items.append(
                    ReceiptLineItem(
                        description=description,
                        unit_price=amounts[-2] if len(amounts) >= 2 else None,
                        amount=amounts[-1],
                        confidence=_line_confidence([line]),
                        source_line_ids=[line_id] if line_id else [],
                    )
                )

    finalize()
    return items[:100]
