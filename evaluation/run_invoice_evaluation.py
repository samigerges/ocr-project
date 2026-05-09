from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipeline.invoice_metrics import summarize_invoice_evaluation

GROUND_TRUTH = Path(__file__).resolve().parent / "ground_truth.csv"
REPORTS_DIR = Path(__file__).resolve().parent / "reports"
STORAGE_DIR = ROOT / "storage"


def _normalize(value: object) -> str:
    return str(value or "").strip().casefold()


def _amount_equal(expected: str, actual: object) -> bool:
    if expected == "" and actual in (None, ""):
        return True
    try:
        return abs(float(expected) - float(actual)) <= 0.02
    except (TypeError, ValueError):
        return False


def _load_invoice_fields(doc_id: str) -> dict:
    candidates = [
        STORAGE_DIR / doc_id / "out" / "invoice_fields.json",
        STORAGE_DIR / doc_id / "invoice" / "invoice_fields.json",
    ]
    for path in candidates:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    return {}


def main() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    with GROUND_TRUTH.open(newline="", encoding="utf-8") as fh:
        for expected in csv.DictReader(fh):
            extracted = _load_invoice_fields(expected["doc_id"])
            rows.append(
                {
                    "doc_id": expected["doc_id"],
                    "invoice_number_match": _normalize(expected.get("invoice_number")) == _normalize(extracted.get("invoice_number")),
                    "invoice_date_match": _normalize(expected.get("invoice_date")) == _normalize(extracted.get("invoice_date")),
                    "total_amount_match": _amount_equal(expected.get("total_amount", ""), extracted.get("total_amount")),
                    "vendor_name_match": _normalize(expected.get("vendor_name")) == _normalize(extracted.get("vendor_name")),
                    "needs_review": bool(extracted.get("needs_review")),
                    "confidence": float(extracted.get("confidence") or 0.0),
                }
            )

    summary = summarize_invoice_evaluation(rows).to_dict()
    (REPORTS_DIR / "invoice_evaluation_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (REPORTS_DIR / "invoice_evaluation_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
