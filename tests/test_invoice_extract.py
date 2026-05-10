from app.pipeline.invoice_extract import (
    extract_invoice_fields,
    extract_invoice_fields_from_lines,
    extract_invoice_number,
    parse_amount,
    parse_invoice_date,
)


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
    assert fields["document_title"] == "CASH SALES"
    assert fields["vendor_name"] == "SOON HUAT MACHINERY ENTERPRISE"
    assert fields["vendor_registration_number"] == "JM0352019-K"
    assert (
        fields["vendor_address"]
        == "NO.53 JALAN PUTRA 1,\nTAMAN SRI PUTRA,\n81200 JOHOR BAHRU\nJOHOR"
    )
    assert fields["gst_id"] == "002116837376"
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
    assert fields["document_title"] == "CASH SALES"
    assert fields["vendor_registration_number"] == "JM0352019-K"
    assert fields["vendor_phone"] == "07-5547360 / 016-7993391"
    assert fields["vendor_fax"] == "07-5624059"
    assert fields["vendor_email"] == "SOONHUAT2000@HOTMAIL.COM"
    assert fields["gst_id"] == "002116837376"
    assert fields["cashier"] == "USER"
    assert fields["transaction_time"] == "09:44:00"
    assert fields["salesperson"] is None
    assert fields["reference"] is None
    assert fields["total_quantity"] == 9
    assert fields["cash_received"] == 327.00
    assert fields["change_amount"] == 0.00
    assert fields["rounding"] == 0.00
    assert len(fields["line_items"]) == 8
    assert fields["line_items"][0]["item_code"] == "1072"
    assert (
        fields["line_items"][0]["description"]
        == "REPAIR ENGINE POWER SPRAYER (1UNIT) workmanship & service"
    )
    assert fields["line_items"][-1]["quantity"] == 2
    assert fields["line_items"][-1]["amount"] == 36.00
    assert "line_items_total_mismatch" not in fields["review_reasons"]
    assert "line_items_quantity_mismatch" not in fields["review_reasons"]
    assert "cash_change_mismatch" not in fields["review_reasons"]


def test_extract_invoice_fields_with_ocr_confused_key_labels():
    text = """Example Trading LLC
Tax lnvoice No: OCR-7842
Inv0ice Date: 2026-04-30
Description Qty Unit Amount
Service fee 1 450.00 450.00
TotaI Am0unt: USD 450.00
"""
    fields = extract_invoice_fields(text)
    assert fields["invoice_number"] == "OCR-7842"
    assert fields["invoice_date"] == "2026-04-30"
    assert fields["total_amount"] == 450.00
    assert "missing_invoice_number" not in fields["review_reasons"]
    assert "missing_invoice_date" not in fields["review_reasons"]
    assert "missing_total_amount" not in fields["review_reasons"]


def test_extract_invoice_fields_with_reference_document_and_payable_aliases():
    text = """Acme Supplies LLC
Reference No: REF-2026-118
Document Date: 30/04/2026
Amount Payable: USD 1,275.50
"""
    fields = extract_invoice_fields(text)
    assert fields["invoice_number"] == "REF-2026-118"
    assert fields["invoice_date"] == "2026-04-30"
    assert fields["total_amount"] == 1275.50


def test_extract_invoice_fields_from_lines_uses_bbox_label_proximity_and_table_columns():
    lines = [
        {
            "text": "Acme Supplies LLC",
            "confidence": 0.99,
            "bbox": [[40, 30], [190, 30], [190, 50], [40, 50]],
            "page": 1,
            "line_id": "vendor",
        },
        {
            "text": "Invoice No",
            "confidence": 0.98,
            "bbox": [[40, 80], [130, 80], [130, 100], [40, 100]],
            "page": 1,
            "line_id": "inv-label",
        },
        {
            "text": "INV-LAYOUT-7",
            "confidence": 0.97,
            "bbox": [[170, 80], [290, 80], [290, 100], [170, 100]],
            "page": 1,
            "line_id": "inv-value",
        },
        {
            "text": "Invoice Date",
            "confidence": 0.98,
            "bbox": [[40, 115], [145, 115], [145, 135], [40, 135]],
            "page": 1,
            "line_id": "date-label",
        },
        {
            "text": "2026-05-09",
            "confidence": 0.97,
            "bbox": [[40, 145], [145, 145], [145, 165], [40, 165]],
            "page": 1,
            "line_id": "date-value",
        },
        {
            "text": "Description",
            "confidence": 0.99,
            "bbox": [[40, 220], [150, 220], [150, 240], [40, 240]],
            "page": 1,
            "line_id": "h-desc",
        },
        {
            "text": "Qty",
            "confidence": 0.99,
            "bbox": [[260, 220], [295, 220], [295, 240], [260, 240]],
            "page": 1,
            "line_id": "h-qty",
        },
        {
            "text": "Unit Price",
            "confidence": 0.99,
            "bbox": [[340, 220], [430, 220], [430, 240], [340, 240]],
            "page": 1,
            "line_id": "h-unit",
        },
        {
            "text": "Amount",
            "confidence": 0.99,
            "bbox": [[470, 220], [540, 220], [540, 240], [470, 240]],
            "page": 1,
            "line_id": "h-amount",
        },
        {
            "text": "Consulting",
            "confidence": 0.96,
            "bbox": [[40, 255], [140, 255], [140, 275], [40, 275]],
            "page": 1,
            "line_id": "r1-desc",
        },
        {
            "text": "2",
            "confidence": 0.96,
            "bbox": [[270, 255], [280, 255], [280, 275], [270, 275]],
            "page": 1,
            "line_id": "r1-qty",
        },
        {
            "text": "50.00",
            "confidence": 0.96,
            "bbox": [[355, 255], [410, 255], [410, 275], [355, 275]],
            "page": 1,
            "line_id": "r1-unit",
        },
        {
            "text": "100.00",
            "confidence": 0.96,
            "bbox": [[480, 255], [540, 255], [540, 275], [480, 275]],
            "page": 1,
            "line_id": "r1-amount",
        },
        {
            "text": "Total Amount",
            "confidence": 0.98,
            "bbox": [[330, 310], [445, 310], [445, 330], [330, 330]],
            "page": 1,
            "line_id": "total-label",
        },
        {
            "text": "USD 105.00",
            "confidence": 0.97,
            "bbox": [[470, 310], [560, 310], [560, 330], [470, 330]],
            "page": 1,
            "line_id": "total-value",
        },
    ]

    fields = extract_invoice_fields_from_lines(lines)

    assert fields["invoice_number"] == "INV-LAYOUT-7"
    assert fields["invoice_date"] == "2026-05-09"
    assert fields["total_amount"] == 105.00
    assert fields["line_items"] == [
        {
            "description": "Consulting",
            "quantity": 2,
            "unit_price": 50.00,
            "amount": 100.00,
        }
    ]
    assert "missing_invoice_number" not in fields["review_reasons"]
    assert "missing_invoice_date" not in fields["review_reasons"]
    assert "missing_total_amount" not in fields["review_reasons"]


def test_extract_malaysian_cash_sales_from_glued_ocr_layout_lines():
    def line(index, text, y):
        return {
            "text": text,
            "text_clean": text,
            "confidence": 0.98,
            "page": 1,
            "line_id": f"p0001_l{index:04d}",
            "bbox": [
                [80.0, float(y)],
                [1600.0, float(y)],
                [1600.0, float(y + 80)],
                [80.0, float(y + 80)],
            ],
        }

    lines = [
        line(1, "tan chay yee", 173),
        line(2, "SOON HUAT MACHINERY ENTERPRISE", 445),
        line(3, "JM0352019-K", 528),
        line(4, "NO.53JALAN PUTRA 1", 624),
        line(5, "TAMAN SRIPUTRA,", 730),
        line(6, "81200 JOHOR BAHRU", 818),
        line(7, "JOHOR", 909),
        line(8, "TEL07-5547360/016-7993391FAX07-5624059", 1006),
        line(9, "SOONHUAT2000@HOTMAIL.COM", 1103),
        line(10, "GSTID002116837376", 1200),
        line(11, "CASH SALES", 1311),
        line(12, "Date11/01/2019 Doc No. CS00004040", 1417),
        line(17, "Time09:44:00 Cashier", 1519),
        line(19, "Ret. Salesperson", 1621),
        line(23, "Amount Tax Qty S/Price S/Price Item", 1795),
        line(26, "80.00", 1882),
        line(28, "80.00 1 80.00 1072", 1882),
        line(30, "REPAIR ENGINE POWER SPRAYER (1UNIT)", 1983),
        line(31, "workmanship &service", 2090),
        line(33, "160.00 160.00 160.00 70549", 2158),
        line(36, "GIANT 606 OVERFLOW ASSY", 2269),
        line(39, "17.00 17.00", 2370),
        line(41, "17.00 1071 1", 2370),
        line(42, "ENGINE OIL", 2467),
        line(43, "10.00 10.00 10.00 70791 1", 2564),
        line(48, "GREASE FOR TOOLS40ML (AKODA", 2665),
        line(50, "6.00 6.00 6.00 1 70637", 2762),
        line(54, "EY20PLUG CHAMPION", 2873),
        line(58, "8.00 1 8.00 8.00 1643", 2970),
        line(60, "STARTER TALI", 3077),
        line(62, "10.00 10.00 10.00 70197", 3164),
        line(65, "EY20 STARTER HANDLE", 3265),
        line(67, "36.00 2 70561 18.00 18.00", 3367),
        line(71, "HD40 1LCOTIN", 3478),
        line(74, "327.00 9 Total Qty", 3554),
        line(75, "Total Sales 327.00", 3720),
        line(77, "Discount 0.00 327.00 Total 0.00", 3836),
        line(82, "Rounding 0.00", 4057),
        line(84, "Total Sales 327.00", 4184),
        line(86, "CASH 327.00", 4295),
        line(88, "Change: 0.00", 4392),
    ]

    fields = extract_invoice_fields_from_lines(lines)

    assert fields["vendor_name"] == "SOON HUAT MACHINERY ENTERPRISE"
    assert fields["vendor_registration_number"] == "JM0352019-K"
    assert fields["vendor_phone"] == "07-5547360/016-7993391"
    assert fields["vendor_fax"] == "07-5624059"
    assert fields["gst_id"] == "002116837376"
    assert fields["invoice_number"] == "CS00004040"
    assert fields["invoice_date"] == "2019-01-11"
    assert fields["transaction_time"] == "09:44:00"
    assert fields["total_amount"] == 327.00
    assert fields["total_quantity"] == 9
    assert fields["cash_received"] == 327.00
    assert fields["change_amount"] == 0.00
    assert len(fields["line_items"]) == 8
    assert fields["line_items"][0]["item_code"] == "1072"
    assert (
        fields["line_items"][0]["description"]
        == "REPAIR ENGINE POWER SPRAYER (1UNIT) workmanship &service"
    )
    assert fields["line_items"][-1]["quantity"] == 2
    assert fields["line_items"][-1]["amount"] == 36.00
    assert "cash_change_mismatch" not in fields["review_reasons"]
    assert "missing_invoice_date" not in fields["review_reasons"]


def test_extract_ocr_glued_cash_bill_fields_from_layout_lines():
    def line(index: int, text: str, y: int, left: int = 100, right: int = 1800):
        return {
            "text": text,
            "text_clean": text,
            "confidence": 0.98,
            "page": 1,
            "line_id": f"p0001_l{index:04d}",
            "bbox": [
                [float(left), float(y)],
                [float(right), float(y)],
                [float(right), float(y + 70)],
                [float(left), float(y + 70)],
            ],
        }

    lines = [
        line(1, "tan woon yann", 132, 308, 1263),
        line(2, "BOOK TA KTAMANDAYASDN BHD", 381, 299, 1647),
        line(3, "789417-W", 484, 824, 1131),
        line(4, "NO.555S7&59JALANSAGU18", 580, 451, 1500),
        line(5, "TAMAN DAYA,", 671, 762, 1184),
        line(6, "81100 JOHOR BAHRU", 757, 644, 1320),
        line(7, "JOHOR.", 849, 857, 1090),
        line(8, "DocumentNoTD01167104", 1341, 209, 1102),
        line(9, "Date", 1457, 205, 406),
        line(10, "25/12/2018813:39PM", 1457, 652, 1352),
        line(12, "MANIS Cashiery", 1548, 205, 865),
        line(14, "CASH BILL", 1792, 762, 1180),
        line(15, "CODE/DESC", 1979, 131, 500),
        line(16, "PRICE Disc", 1979, 791, 1221),
        line(18, "AMOUNT", 1979, 1467, 1742),
        line(20, "RM RM QTY", 2059, 279, 1765),
        line(23, "KF MODELLING CLAY KIDDYFISH 9556939040118", 2219, 123, 1566),
        line(27, "9.00 9.000 0.00 1PC", 2316, 285, 1754),
        line(29, "9.00 Total':", 2492, 955, 1758),
        line(31, "0.00 Rour Jing Adjustment", 2612, 475, 1754),
        line(32, "Roundd Total RM", 2745, 357, 1156),
        line(33, "9.00", 2745, 1570, 1754),
        line(34, "Cash", 2910, 803, 975),
        line(35, "10.00", 2923, 1574, 1750),
        line(37, "100 CHANGE", 2994, 807, 1757),
    ]

    fields = extract_invoice_fields_from_lines(lines)

    assert fields["vendor_registration_number"] == "789417-W"
    assert (
        fields["vendor_address"]
        == "NO.555S7&59JALANSAGU18\nTAMAN DAYA,\n81100 JOHOR BAHRU\nJOHOR."
    )
    assert fields["invoice_number"] == "TD01167104"
    assert fields["invoice_date"] == "2018-12-25"
    assert fields["transaction_time"] == "8:13:39PM"
    assert fields["cashier"] == "MANIS"
    assert fields["total_amount"] == 9.00
    assert fields["cash_received"] == 10.00
    assert fields["change_amount"] == 1.00
    assert fields["line_items"] == [
        {
            "item_code": "9556939040118",
            "description": "KF MODELLING CLAY KIDDYFISH",
            "quantity": 1,
            "unit_price": 9.00,
            "amount": 9.00,
        }
    ]
    assert "line_items_total_mismatch" not in fields["review_reasons"]
