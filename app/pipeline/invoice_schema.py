from __future__ import annotations

from typing import Any, TypedDict


class LineItem(TypedDict, total=False):
    item_code: str
    description: str
    quantity: float | int | None
    unit_price: float | None
    amount: float | None


class InvoiceFields(TypedDict):
    document_type: str
    document_title: str | None
    vendor_name: str | None
    vendor_registration_number: str | None
    vendor_address: str | None
    vendor_phone: str | None
    vendor_fax: str | None
    vendor_email: str | None
    gst_id: str | None
    buyer_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    subtotal: float | None
    tax: float | None
    discount: float | None
    total_amount: float | None
    total_quantity: float | int | None
    cash_received: float | None
    change_amount: float | None
    currency: str
    payment_method: str | None
    cashier: str | None
    transaction_time: str | None
    salesperson: str | None
    reference: str | None
    rounding: float | None
    line_items: list[LineItem]
    confidence: float
    needs_review: bool
    review_reasons: list[str]


EMPTY_INVOICE: InvoiceFields = {
    "document_type": "invoice",
    "document_title": None,
    "vendor_name": None,
    "vendor_registration_number": None,
    "vendor_address": None,
    "vendor_phone": None,
    "vendor_fax": None,
    "vendor_email": None,
    "gst_id": None,
    "buyer_name": None,
    "invoice_number": None,
    "invoice_date": None,
    "due_date": None,
    "subtotal": None,
    "tax": None,
    "discount": None,
    "total_amount": None,
    "total_quantity": None,
    "cash_received": None,
    "change_amount": None,
    "currency": "unknown",
    "payment_method": None,
    "cashier": None,
    "transaction_time": None,
    "salesperson": None,
    "reference": None,
    "rounding": None,
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
