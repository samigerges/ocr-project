from __future__ import annotations

import json
import re
from pathlib import Path

from app.pipeline.invoice_extract import extract_invoice_fields, parse_amount
from app.pipeline.receipt_items import parse_line_items_from_ocr_lines
from app.pipeline.receipt_schema import ReceiptFields
from app.pipeline.receipt_validate import approximately_equal, validate_receipt


def _model_dump(model):
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _find_source_lines(lines: list[dict], pattern: str) -> list[str]:
    regex = re.compile(pattern, re.I)
    return [str(line.get("line_id")) for line in lines if regex.search(line.get("text", "")) and line.get("line_id")]


def _receipt_document_type(title: str | None, invoice_type: str) -> str:
    normalized = (title or invoice_type or "").lower()
    if "cash sales" in normalized:
        return "cash_sales"
    if "cash bill" in normalized:
        return "cash_bill"
    if "receipt" in normalized:
        return "receipt"
    if "invoice" in normalized:
        return "invoice"
    return "unknown"


def _extract_footer_note(lines: list[dict]) -> str | None:
    note_lines = []
    for line in lines[-8:]:
        text = (line.get("text") or "").strip()
        if re.search(r"thank|goods sold|return|exchange|note", text, re.I):
            note_lines.append(text)
    return " ".join(note_lines) or None


def _extract_handwritten_total(lines: list[dict], printed_total: float | None) -> float | None:
    """Conservative placeholder: only accept explicit handwriting/circled anchors from OCR text."""
    for line in lines:
        text = line.get("text", "")
        if not re.search(r"hand\s*written|circled|manual", text, re.I):
            continue
        amounts = [parse_amount(value) for value in re.findall(r"\d+(?:[,.]\d{2})", text)]
        amounts = [amount for amount in amounts if amount is not None]
        if amounts:
            return amounts[-1]
    return printed_total if printed_total is not None and _find_source_lines(lines, r"hand\s*written|circled|manual") else None


def extract_receipt_from_layout(doc_id: str, layout_payload: dict, extracted_dir: Path, validation_dir: Path) -> ReceiptFields:
    lines = layout_payload.get("lines", []) or []
    full_text = "\n".join(line.get("text", "") for line in lines)
    invoice_fields = extract_invoice_fields(full_text)
    line_items = parse_line_items_from_ocr_lines(lines)
    if not line_items:
        line_items = [
            {
                "item_code": item.get("item_code"),
                "description": item.get("description"),
                "qty": item.get("quantity"),
                "unit_price": item.get("unit_price"),
                "amount": item.get("amount"),
                "confidence": 0.0,
                "source_line_ids": [],
            }
            for item in invoice_fields.get("line_items", [])
        ]

    printed_total = invoice_fields.get("total_amount")
    handwritten_total = _extract_handwritten_total(lines, printed_total)
    final_total = printed_total
    if final_total is None and handwritten_total is not None:
        final_total = handwritten_total
    elif printed_total is not None and handwritten_total is not None and approximately_equal(printed_total, handwritten_total):
        final_total = printed_total

    receipt = ReceiptFields(
        merchant_name=invoice_fields.get("vendor_name"),
        merchant_address=invoice_fields.get("vendor_address"),
        phone=invoice_fields.get("vendor_phone"),
        email=invoice_fields.get("vendor_email"),
        gst_id=invoice_fields.get("gst_id"),
        document_type=_receipt_document_type(invoice_fields.get("document_title"), invoice_fields.get("document_type", "")),
        document_number=invoice_fields.get("invoice_number"),
        date=invoice_fields.get("invoice_date"),
        time=invoice_fields.get("transaction_time"),
        cashier=invoice_fields.get("cashier"),
        salesperson=invoice_fields.get("salesperson"),
        currency="RM" if invoice_fields.get("currency") == "MYR" else invoice_fields.get("currency", "RM"),
        line_items=line_items,
        subtotal=invoice_fields.get("subtotal"),
        discount=invoice_fields.get("discount"),
        rounding=invoice_fields.get("rounding"),
        total=printed_total,
        cash_paid=invoice_fields.get("cash_received"),
        change=invoice_fields.get("change_amount"),
        printed_total=printed_total,
        handwritten_total=handwritten_total,
        final_total=final_total,
        total_match=approximately_equal(printed_total, handwritten_total) if handwritten_total is not None else None,
        footer_note=_extract_footer_note(lines),
        source_line_ids={
            "document_number": _find_source_lines(lines, r"doc(?:ument)?\s*no"),
            "date": _find_source_lines(lines, r"\bdate\b"),
            "cashier": _find_source_lines(lines, r"\bcashier\b"),
            "total": _find_source_lines(lines, r"total\s+sales|rounded\s+total|\btotal\b"),
            "cash_paid": _find_source_lines(lines, r"\bcash\b"),
            "change": _find_source_lines(lines, r"\bchange\b"),
        },
    )

    report = validate_receipt(receipt)
    extracted_dir.mkdir(parents=True, exist_ok=True)
    validation_dir.mkdir(parents=True, exist_ok=True)
    receipt_payload = _model_dump(receipt)
    receipt_payload["doc_id"] = doc_id
    (extracted_dir / "receipt.json").write_text(json.dumps(receipt_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (validation_dir / "report.json").write_text(json.dumps(_model_dump(report), ensure_ascii=False, indent=2), encoding="utf-8")
    return receipt
