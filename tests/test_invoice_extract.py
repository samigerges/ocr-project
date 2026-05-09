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


def test_extract_malaysian_cash_sales_receipt_fields():
    text = """tan chay yee
SOON HUAT MACHINERY ENTERPRISE
(JM0352019-K)
NO.53 JALAN PUTRA 1,
TAMAN SRI PUTRA,
81200 JOHOR BAHRU
JOHOR
TEL: 07-5547360 / 016-7993391 FAX: 07-5624059
GST ID: 002116837376
CASH SALES
Doc No. : CS00004040 Date: 11/01/2019
Cashier : USER Time: 09:44:00
Item Qty S/Price S/Price Amount Tax
1072 1 80.00 80.00 80.00
REPAIR ENGINE POWER SPRAYER (1UNIT)
Total Qty: 9 327.00
Total Sales : 327.00
Discount : 0.00
Total : 0.00
Rounding : 0.00
Total Sales : 327.00
CASH : 327.00
Change : 0.00
"""
    fields = extract_invoice_fields(text)
    assert fields["vendor_name"] == "SOON HUAT MACHINERY ENTERPRISE"
    assert fields["invoice_number"] == "CS00004040"
    assert fields["invoice_date"] == "2019-01-11"
    assert fields["total_amount"] == 327.00
    assert fields["currency"] == "MYR"
    assert fields["tax"] is None
    assert "missing_invoice_number" not in fields["review_reasons"]
    assert "missing_invoice_date" not in fields["review_reasons"]
    assert "missing_total_amount" not in fields["review_reasons"]


def test_extract_malaysian_cash_bill_receipt_fields():
    text = """tan woon yann
BOOK TA -K (TAMAN DAYA) SDN BHD
739117-W
NO.5; 55,57 & 59, JALAN SAGU 18,
TAMAN DAYA,
81100 JOHOR BAHRU,
JOHOR.
Document No : TD01167104
Date : 25/12/2018 8:13:39 PM
Cashier : MANIS
CASH BILL
CODE/DESC PRICE Disc AMOUNT
QTY RM RM
9556939040116 XF MODELLING CLAY KIDDY FISH
1 PC 9.00 0.00 9.00
Total: 9.00
Rounding Adjustment: 0.00
Rounded Total (RM): 9.00
Cash 10.00
CHANGE 1.00
"""
    fields = extract_invoice_fields(text)
    assert fields["vendor_name"] == "BOOK TA -K (TAMAN DAYA) SDN BHD"
    assert fields["invoice_number"] == "TD01167104"
    assert fields["invoice_date"] == "2018-12-25"
    assert fields["total_amount"] == 9.00
    assert fields["currency"] == "MYR"
    assert "missing_total_amount" not in fields["review_reasons"]


def test_extract_thermal_cash_sales_receipt_line_items_and_cash_totals():
    text = """tan chay yee
SOON HUAT MACHINERY ENTERPRISE
(JM0352019-K)
NO.53 JALAN PUTRA 1,
TAMAN SRI PUTRA,
81200 JOHOR BAHRU
JOHOR
TEL: 07-5547360 / 016-7993391 FAX: 07-5624059
SOONHUAT2000@HOTMAIL.COM
GST ID: 002116837376
CASH SALES
Doc No. : CS00004040 Date: 11/01/2019
Cashier : USER Time: 09:44:00
Salesperson : Ref.:
Item Qty S/Price S/Price Amount Tax
1072 1 80.00 80.00 80.00
REPAIR ENGINE POWER SPRAYER (1UNIT)
workmanship & service
70549 1 160.00 160.00 160.00
GIANT 606 OVERFLOW ASSY
1071 1 17.00 17.00 17.00
ENGINE OIL
70791 1 10.00 10.00 10.00
GREASE FOR TOOLS 40ML (AKODA)
70637 1 6.00 6.00 6.00
EY20 PLUG CHAMPION
1643 1 8.00 8.00 8.00
STARTER TALI
70197 1 10.00 10.00 10.00
EY20 STARTER HANDLE
70561 2 18.00 18.00 36.00
HD40 1L COTIN
Total Qty: 9 327.00
Total Sales : 327.00
Discount : 0.00
Total : 0.00
Rounding : 0.00
Total Sales : 327.00
CASH : 327.00
Change : 0.00
"""
    fields = extract_invoice_fields(text)
    assert fields["document_type"] == "cash_sales_receipt"
    assert fields["total_quantity"] == 9
    assert fields["cash_received"] == 327.00
    assert fields["change_amount"] == 0.00
    assert len(fields["line_items"]) == 8
    assert fields["line_items"][0]["item_code"] == "1072"
    assert fields["line_items"][0]["description"] == "REPAIR ENGINE POWER SPRAYER (1UNIT) workmanship & service"
    assert fields["line_items"][-1]["quantity"] == 2
    assert fields["line_items"][-1]["amount"] == 36.00
    assert "line_items_total_mismatch" not in fields["review_reasons"]
    assert "line_items_quantity_mismatch" not in fields["review_reasons"]
    assert "cash_change_mismatch" not in fields["review_reasons"]
