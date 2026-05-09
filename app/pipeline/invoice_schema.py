from __future__ import annotations

from typing import Any, TypedDict


class LineItem(TypedDict, total=False):
    description: str
    quantity: float | int | None
    unit_price: float | None
    amount: float | None


class InvoiceFields(TypedDict):
    document_type: str
    vendor_name: str | None
    vendor_address: str | None
    buyer_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    subtotal: float | None
    tax: float | None
    discount: float | None
    total_amount: float | None
    currency: str
    payment_method: str | None
    line_items: list[LineItem]
    confidence: float
    needs_review: bool
    review_reasons: list[str]


EMPTY_INVOICE: InvoiceFields = {
    "document_type": "invoice",
    "vendor_name": None,
    "vendor_address": None,
    "buyer_name": None,
    "invoice_number": None,
    "invoice_date": None,
    "due_date": None,
    "subtotal": None,
    "tax": None,
    "discount": None,
    "total_amount": None,
    "currency": "unknown",
    "payment_method": None,
    "line_items": [],
    "confidence": 0.0,
    "needs_review": True,
    "review_reasons": [],
}


def empty_invoice_fields() -> InvoiceFields:
    """Return a fresh invoice field dictionary with the required output keys."""
    copied: dict[str, Any] = dict(EMPTY_INVOICE)
    copied["line_items"] = []
    copied["review_reasons"] = []
    return copied  # type: ignore[return-value]
