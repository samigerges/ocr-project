from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from app.pipeline.invoice_schema import InvoiceFields, LineItem, empty_invoice_fields
from app.pipeline.invoice_validate import validate_invoice_fields

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "EGP", "AED", "SAR", "CAD", "AUD", "JPY", "CHF", "INR", "MYR"}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"

AMOUNT_TOKEN = r"(?:[$€£¥]\s*)?(?:[A-Z]{3}\s*)?-?\d{1,3}(?:[,.]\d{3})*(?:[,.]\d{2})?|(?:[$€£¥]\s*)?(?:[A-Z]{3}\s*)?-?\d+(?:[,.]\d{2})?"


def parse_amount(raw: str | None) -> float | None:
    """Safely parse common invoice amount formats without guessing arbitrary text."""
    if not raw:
        return None
    value = raw.strip()
    value = re.sub(r"\b(?:USD|EUR|GBP|EGP|AED|SAR|CAD|AUD|JPY|CHF|INR)\b", "", value, flags=re.I)
    value = re.sub(r"[$€£¥]", "", value).strip()
    value = value.replace(" ", "")
    value = re.sub(r"[^0-9,.-]", "", value)
    if not value or not re.search(r"\d", value):
        return None

    negative = value.startswith("-") or (value.startswith("(") and value.endswith(")"))
    value = value.strip("-()")

    if "," in value and "." in value:
        # Decide by the rightmost separator: 1,250.50 vs 1.250,50.
        if value.rfind(",") > value.rfind("."):
            normalized = value.replace(".", "").replace(",", ".")
        else:
            normalized = value.replace(",", "")
    elif "," in value:
        parts = value.split(",")
        if len(parts[-1]) == 2:
            normalized = "".join(parts[:-1]).replace(",", "") + "." + parts[-1]
        else:
            normalized = value.replace(",", "")
    elif "." in value:
        parts = value.split(".")
        if len(parts) > 2 and len(parts[-1]) == 2:
            normalized = "".join(parts[:-1]) + "." + parts[-1]
        elif len(parts) > 2:
            normalized = value.replace(".", "")
        elif len(parts[-1]) == 3 and len(parts[0]) <= 3:
            normalized = value.replace(".", "")
        else:
            normalized = value
    else:
        normalized = value

    try:
        amount = round(float(normalized), 2)
    except ValueError:
        return None
    return -amount if negative else amount


def parse_invoice_date(raw: str | None, *, prefer_day_first: bool = False) -> tuple[str | None, bool]:
    """Return an ISO date when safe; otherwise preserve ambiguous raw date."""
    if not raw:
        return None, False
    text = raw.strip().rstrip(".,")
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat(), False
        except ValueError:
            pass

    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", text)
    if match:
        first, second, year = match.groups()
        a, b = int(first), int(second)
        yyyy = int(year) + (2000 if len(year) == 2 else 0)
        if a > 12 and b <= 12:
            return datetime(yyyy, b, a).date().isoformat(), False
        if b > 12 and a <= 12:
            return datetime(yyyy, a, b).date().isoformat(), False
        if prefer_day_first:
            return datetime(yyyy, b, a).date().isoformat(), False
        return text, True
    return text, False


def extract_invoice_number(text: str) -> str | None:
    patterns = [
        r"\bInvoice\s*(?:No\.?|Number|#|ID)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
        r"\bInv\s*(?:No\.?|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
        r"\bBill\s*(?:No\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
        r"\bDoc(?:ument)?\s*(?:No\.?|Number|#)?\s*[:#-]?\s*([A-Z0-9][A-Z0-9._/-]{2,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip().rstrip(".,")
    return None


def _is_malaysian_receipt(text: str) -> bool:
    return bool(re.search(r"\b(RM|MYR|SDN\.?\s*BHD|JOHOR|KUALA\s+LUMPUR|GST\s*ID)\b", text, flags=re.I))


def _extract_labeled_date(text: str, labels: Iterable[str], *, prefer_day_first: bool = False) -> tuple[str | None, bool]:
    date_pattern = rf"(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}|(?:{MONTHS})\s+\d{{1,2}},\s*\d{{4}})"
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b(?:{label_pattern})\b[ \t]*[:#-]?[ \t]*{date_pattern}", text, flags=re.I)
    if not match:
        return None, False
    return parse_invoice_date(match.group(1), prefer_day_first=prefer_day_first)


def detect_currency(text: str) -> str:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    if re.search(r"\bRM\b|\(RM\)", text, flags=re.I):
        return "MYR"
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", text, flags=re.I):
            return code
    if _is_malaysian_receipt(text):
        return "MYR"
    return "unknown"


def _extract_labeled_amount(text: str, labels: Iterable[str]) -> float | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    matches = re.finditer(rf"\b(?:{label_pattern})\b[ \t]*[:#-]?[ \t]*({AMOUNT_TOKEN})", text, flags=re.I)
    amounts = [parse_amount(match.group(1)) for match in matches]
    amounts = [amount for amount in amounts if amount is not None]
    if not amounts:
        return None
    return amounts[-1]


def extract_total_amount(text: str) -> float | None:
    """Find the payable receipt total while ignoring cash/change and metadata totals."""
    priorities = [
        (re.compile(r"\b(round(?:ed)?\s+total|total\s+sales|grand\s+total|amount\s+due|invoice\s+total|total\s+amount)\b", re.I), 3),
        (re.compile(r"\btotal\b", re.I), 1),
    ]
    blocked = re.compile(r"\b(total\s+qty|change|cash|discount|subtotal|sub\s+total|tax|gst\s*id|rounding)\b", re.I)
    candidates: list[tuple[int, float]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or blocked.search(line):
            continue
        score = 0
        for pattern, priority in priorities:
            if pattern.search(line):
                score = max(score, priority)
        if not score:
            continue
        amounts = [parse_amount(amount) for amount in re.findall(AMOUNT_TOKEN, line)]
        amounts = [amount for amount in amounts if amount is not None]
        if amounts:
            candidates.append((score, amounts[-1]))

    if not candidates:
        return _extract_labeled_amount(text, ["Total Amount", "Amount Due", "Balance Due", "Grand Total", "Invoice Total", "Total"])

    best_score = max(score for score, _ in candidates)
    best_amounts = [amount for score, amount in candidates if score == best_score]
    non_zero = [amount for amount in best_amounts if amount != 0]
    return non_zero[-1] if non_zero else best_amounts[-1]


def _looks_like_company_name(line: str) -> bool:
    return bool(
        re.search(
            r"\b(SDN\.?\s*BHD|BHD|ENTERPRISE|TRADING|MACHINERY|BOOK|STORE|MART|RESTAURANT|SUPPLIES|LLC|LTD|INC|CO\.?|COMPANY)\b",
            line,
            flags=re.I,
        )
    )


def _has_company_suffix(line: str) -> bool:
    return bool(
        re.search(r"\b(SDN\.?\s*BHD|BHD|ENTERPRISE|LLC|LTD|INC|CO\.?|COMPANY)\b", line, flags=re.I)
    )


def _is_metadata_or_address(line: str) -> bool:
    return bool(
        re.search(
            r"\b(invoice|date|doc(?:ument)?\s*no|cash\s+(?:sales|bill)|bill to|ship to|total|receipt|tel|fax|gst\s*id|no\.?\s*\d|jalan|taman|johor|bahru|barcode)\b",
            line,
            flags=re.I,
        )
    )


def _extract_vendor_and_buyer(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    cleaned = [line.strip() for line in lines if line.strip()]
    vendor_name = None
    vendor_start = 0
    vendor_end = 0
    for idx, line in enumerate(cleaned[:10]):
        if _looks_like_company_name(line):
            vendor_start = idx
            vendor_end = idx
            vendor_parts = [line]
            if not _has_company_suffix(line):
                for next_offset, next_line in enumerate(cleaned[idx + 1 : idx + 3], start=idx + 1):
                    if _is_metadata_or_address(next_line):
                        break
                    candidate = " ".join(vendor_parts + [next_line])
                    if _looks_like_company_name(candidate) or re.fullmatch(r"[A-Z&(). -]{2,}", next_line):
                        vendor_end = next_offset
                        vendor_parts.append(next_line)
                        if _has_company_suffix(candidate):
                            break
            vendor_name = " ".join(vendor_parts)
            break
    if not vendor_name:
        for line in cleaned[:8]:
            if not _is_metadata_or_address(line):
                vendor_start = cleaned.index(line)
                vendor_end = vendor_start
                vendor_name = line
                break

    buyer_name = None
    for idx, line in enumerate(cleaned):
        if re.search(r"\b(?:bill to|billed to|customer|client|buyer)\b", line, re.I):
            trailing = re.sub(r".*?(?:bill to|billed to|customer|client|buyer)\s*[:#-]?\s*", "", line, flags=re.I).strip()
            if trailing and trailing.lower() != line.lower():
                buyer_name = trailing
            elif idx + 1 < len(cleaned):
                buyer_name = cleaned[idx + 1]
            break

    address_lines: list[str] = []
    if vendor_name:
        start = vendor_end + 1
        for line in cleaned[start : start + 4]:
            if re.search(r"invoice|bill to|date|total|subtotal", line, re.I):
                break
            if re.search(r"\d|street|st\.?|road|rd\.?|ave|avenue|city|egypt|usa|zip|jalan|taman|johor|bahru", line, re.I):
                address_lines.append(line)
    return vendor_name, "\n".join(address_lines) or None, buyer_name


def extract_line_items(text: str) -> list[LineItem]:
    """Parse simple invoice item rows after a table header without treating metadata as items."""
    items: list[LineItem] = []
    in_items = False
    header_pattern = re.compile(r"\b(description|item|service|product)\b.*\b(qty|quantity|unit|price|amount)\b", re.I)
    stop_pattern = re.compile(r"\b(subtotal|sub total|total|tax|discount|balance|amount due|payment)\b", re.I)
    metadata_pattern = re.compile(r"\b(invoice|date|due|bill to|ship to|customer|client|address)\b", re.I)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if header_pattern.search(line):
            in_items = True
            continue
        if stop_pattern.search(line):
            if in_items:
                break
            continue
        if not in_items or metadata_pattern.search(line):
            continue

        amounts = re.findall(AMOUNT_TOKEN, line)
        if not amounts:
            continue
        numeric_amounts = [parse_amount(amount) for amount in amounts]
        numeric_amounts = [amount for amount in numeric_amounts if amount is not None]
        if not numeric_amounts:
            continue

        amount = numeric_amounts[-1]
        quantity: float | int | None = None
        unit_price: float | None = numeric_amounts[-2] if len(numeric_amounts) >= 2 else None
        description = line
        row_match = re.match(r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+" + AMOUNT_TOKEN + r"\s+" + AMOUNT_TOKEN + r"$", line)
        if row_match:
            description = row_match.group(1).strip()
            quantity_value = parse_amount(row_match.group(2))
            quantity = int(quantity_value) if quantity_value is not None and quantity_value.is_integer() else quantity_value
        else:
            description = re.sub(re.escape(amounts[-1]) + r"\s*$", "", line).strip(" -|\t")
        if description and len(description) >= 3:
            items.append({"description": description, "quantity": quantity, "unit_price": unit_price, "amount": amount})
    return items[:100]


def extract_payment_method(text: str) -> str | None:
    patterns = [
        r"\bPayment Method\b\s*[:#-]?\s*(.+)",
        r"\bPaid by\b\s*[:#-]?\s*(.+)",
        r"\bPayment\b\s*[:#-]?\s*(cash|card|credit card|bank transfer|wire transfer|check|cheque)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(1).strip().rstrip(".,")[:80]
    return None


def extract_invoice_fields(text: str) -> InvoiceFields:
    fields = empty_invoice_fields()
    lines = text.splitlines()
    fields["invoice_number"] = extract_invoice_number(text)
    prefer_day_first = _is_malaysian_receipt(text)
    invoice_date, ambiguous_invoice = _extract_labeled_date(
        text, ["Invoice Date", "Date", "Issued", "Issue Date"], prefer_day_first=prefer_day_first
    )
    due_date, ambiguous_due = _extract_labeled_date(
        text, ["Due Date", "Payment Due", "Due"], prefer_day_first=prefer_day_first
    )
    fields["invoice_date"] = invoice_date
    fields["due_date"] = due_date
    fields["subtotal"] = _extract_labeled_amount(text, ["Subtotal", "Sub Total", "Net Amount"])
    fields["tax"] = _extract_labeled_amount(text, ["Tax", "VAT", "Sales Tax", "GST Amount"])
    fields["discount"] = _extract_labeled_amount(text, ["Discount"])
    fields["total_amount"] = extract_total_amount(text)
    fields["currency"] = detect_currency(text)
    fields["payment_method"] = extract_payment_method(text)
    fields["line_items"] = extract_line_items(text)
    vendor_name, vendor_address, buyer_name = _extract_vendor_and_buyer(lines)
    fields["vendor_name"] = vendor_name
    fields["vendor_address"] = vendor_address
    fields["buyer_name"] = buyer_name

    reasons = []
    if ambiguous_invoice or ambiguous_due:
        reasons.append("ambiguous_date_format")
    return validate_invoice_fields(fields, extra_review_reasons=reasons)


def extract_invoice_from_result(doc_id: str, result: dict, out_dir: Path) -> InvoiceFields:
    """Run invoice extraction after assemble and persist invoice_fields.json."""
    text = result.get("full_text", "") or ""
    fields = extract_invoice_fields(text)
    invoice_dir = out_dir.parent / "invoice"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    final_dir = out_dir
    final_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(fields)
    payload["doc_id"] = doc_id
    (invoice_dir / "invoice_fields.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (final_dir / "invoice_fields.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return fields
