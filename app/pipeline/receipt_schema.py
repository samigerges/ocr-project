from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReceiptLineItem(BaseModel):
    item_code: str | None = None
    description: str | None = None
    qty: float | int | None = None
    unit_price: float | None = None
    discount: float | None = None
    amount: float | None = None
    confidence: float = 0.0
    source_line_ids: list[str] = Field(default_factory=list)


class ReceiptFields(BaseModel):
    merchant_name: str | None = None
    merchant_address: str | None = None
    phone: str | None = None
    email: str | None = None
    gst_id: str | None = None
    document_type: Literal["cash_sales", "cash_bill", "receipt", "invoice", "unknown"] = "unknown"
    document_number: str | None = None
    date: str | None = None
    time: str | None = None
    cashier: str | None = None
    salesperson: str | None = None
    currency: str = "RM"
    line_items: list[ReceiptLineItem] = Field(default_factory=list)
    subtotal: float | None = None
    discount: float | None = None
    rounding: float | None = None
    total: float | None = None
    cash_paid: float | None = None
    change: float | None = None
    printed_total: float | None = None
    handwritten_total: float | None = None
    final_total: float | None = None
    total_match: bool | None = None
    footer_note: str | None = None
    source_line_ids: dict[str, list[str]] = Field(default_factory=dict)


class ReceiptValidationReport(BaseModel):
    is_valid: bool
    warnings: list[str] = Field(default_factory=list)
    checks: dict[str, float | bool | None] = Field(default_factory=dict)
