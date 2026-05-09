from __future__ import annotations


from app.pipeline.invoice_schema import InvoiceFields

MONEY_TOLERANCE = 0.02
LINE_SUM_TOLERANCE = 0.05


def approximately_equal(left: float | None, right: float | None, tolerance: float = MONEY_TOLERANCE) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 2)))


def calculate_confidence(fields: InvoiceFields, arithmetic_valid: bool) -> float:
    score = 0.0
    if fields.get("invoice_number"):
        score += 0.15
    if fields.get("invoice_date"):
        score += 0.15
    if fields.get("total_amount") is not None:
        score += 0.25
    if fields.get("vendor_name"):
        score += 0.15
    if fields.get("currency") and fields.get("currency") != "unknown":
        score += 0.10
    if fields.get("line_items"):
        score += 0.10
    if arithmetic_valid:
        score += 0.10
    return clamp_confidence(score)


def validate_invoice_fields(fields: InvoiceFields, *, extra_review_reasons: list[str] | None = None) -> InvoiceFields:
    """Apply deterministic invoice validation, confidence scoring, and review flags."""
    reasons = set(fields.get("review_reasons") or [])
    if extra_review_reasons:
        reasons.update(extra_review_reasons)

    if not fields.get("invoice_number"):
        reasons.add("missing_invoice_number")
    if not fields.get("invoice_date"):
        reasons.add("missing_invoice_date")
    if fields.get("total_amount") is None:
        reasons.add("missing_total_amount")
    if not fields.get("currency") or fields.get("currency") == "unknown":
        fields["currency"] = "unknown"
        reasons.add("currency_not_detected")

    arithmetic_valid = True
    subtotal = fields.get("subtotal")
    tax = fields.get("tax")
    discount = fields.get("discount")
    total = fields.get("total_amount")

    if total is not None and subtotal is not None and (tax is not None or discount is not None):
        expected_total = float(subtotal) + float(tax or 0.0) - float(discount or 0.0)
        arithmetic_valid = approximately_equal(float(total), expected_total)
        if not arithmetic_valid:
            reasons.add("total_mismatch")

    line_items = fields.get("line_items") or []
    line_amounts = [item.get("amount") for item in line_items if item.get("amount") is not None]
    if subtotal is not None and line_amounts:
        line_sum = sum(float(amount) for amount in line_amounts if amount is not None)
        if not approximately_equal(float(subtotal), line_sum, LINE_SUM_TOLERANCE):
            reasons.add("line_items_subtotal_mismatch")
            arithmetic_valid = False

    fields["confidence"] = calculate_confidence(fields, arithmetic_valid)
    if fields["confidence"] < 0.75:
        reasons.add("low_ocr_confidence")

    blocking_reasons = {
        "missing_invoice_number",
        "missing_invoice_date",
        "missing_total_amount",
        "ambiguous_date_format",
        "total_mismatch",
        "line_items_subtotal_mismatch",
    }
    fields["needs_review"] = fields["confidence"] < 0.75 or bool(reasons & blocking_reasons)
    fields["review_reasons"] = sorted(reasons)
    return fields
