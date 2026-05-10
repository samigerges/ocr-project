import csv
import json

import pytest

import evaluation.run_invoice_evaluation as invoice_evaluation


SUMMARY_JSON = "invoice_evaluation_summary.json"
SUMMARY_CSV = "invoice_evaluation_summary.csv"


def _read_summary_csv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return next(csv.DictReader(fh))


def test_invoice_evaluation_writes_summary_for_ground_truth_rows(tmp_path, monkeypatch):
    ground_truth = tmp_path / "ground_truth.csv"
    reports_dir = tmp_path / "reports"
    storage_dir = tmp_path / "storage"
    doc_dir = storage_dir / "doc-1" / "out"
    doc_dir.mkdir(parents=True)

    ground_truth.write_text(
        "doc_id,vendor_name,invoice_number,invoice_date,total_amount\n"
        "doc-1,Acme Supplies LLC,INV-1001,2026-05-09,105.00\n",
        encoding="utf-8",
    )
    (doc_dir / "invoice_fields.json").write_text(
        json.dumps(
            {
                "vendor_name": "Acme Supplies LLC",
                "invoice_number": "INV-1001",
                "invoice_date": "2026-05-09",
                "total_amount": 105.0,
                "needs_review": False,
                "confidence": 1.0,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(invoice_evaluation, "GROUND_TRUTH", ground_truth)
    monkeypatch.setattr(invoice_evaluation, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(invoice_evaluation, "STORAGE_DIR", storage_dir)

    invoice_evaluation.main()

    summary = json.loads((reports_dir / SUMMARY_JSON).read_text(encoding="utf-8"))
    assert summary["document_count"] == 1
    assert summary["vendor_name_accuracy"] == 1.0
    assert summary["invoice_number_accuracy"] == 1.0
    assert summary["invoice_date_accuracy"] == 1.0
    assert summary["total_amount_accuracy"] == 1.0

    csv_summary = _read_summary_csv(reports_dir / SUMMARY_CSV)
    assert csv_summary["document_count"] == "1"
    assert csv_summary["average_confidence"] == "1.0"


def test_invoice_evaluation_fails_clearly_when_non_empty_ground_truth_has_zero_documents(tmp_path, monkeypatch):
    ground_truth = tmp_path / "ground_truth.csv"
    reports_dir = tmp_path / "reports"
    storage_dir = tmp_path / "storage"
    ground_truth.write_text(
        "doc_id,vendor_name,invoice_number,invoice_date,total_amount\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(invoice_evaluation, "GROUND_TRUTH", ground_truth)
    monkeypatch.setattr(invoice_evaluation, "REPORTS_DIR", reports_dir)
    monkeypatch.setattr(invoice_evaluation, "STORAGE_DIR", storage_dir)

    with pytest.raises(SystemExit, match="processed 0 documents"):
        invoice_evaluation.main()

    summary = json.loads((reports_dir / SUMMARY_JSON).read_text(encoding="utf-8"))
    assert summary["document_count"] == 0

    csv_summary = _read_summary_csv(reports_dir / SUMMARY_CSV)
    assert csv_summary["document_count"] == "0"
