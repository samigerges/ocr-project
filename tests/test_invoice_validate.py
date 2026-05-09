from app.pipeline.invoice_schema import empty_invoice_fields
from app.pipeline.invoice_validate import calculate_confidence, validate_invoice_fields


def test_total_validation_passes_and_confidence_scores():
    fields = empty_invoice_fields()
    fields.update(
        {
            "vendor_name": "Acme",
            "invoice_number": "INV-1",
            "invoice_date": "2026-05-09",
            "subtotal": 100.0,
            "tax": 10.0,
            "discount": 5.0,
            "total_amount": 105.0,
            "currency": "USD",
            "line_items": [{"description": "Service", "quantity": 1, "unit_price": 100.0, "amount": 100.0}],
        }
    )
    validated = validate_invoice_fields(fields)
    assert validated["confidence"] == 1.0
    assert validated["needs_review"] is False
    assert "total_mismatch" not in validated["review_reasons"]


def test_needs_review_for_missing_required_fields():
    fields = empty_invoice_fields()
    fields["vendor_name"] = "Acme"
    validated = validate_invoice_fields(fields)
    assert validated["needs_review"] is True
    assert "missing_invoice_number" in validated["review_reasons"]
    assert "missing_invoice_date" in validated["review_reasons"]
    assert "missing_total_amount" in validated["review_reasons"]
    assert "currency_not_detected" in validated["review_reasons"]


def test_total_mismatch_needs_review():
    fields = empty_invoice_fields()
    fields.update(
        {
            "vendor_name": "Acme",
            "invoice_number": "INV-2",
            "invoice_date": "2026-05-09",
            "subtotal": 100.0,
            "tax": 10.0,
            "total_amount": 999.0,
            "currency": "USD",
        }
    )
    validated = validate_invoice_fields(fields)
    assert validated["needs_review"] is True
    assert "total_mismatch" in validated["review_reasons"]


def test_confidence_scoring_partial():
    fields = empty_invoice_fields()
    fields.update({"invoice_number": "INV-3", "invoice_date": "2026-05-09", "total_amount": 50.0})
    assert calculate_confidence(fields, arithmetic_valid=False) == 0.55
