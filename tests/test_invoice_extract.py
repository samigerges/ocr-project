from app.pipeline.invoice_extract import extract_invoice_fields, extract_invoice_number, parse_amount, parse_invoice_date


def test_parse_amount_common_formats():
    assert parse_amount("1,250.00") == 1250.00
    assert parse_amount("1250.00") == 1250.00
    assert parse_amount("EGP 1,250") == 1250.00
    assert parse_amount("$1,250.50") == 1250.50
    assert parse_amount("1.250,50") == 1250.50


def test_parse_invoice_date_safe_and_ambiguous():
    assert parse_invoice_date("2026-05-09") == ("2026-05-09", False)
    assert parse_invoice_date("9 May 2026") == ("2026-05-09", False)
    assert parse_invoice_date("May 9, 2026") == ("2026-05-09", False)
    assert parse_invoice_date("09/05/2026") == ("09/05/2026", True)


def test_invoice_number_extraction():
    assert extract_invoice_number("Invoice No: INV-2026-0042") == "INV-2026-0042"


def test_extract_invoice_fields_end_to_end():
    text = """Acme Supplies LLC
123 Market Street
Invoice No: INV-1001
Invoice Date: 2026-05-09
Due Date: May 30, 2026
Bill To: Beta Co
Description Qty Unit Amount
Consulting 2 50.00 100.00
Subtotal: USD 100.00
Tax: USD 10.00
Discount: USD 5.00
Total Amount: USD 105.00
Payment Method: bank transfer
"""
    fields = extract_invoice_fields(text)
    assert fields["vendor_name"] == "Acme Supplies LLC"
    assert fields["buyer_name"] == "Beta Co"
    assert fields["invoice_number"] == "INV-1001"
    assert fields["invoice_date"] == "2026-05-09"
    assert fields["due_date"] == "2026-05-30"
    assert fields["total_amount"] == 105.00
    assert fields["currency"] == "USD"
    assert fields["line_items"]
    assert fields["needs_review"] is False
