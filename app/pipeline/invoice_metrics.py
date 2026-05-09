from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Iterable


@dataclass
class InvoiceEvaluationSummary:
    invoice_number_accuracy: float
    invoice_date_accuracy: float
    total_amount_accuracy: float
    vendor_name_accuracy: float
    needs_review_percentage: float
    average_confidence: float
    document_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _accuracy(matches: int, total: int) -> float:
    return round(matches / total, 4) if total else 0.0


def summarize_invoice_evaluation(rows: Iterable[dict]) -> InvoiceEvaluationSummary:
    materialized = list(rows)
    total = len(materialized)
    return InvoiceEvaluationSummary(
        invoice_number_accuracy=_accuracy(sum(1 for row in materialized if row.get("invoice_number_match")), total),
        invoice_date_accuracy=_accuracy(sum(1 for row in materialized if row.get("invoice_date_match")), total),
        total_amount_accuracy=_accuracy(sum(1 for row in materialized if row.get("total_amount_match")), total),
        vendor_name_accuracy=_accuracy(sum(1 for row in materialized if row.get("vendor_name_match")), total),
        needs_review_percentage=round(sum(1 for row in materialized if row.get("needs_review")) / total * 100, 2) if total else 0.0,
        average_confidence=round(sum(float(row.get("confidence") or 0.0) for row in materialized) / total, 4) if total else 0.0,
        document_count=total,
    )
