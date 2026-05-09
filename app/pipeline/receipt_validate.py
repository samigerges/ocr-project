from __future__ import annotations

from app.pipeline.receipt_schema import ReceiptFields, ReceiptValidationReport

MONEY_TOLERANCE = 0.02
LINE_SUM_TOLERANCE = 0.05


def approximately_equal(left: float | None, right: float | None, tolerance: float = MONEY_TOLERANCE) -> bool:
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) <= tolerance


def validate_receipt(receipt: ReceiptFields) -> ReceiptValidationReport:
    warnings: list[str] = []
    line_amounts = [float(item.amount) for item in receipt.line_items if item.amount is not None]
    line_sum = round(sum(line_amounts), 2) if line_amounts else None
    total = receipt.final_total if receipt.final_total is not None else receipt.total

    if receipt.document_number is None:
        warnings.append("document_number_missing")
    if receipt.merchant_name is None:
        warnings.append("merchant_missing")
    if receipt.date is None:
        warnings.append("date_missing")
    if total is None:
        warnings.append("total_missing")

    if line_sum is not None and total is not None and not approximately_equal(line_sum, total, LINE_SUM_TOLERANCE):
        warnings.append("line_item_sum_does_not_match_total")

    for index, item in enumerate(receipt.line_items, start=1):
        if item.qty is not None and item.unit_price is not None and item.amount is not None:
            expected = round(float(item.qty) * float(item.unit_price), 2)
            if not approximately_equal(expected, float(item.amount), LINE_SUM_TOLERANCE):
                warnings.append(f"line_{index}_quantity_price_amount_mismatch")

    expected_change = None
    if receipt.cash_paid is not None and total is not None:
        expected_change = round(float(receipt.cash_paid) - float(total), 2)
        if receipt.change is not None and not approximately_equal(expected_change, float(receipt.change)):
            warnings.append("cash_paid_change_calculation_failed")

    printed_total = receipt.printed_total if receipt.printed_total is not None else receipt.total
    handwritten_total = receipt.handwritten_total
    total_match = None
    if printed_total is not None and handwritten_total is not None:
        total_match = approximately_equal(printed_total, handwritten_total)
        if not total_match:
            warnings.append("handwritten_total_does_not_match_printed_total")

    return ReceiptValidationReport(
        is_valid=not warnings,
        warnings=warnings,
        checks={
            "line_items_sum": line_sum,
            "printed_total": printed_total,
            "handwritten_total": handwritten_total,
            "cash_paid": receipt.cash_paid,
            "change": receipt.change,
            "expected_change": expected_change,
            "totals_match": total_match if total_match is not None else (approximately_equal(line_sum, total, LINE_SUM_TOLERANCE) if line_sum is not None and total is not None else None),
        },
    )
