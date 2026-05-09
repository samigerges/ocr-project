from app.pipeline.receipt_layout import group_receipt_sections
from app.pipeline.receipt_items import parse_line_items_from_ocr_lines
from app.pipeline.receipt_extract import extract_receipt_from_layout
from app.pipeline.receipt_validate import validate_receipt
from app.pipeline.receipt_schema import ReceiptFields, ReceiptLineItem


def _line(index: int, text: str, y: int = 10, confidence: float = 0.94):
    return {
        "line_id": f"p0001_l{index:04d}",
        "page": 1,
        "text": text,
        "confidence": confidence,
        "bbox": [[10, y], [300, y], [300, y + 10], [10, y + 10]],
        "bounds": [10, y, 300, y + 10],
    }


def test_receipt_item_parser_groups_code_rows_and_continuations():
    lines = [
        _line(1, "Item Qty S/Price S/Price Amount Tax"),
        _line(2, "1072 1 80.00 80.00 80.00"),
        _line(3, "REPAIR ENGINE POWER SPRAYER (1UNIT)"),
        _line(4, "Workmanship & service"),
        _line(5, "Total Sales : 80.00"),
    ]

    items = parse_line_items_from_ocr_lines(lines)

    assert len(items) == 1
    assert items[0].item_code == "1072"
    assert items[0].description == "REPAIR ENGINE POWER SPRAYER (1UNIT) Workmanship & service"
    assert items[0].qty == 1
    assert items[0].unit_price == 80.00
    assert items[0].amount == 80.00
    assert items[0].source_line_ids == ["p0001_l0002", "p0001_l0003", "p0001_l0004"]


def test_receipt_layout_groups_metadata_items_and_totals():
    sections = group_receipt_sections(
        [
            _line(1, "SOON HUAT MACHINERY ENTERPRISE", y=5),
            _line(2, "Doc No. : CS00004040 Date: 11/01/2019", y=40),
            _line(3, "Item Qty S/Price Amount", y=80),
            _line(4, "1072 1 80.00 80.00", y=95),
            _line(5, "Total Sales : 80.00", y=150),
        ]
    )

    assert sections["header_company"]["lines"][0]["text"] == "SOON HUAT MACHINERY ENTERPRISE"
    assert sections["document_metadata"]["lines"][0]["line_id"] == "p0001_l0002"
    assert sections["items_table"]["lines"]
    assert sections["totals_payment"]["lines"][0]["text"] == "Total Sales : 80.00"


def test_receipt_validation_reconciles_totals_and_cash_change():
    receipt = ReceiptFields(
        merchant_name="SOON HUAT MACHINERY ENTERPRISE",
        document_number="CS00004040",
        date="2019-01-11",
        total=80.00,
        printed_total=80.00,
        final_total=80.00,
        cash_paid=100.00,
        change=20.00,
        line_items=[ReceiptLineItem(qty=1, unit_price=80.00, amount=80.00)],
    )

    report = validate_receipt(receipt)

    assert report.is_valid is True
    assert report.warnings == []
    assert report.checks["line_items_sum"] == 80.00
    assert report.checks["expected_change"] == 20.00


def test_extract_receipt_from_layout_persists_receipt_and_validation(tmp_path):
    lines = [
        _line(1, "SOON HUAT MACHINERY ENTERPRISE"),
        _line(2, "GST ID: 002116837376"),
        _line(3, "CASH SALES"),
        _line(4, "Doc No. : CS00004040 Date: 11/01/2019"),
        _line(5, "Cashier : USER Time: 09:44:00"),
        _line(6, "Item Qty S/Price S/Price Amount Tax"),
        _line(7, "1072 1 80.00 80.00 80.00"),
        _line(8, "REPAIR ENGINE POWER SPRAYER (1UNIT)"),
        _line(9, "Workmanship & service"),
        _line(10, "Total Sales : 80.00"),
        _line(11, "CASH : 80.00"),
        _line(12, "Change : 0.00"),
    ]

    receipt = extract_receipt_from_layout(
        "doc-1",
        {"lines": lines, "sections": group_receipt_sections(lines)},
        tmp_path / "extracted",
        tmp_path / "validation",
    )

    assert receipt.document_type == "cash_sales"
    assert receipt.document_number == "CS00004040"
    assert receipt.date == "2019-01-11"
    assert receipt.total == 80.00
    assert receipt.cash_paid == 80.00
    assert receipt.change == 0.00
    assert receipt.line_items[0].item_code == "1072"
    assert (tmp_path / "extracted" / "receipt.json").exists()
    assert (tmp_path / "validation" / "report.json").exists()
