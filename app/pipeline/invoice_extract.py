from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.pipeline.invoice_schema import InvoiceFields, LineItem, empty_invoice_fields
from app.pipeline.invoice_validate import validate_invoice_fields

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = {
    "USD",
    "EUR",
    "GBP",
    "EGP",
    "AED",
    "SAR",
    "CAD",
    "AUD",
    "JPY",
    "CHF",
    "INR",
    "MYR",
}
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"

AMOUNT_TOKEN = r"(?:[$€£¥]\s*)?(?:[A-Z]{3}\s*)?-?\d{1,3}(?:[,.]\d{3})*(?:[,.]\d{2})?|(?:[$€£¥]\s*)?(?:[A-Z]{3}\s*)?-?\d+(?:[,.]\d{2})?"

INVOICE_NUMBER_LABEL_ALIASES = (
    "Invoice No",
    "Invoice Number",
    "Tax Invoice No",
    "Inv No",
    "Ref No",
    "Reference No",
    "Document No",
    # Legacy receipt shorthand retained for existing cash-sale documents.
    "Doc No",
)
INVOICE_DATE_LABEL_ALIASES = (
    "Invoice Date",
    "Inv Date",
    "Date Issued",
    "Issue Date",
    "Document Date",
    # Short receipt labels retained for documents that do not print an invoice-specific date label.
    "Date",
    "Issued",
)
TOTAL_AMOUNT_LABEL_ALIASES = (
    "Total Amount",
    "Amount Due",
    "Amount Payable",
    "Balance Due",
    "Net Total",
    "Grand Total",
    "Rounded Total",
    # Existing aliases used by receipt and invoice fixtures.
    "Invoice Total",
    "Total Sales",
    "Total",
)

OCR_CONFUSABLES = {
    "i": "[iIl1]",
    "I": "[iIl1]",
    "l": "[lLI1]",
    "L": "[lLI1]",
    "o": "[oO0]",
    "O": "[oO0]",
}


def _label_to_regex(label: str) -> str:
    """Build an OCR-tolerant regex for configured field labels."""
    parts: list[str] = []
    for char in label:
        if char.isspace():
            parts.append(r"\s*")
        elif char == ".":
            parts.append(r"\.?")
        else:
            parts.append(OCR_CONFUSABLES.get(char, re.escape(char)))
    return "".join(parts)


def _label_pattern(labels: Iterable[str]) -> str:
    return "|".join(
        _label_to_regex(label) for label in sorted(labels, key=len, reverse=True)
    )


def _label_prefix_pattern(labels: Iterable[str]) -> str:
    """Return an OCR-tolerant label pattern that may be glued to its value."""
    return rf"(?<!\w)(?:{_label_pattern(labels)})\.?[ \t]*[:#-]?[ \t]*"


def parse_amount(raw: str | None) -> float | None:
    """Safely parse common invoice amount formats without guessing arbitrary text."""
    if not raw:
        return None
    value = raw.strip()
    value = re.sub(
        r"\b(?:USD|EUR|GBP|EGP|AED|SAR|CAD|AUD|JPY|CHF|INR)\b", "", value, flags=re.I
    )
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


def parse_invoice_date(
    raw: str | None, *, prefer_day_first: bool = False
) -> tuple[str | None, bool]:
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
    value_pattern = r"([A-Z0-9][A-Z0-9._/-]{2,})"
    for line in text.splitlines():
        match = re.search(
            rf"{_label_prefix_pattern(INVOICE_NUMBER_LABEL_ALIASES)}{value_pattern}",
            line.strip(),
            flags=re.I,
        )
        if match:
            return match.group(1).strip().rstrip(".,")
    return None


def _is_malaysian_receipt(text: str) -> bool:
    return bool(
        re.search(
            r"\b(RM|MYR|SDN\.?\s*BHD|JOHOR|KUALA\s+LUMPUR)\b|(?<!\w)GST\s*ID",
            text,
            flags=re.I,
        )
    )


def _extract_labeled_date(
    text: str, labels: Iterable[str], *, prefer_day_first: bool = False
) -> tuple[str | None, bool]:
    date_pattern = rf"(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}|(?:{MONTHS})\s+\d{{1,2}},\s*\d{{4}})"
    match = re.search(
        rf"{_label_prefix_pattern(labels)}{date_pattern}", text, flags=re.I
    )
    if not match:
        return None, False
    return parse_invoice_date(match.group(1), prefer_day_first=prefer_day_first)


def _extract_labeled_text(
    text: str, labels: Iterable[str], *, max_length: int = 120
) -> str | None:
    """Extract short single-line metadata values such as cashier, GST ID, and references."""
    for line in text.splitlines():
        match = re.search(
            rf"{_label_prefix_pattern(labels)}(.+)", line.strip(), flags=re.I
        )
        if match:
            value = match.group(1).strip().strip("|;,")
            if value:
                return value[:max_length]
    return None


def _extract_inline_labeled_text(
    text: str, label: str, *, stop_labels: Iterable[str] = (), max_length: int = 120
) -> str | None:
    """Extract metadata that can appear beside another label on the same receipt line."""
    stop_pattern = "|".join(
        re.escape(stop_label).rstrip(r"\.") + r"\.?" for stop_label in stop_labels
    )
    suffix = rf"(?=\s*(?:{stop_pattern})\s*[:#-]?|$)" if stop_pattern else r"$"
    label_pattern = re.escape(label).rstrip(r"\.") + r"\.?"
    for line in text.splitlines():
        match = re.search(
            rf"(?<!\w){label_pattern}\s*[:#-]?\s*(.*?){suffix}",
            line.strip(),
            flags=re.I,
        )
        if match:
            value = " ".join(match.group(1).split()).strip().strip("|;,")
            if value:
                return value[:max_length]
    return None


def extract_document_title(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip()
        if re.fullmatch(
            r"CASH\s+(?:SALES|BILL)|(?:TAX\s+)?INVOICE|RECEIPT", cleaned, flags=re.I
        ):
            return cleaned.upper()
    return None


def extract_vendor_registration_number(text: str) -> str | None:
    for line in text.splitlines():
        cleaned = line.strip()
        if re.fullmatch(r"\(?[A-Z]{1,4}\d{4,}[A-Z0-9-]*\)?", cleaned, flags=re.I):
            return cleaned.strip("()")
    return None


def extract_gst_id(text: str) -> str | None:
    return _extract_labeled_text(text, ["GST ID", "GST No", "GSTIN"], max_length=60)


def extract_contact_details(text: str) -> tuple[str | None, str | None, str | None]:
    phone = None
    fax = None
    email = None
    email_match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, flags=re.I)
    if email_match:
        email = email_match.group(0)

    for line in text.splitlines():
        cleaned = line.strip()
        if not phone:
            tel_match = re.search(
                r"(?<!\w)(?:TEL|PHONE)\.?\s*[:#-]?\s*(.*?)(?=\s*FAX\.?\s*[:#-]?|$)",
                cleaned,
                flags=re.I,
            )
            if tel_match:
                phone = tel_match.group(1).strip().strip("|;,") or None
        if not fax:
            fax_match = re.search(r"FAX\.?\s*[:#-]?\s*(.+)", cleaned, flags=re.I)
            if fax_match:
                fax = fax_match.group(1).strip().strip("|;,") or None
    return phone, fax, email


def extract_transaction_time(text: str) -> str | None:
    match = re.search(
        r"(?<!\w)Time\.?\s*[:#-]?\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?)",
        text,
        flags=re.I,
    )
    return match.group(1).strip() if match else None


def extract_cashier(text: str) -> str | None:
    return _extract_inline_labeled_text(
        text,
        "Cashier",
        stop_labels=["Time", "Date", "Salesperson", "Ref.", "Ref"],
        max_length=80,
    )


def extract_salesperson(text: str) -> str | None:
    return _extract_inline_labeled_text(
        text, "Salesperson", stop_labels=["Ref.", "Ref", "Time", "Date"], max_length=80
    )


def extract_reference(text: str) -> str | None:
    return _extract_inline_labeled_text(
        text, "Ref.", stop_labels=["Time", "Date"], max_length=80
    ) or _extract_inline_labeled_text(
        text, "Ref", stop_labels=["Time", "Date"], max_length=80
    )


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
    label_pattern = _label_pattern(labels)
    matches = re.finditer(
        rf"\b(?:{label_pattern})\b\.?[ \t]*[:#-]?[ \t]*({AMOUNT_TOKEN})",
        text,
        flags=re.I,
    )
    amounts = [parse_amount(match.group(1)) for match in matches]
    amounts = [amount for amount in amounts if amount is not None]
    if not amounts:
        return None
    return amounts[-1]


def extract_total_amount(text: str) -> float | None:
    """Find the payable receipt total while ignoring cash/change and metadata totals."""
    high_priority_total_labels = [
        label for label in TOTAL_AMOUNT_LABEL_ALIASES if label != "Total"
    ]
    high_priority_total_pattern = _label_pattern(high_priority_total_labels)
    generic_total_pattern = _label_pattern(["Total"])
    priorities = [
        (re.compile(rf"\b(?:{high_priority_total_pattern})\b", re.I), 3),
        (re.compile(rf"\b(?:{generic_total_pattern})\b", re.I), 1),
    ]
    blocked = re.compile(
        r"\b(total\s+qty|change|cash|discount|subtotal|sub\s+total|tax|gst\s*id|rounding)\b",
        re.I,
    )
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
        return _extract_labeled_amount(text, TOTAL_AMOUNT_LABEL_ALIASES)

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
        re.search(
            r"\b(SDN\.?\s*BHD|BHD|ENTERPRISE|LLC|LTD|INC|CO\.?|COMPANY)\b",
            line,
            flags=re.I,
        )
    )


def _is_metadata_or_address(line: str) -> bool:
    return bool(
        re.search(
            r"\b(invoice|date|doc(?:ument)?\s*no|cash\s+(?:sales|bill)|bill to|ship to|total|receipt|tel|fax|gst\s*id|no\.?\s*\d|jalan|taman|johor|bahru|barcode)\b",
            line,
            flags=re.I,
        )
    )


def _extract_vendor_and_buyer(
    lines: list[str],
) -> tuple[str | None, str | None, str | None]:
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
                for next_offset, next_line in enumerate(
                    cleaned[idx + 1 : idx + 3], start=idx + 1
                ):
                    if _is_metadata_or_address(next_line):
                        break
                    candidate = " ".join(vendor_parts + [next_line])
                    if _looks_like_company_name(candidate) or re.fullmatch(
                        r"[A-Z&(). -]{2,}", next_line
                    ):
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
            trailing = re.sub(
                r".*?(?:bill to|billed to|customer|client|buyer)\s*[:#-]?\s*",
                "",
                line,
                flags=re.I,
            ).strip()
            if trailing and trailing.lower() != line.lower():
                buyer_name = trailing
            elif idx + 1 < len(cleaned):
                buyer_name = cleaned[idx + 1]
            break

    address_lines: list[str] = []
    if vendor_name:
        start = vendor_end + 1
        for line in cleaned[start : start + 6]:
            if re.search(
                r"invoice|bill to|date|total|subtotal|cash\s+(?:sales|bill)|tel|fax|gst\s*id|@",
                line,
                re.I,
            ):
                break
            if extract_vendor_registration_number(line):
                continue
            if re.search(
                r"\d|street|st\.?|road|rd\.?|ave|avenue|city|egypt|usa|zip|jalan|taman|johor|bahru",
                line,
                re.I,
            ):
                address_lines.append(line)
    return vendor_name, "\n".join(address_lines) or None, buyer_name


def _normalize_quantity(value: float | None) -> float | int | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def _parse_receipt_code_row(line: str) -> LineItem | None:
    """Parse receipt item rows even when OCR column order is reversed or shifted."""
    parts = line.split()
    code_indexes = [
        index for index, part in enumerate(parts) if re.fullmatch(r"\d{3,}", part)
    ]
    if not code_indexes or len(code_indexes) > 1:
        return None

    for code_index in code_indexes:
        code = parts[code_index]
        before = [parse_amount(part) for part in parts[:code_index]]
        after = [parse_amount(part) for part in parts[code_index + 1 :]]
        before = [value for value in before if value is not None]
        after = [value for value in after if value is not None]
        quantity: float | int | None = None
        unit_price: float | None = None
        amount: float | None = None

        if code_index == 0 and len(after) >= 3:
            quantity = _normalize_quantity(after[0])
            unit_price = after[1]
            amount = after[-1]
        elif before and after:
            amount = before[0]
            if len(before) >= 3 and len(after) == 1:
                # Example OCR order: "10.00 10.00 10.00 70791 1".
                quantity = _normalize_quantity(after[0])
                unit_price = before[-1]
            elif len(before) >= 2:
                # Example OCR order: "36.00 2 70561 18.00 18.00".
                quantity = _normalize_quantity(before[1])
                unit_price = after[0]
            else:
                # Example OCR order: "17.00 1071 1".
                quantity = _normalize_quantity(after[0])
                unit_price = amount
        elif len(before) >= 3:
            amount = before[0]
            if len(before) >= 4:
                # Example OCR order: "6.00 6.00 6.00 1 70637".
                quantity = _normalize_quantity(before[-1])
                unit_price = before[-2]
            elif before[0] == before[1] == before[2]:
                # Example OCR order with omitted quantity: "160.00 160.00 160.00 70549".
                quantity = 1
                unit_price = before[-1]
            elif float(before[1]).is_integer() and before[1] <= 999:
                # Example OCR order: "80.00 1 80.00 1072".
                quantity = _normalize_quantity(before[1])
                unit_price = before[2]
            else:
                quantity = 1
                unit_price = before[-1]
        elif len(before) >= 2:
            # Example OCR order: "17.00 1071 1" has the code in the middle.
            amount = before[0]
            quantity = _normalize_quantity(before[1]) if len(before) > 1 else 1
            unit_price = amount

        if amount is None or unit_price is None:
            continue
        if quantity is None:
            quantity = 1
        return {
            "item_code": code,
            "description": code,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
        }
    return None


def _finalize_receipt_item(items: list[LineItem], pending: LineItem | None) -> None:
    if not pending:
        return
    description = (pending.get("description") or pending.get("item_code") or "").strip()
    if len(description) < 3:
        return
    pending["description"] = description
    items.append(pending)


def extract_line_items(text: str) -> list[LineItem]:
    """Parse invoice/receipt table rows and group receipt code rows with following descriptions."""
    items: list[LineItem] = []
    in_items = False
    pending_receipt_item: LineItem | None = None
    header_pattern = re.compile(
        r"(?=.*\b(description|code/?desc|item|service|product)\b)(?=.*\b(qty|quantity|unit|price|amount|s/price)\b)",
        re.I,
    )
    stop_pattern = re.compile(
        r"\b(subtotal|sub total|total\s+qty|total\s+sales|grand\s+total|total|tax|discount|"
        r"balance|amount due|payment|cash|change|rounding)\b",
        re.I,
    )
    metadata_pattern = re.compile(
        r"\b(invoice|date|due|bill to|ship to|customer|client|address|cashier|salesperson|"
        r"ref\.?|tel|fax|gst\s*id)\b",
        re.I,
    )
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if header_pattern.search(line):
            in_items = True
            continue
        if stop_pattern.search(line):
            if in_items:
                _finalize_receipt_item(items, pending_receipt_item)
                pending_receipt_item = None
                break
            continue
        if not in_items or metadata_pattern.search(line):
            continue

        receipt_item = _parse_receipt_code_row(line)
        if receipt_item:
            _finalize_receipt_item(items, pending_receipt_item)
            pending_receipt_item = receipt_item
            continue
        if len(re.findall(r"\b\d{3,}\b", line)) > 1:
            continue

        if pending_receipt_item:
            line_amounts = [
                parse_amount(amount) for amount in re.findall(AMOUNT_TOKEN, line)
            ]
            line_amounts = [amount for amount in line_amounts if amount is not None]
            last_token_is_amount = (
                parse_amount(line.split()[-1]) is not None if line.split() else False
            )
            looks_like_amount_row = (
                len(line_amounts) >= 2
                and last_token_is_amount
                and not re.search(r"[A-Z]{2,}", line, re.I)
            )
            if not looks_like_amount_row:
                previous_description = pending_receipt_item.get("description") or ""
                if previous_description == pending_receipt_item.get("item_code"):
                    pending_receipt_item["description"] = line
                else:
                    pending_receipt_item["description"] = (
                        f"{previous_description} {line}".strip()
                    )
                continue

        amounts = re.findall(AMOUNT_TOKEN, line)
        if not amounts:
            continue
        if re.fullmatch(r"[\d.,\s$€£¥A-Z-]+", line) and not re.search(
            r"[A-Z]{2,}", line
        ):
            continue
        numeric_amounts = [parse_amount(amount) for amount in amounts]
        numeric_amounts = [amount for amount in numeric_amounts if amount is not None]
        if not numeric_amounts:
            continue

        amount = numeric_amounts[-1]
        quantity: float | int | None = None
        unit_price: float | None = (
            numeric_amounts[-2] if len(numeric_amounts) >= 2 else None
        )
        description = line
        row_match = re.match(
            r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+"
            + AMOUNT_TOKEN
            + r"\s+"
            + AMOUNT_TOKEN
            + r"$",
            line,
        )
        if row_match and row_match.group(1):
            description = row_match.group(1).strip()
            quantity = _normalize_quantity(parse_amount(row_match.group(2)))
        else:
            description = re.sub(re.escape(amounts[-1]) + r"\s*$", "", line).strip(
                " -|\t"
            )
        if description and len(description) >= 3:
            items.append(
                {
                    "description": description,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "amount": amount,
                }
            )

    _finalize_receipt_item(items, pending_receipt_item)
    return items[:100]


def detect_document_type(text: str) -> str:
    if re.search(r"\bCASH\s+(SALES|BILL)\b|\bRECEIPT\b", text, flags=re.I):
        return "cash_sales_receipt"
    return "invoice"


def extract_total_quantity(text: str) -> float | int | None:
    match = re.search(r"\bTotal\s+Qty\b\s*[:#-]?\s*(\d+(?:[.,]\d+)?)", text, flags=re.I)
    if match:
        return _normalize_quantity(parse_amount(match.group(1)))
    reversed_match = re.search(
        rf"({AMOUNT_TOKEN})\s+(\d+(?:[.,]\d+)?)\s+Total\s+Qty\b", text, flags=re.I
    )
    if reversed_match:
        return _normalize_quantity(parse_amount(reversed_match.group(2)))
    return None


def extract_cash_received(text: str) -> float | None:
    return _extract_labeled_amount(text, ["Cash", "Cash Received", "Tendered"])


def extract_change_amount(text: str) -> float | None:
    return _extract_labeled_amount(text, ["Change", "Balance Change"])


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


def _line_bbox_bounds(line: dict[str, Any]) -> tuple[float, float, float, float] | None:
    bbox = line.get("bbox")
    if not bbox or len(bbox) < 4:
        return None
    try:
        xs = [float(point[0]) for point in bbox]
        ys = [float(point[1]) for point in bbox]
    except (TypeError, ValueError, IndexError):
        return None
    return min(xs), min(ys), max(xs), max(ys)


def _line_with_layout(line: dict[str, Any], index: int) -> dict[str, Any] | None:
    text = str(line.get("text_clean") or line.get("text") or "").strip()
    bounds = _line_bbox_bounds(line)
    if not text or bounds is None:
        return None
    left, top, right, bottom = bounds
    page = int(line.get("page") or 1)
    return {
        "text": text,
        "confidence": float(line.get("confidence", 0.0) or 0.0),
        "bbox": line.get("bbox"),
        "page": page,
        "line_id": line.get("line_id") or f"p{page}-l{index}",
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "center_x": (left + right) / 2.0,
        "center_y": (top + bottom) / 2.0,
        "height": max(bottom - top, 1.0),
        "width": max(right - left, 1.0),
    }


def _normalize_layout_lines(lines: list[dict]) -> list[dict[str, Any]]:
    normalized = [_line_with_layout(line, index) for index, line in enumerate(lines)]
    return sorted(
        (line for line in normalized if line),
        key=lambda line: (line["page"], line["top"], line["left"]),
    )


def _layout_text(lines: list[dict[str, Any]]) -> str:
    return "\n".join(line["text"] for line in lines if line.get("text"))


def _label_value_from_same_line(
    text: str, labels: Iterable[str], value_pattern: str = r"(.+)"
) -> str | None:
    label_pattern = _label_pattern(labels)
    match = re.search(
        rf"\b(?:{label_pattern})\b\.?\s*[:#-]?\s*{value_pattern}", text, flags=re.I
    )
    if match:
        value = match.group(1).strip().strip("|;,")
        return value or None
    return None


def _looks_like_label(text: str) -> bool:
    label_groups = (
        INVOICE_NUMBER_LABEL_ALIASES,
        INVOICE_DATE_LABEL_ALIASES,
        TOTAL_AMOUNT_LABEL_ALIASES,
        (
            "Due Date",
            "Payment Due",
            "Due",
            "Subtotal",
            "Sub Total",
            "Tax",
            "VAT",
            "Discount",
            "Rounding",
        ),
    )
    return any(
        re.search(rf"\b(?:{_label_pattern(labels)})\b", text, flags=re.I)
        for labels in label_groups
    )


def _candidate_to_right(
    label_line: dict[str, Any], lines: list[dict[str, Any]]
) -> str | None:
    candidates: list[tuple[float, str]] = []
    for line in lines:
        if (
            line["line_id"] == label_line["line_id"]
            or line["page"] != label_line["page"]
        ):
            continue
        if line["left"] < label_line["right"] - max(4.0, label_line["height"] * 0.25):
            continue
        vertical_gap = abs(line["center_y"] - label_line["center_y"])
        if vertical_gap > max(label_line["height"], line["height"]) * 0.8:
            continue
        if _looks_like_label(line["text"]):
            continue
        horizontal_gap = max(0.0, line["left"] - label_line["right"])
        score = vertical_gap * 4.0 + horizontal_gap
        candidates.append((score, line["text"]))
    if not candidates:
        return None
    return min(candidates)[1]


def _candidate_below(
    label_line: dict[str, Any], lines: list[dict[str, Any]]
) -> str | None:
    candidates: list[tuple[float, str]] = []
    for line in lines:
        if (
            line["line_id"] == label_line["line_id"]
            or line["page"] != label_line["page"]
        ):
            continue
        if line["top"] < label_line["bottom"] - max(2.0, label_line["height"] * 0.15):
            continue
        vertical_gap = line["top"] - label_line["bottom"]
        if vertical_gap > label_line["height"] * 3.0:
            continue
        horizontal_offset = abs(line["left"] - label_line["left"])
        overlap = min(label_line["right"], line["right"]) - max(
            label_line["left"], line["left"]
        )
        if overlap < 0 and horizontal_offset > max(80.0, label_line["width"]):
            continue
        if _looks_like_label(line["text"]):
            continue
        score = vertical_gap * 3.0 + horizontal_offset
        candidates.append((score, line["text"]))
    if not candidates:
        return None
    return min(candidates)[1]


def _extract_layout_labeled_value(
    lines: list[dict[str, Any]], labels: Iterable[str], *, value_pattern: str = r"(.+)"
) -> str | None:
    label_pattern = re.compile(rf"\b(?:{_label_pattern(labels)})\b", flags=re.I)
    for line in lines:
        if not label_pattern.search(line["text"]):
            continue
        inline = _label_value_from_same_line(
            line["text"], labels, value_pattern=value_pattern
        )
        if inline:
            return inline
        right = _candidate_to_right(line, lines)
        if right:
            return right.strip().strip("|;,")
        below = _candidate_below(line, lines)
        if below:
            return below.strip().strip("|;,")
    return None


def _group_layout_rows(lines: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    rows: list[list[dict[str, Any]]] = []
    for line in lines:
        if not rows:
            rows.append([line])
            continue
        previous = rows[-1]
        prev_center = sum(item["center_y"] for item in previous) / len(previous)
        prev_height = max(item["height"] for item in previous)
        if (
            line["page"] == previous[0]["page"]
            and abs(line["center_y"] - prev_center)
            <= max(prev_height, line["height"]) * 0.7
        ):
            previous.append(line)
        else:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda item: item["left"])
    return rows


def _row_text(row: list[dict[str, Any]]) -> str:
    return " ".join(
        cell["text"] for cell in sorted(row, key=lambda item: item["left"])
    ).strip()


def _infer_header_columns(row: list[dict[str, Any]]) -> dict[str, float]:
    if len(row) <= 1:
        return {}
    columns: dict[str, float] = {}
    for cell in row:
        text = cell["text"].lower()
        if re.search(r"description|code/?desc|item|service|product", text):
            columns.setdefault("description", cell["center_x"])
        if re.search(r"\bqty\b|quantity", text):
            columns.setdefault("quantity", cell["center_x"])
        if re.search(r"unit|price|s/price|rate", text) and not re.search(
            r"amount|total", text
        ):
            columns.setdefault("unit_price", cell["center_x"])
        if re.search(r"amount|total", text):
            columns.setdefault("amount", cell["center_x"])
    return columns


def _assign_cells_to_columns(
    row: list[dict[str, Any]], columns: dict[str, float]
) -> dict[str, str]:
    assigned: dict[str, list[str]] = {name: [] for name in columns}
    ordered_columns = sorted(columns.items(), key=lambda item: item[1])
    for cell in row:
        nearest = min(
            ordered_columns, key=lambda item: abs(cell["center_x"] - item[1])
        )[0]
        assigned.setdefault(nearest, []).append(cell["text"])
    return {name: " ".join(parts).strip() for name, parts in assigned.items() if parts}


def _parse_layout_row_with_columns(
    row: list[dict[str, Any]], columns: dict[str, float]
) -> LineItem | None:
    text = _row_text(row)
    assigned = _assign_cells_to_columns(row, columns) if columns else {}
    description = assigned.get("description")
    quantity = (
        _normalize_quantity(parse_amount(assigned.get("quantity")))
        if assigned.get("quantity")
        else None
    )
    unit_price = (
        parse_amount(assigned.get("unit_price")) if assigned.get("unit_price") else None
    )
    amount = parse_amount(assigned.get("amount")) if assigned.get("amount") else None

    if not amount:
        amounts = [parse_amount(token) for token in re.findall(AMOUNT_TOKEN, text)]
        amounts = [value for value in amounts if value is not None]
        if amounts:
            amount = amounts[-1]
            if unit_price is None and len(amounts) >= 2:
                unit_price = amounts[-2]

    if not description:
        row_match = re.match(
            r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+"
            + AMOUNT_TOKEN
            + r"\s+"
            + AMOUNT_TOKEN
            + r"$",
            text,
        )
        if row_match and row_match.group(1):
            description = row_match.group(1).strip()
            quantity = _normalize_quantity(parse_amount(row_match.group(2)))
        elif amount is not None:
            amount_tokens = re.findall(AMOUNT_TOKEN, text)
            description = (
                re.sub(re.escape(amount_tokens[-1]) + r"\s*$", "", text).strip(" -|\t")
                if amount_tokens
                else text
            )

    if not description or len(description) < 3 or amount is None:
        return None
    item: LineItem = {
        "description": description,
        "quantity": quantity,
        "unit_price": unit_price,
        "amount": amount,
    }
    return item


def _extract_layout_line_items(lines: list[dict[str, Any]]) -> list[LineItem]:
    rows = _group_layout_rows(lines)
    header_pattern = re.compile(
        r"(?=.*\b(description|code/?desc|item|service|product)\b)(?=.*\b(qty|quantity|unit|price|amount|s/price)\b)",
        re.I,
    )
    stop_pattern = re.compile(
        r"\b(subtotal|sub total|total\s+qty|total\s+sales|grand\s+total|total|tax|discount|"
        r"balance|amount due|payment|cash|change|rounding)\b",
        re.I,
    )
    for index, row in enumerate(rows):
        text = _row_text(row)
        if not header_pattern.search(text):
            continue
        columns = _infer_header_columns(row)
        items: list[LineItem] = []
        table_text = [text]
        for data_row in rows[index + 1 :]:
            row_text = _row_text(data_row)
            if stop_pattern.search(row_text):
                break
            if not row_text:
                continue
            table_text.append(row_text)
            if columns:
                item = _parse_layout_row_with_columns(data_row, columns)
                if item:
                    items.append(item)
        if items:
            return items[:100]
        fallback_items = extract_line_items("\n".join(table_text))
        if fallback_items:
            return fallback_items
    return []


def extract_invoice_fields_from_lines(lines: list[dict]) -> InvoiceFields:
    """Extract invoice fields using OCR line bbox proximity, falling back to text parsing."""
    layout_lines = _normalize_layout_lines(lines)
    text = (
        _layout_text(layout_lines)
        if layout_lines
        else "\n".join(str(line.get("text") or "") for line in lines)
    )
    fields = extract_invoice_fields(text)
    if not layout_lines:
        return fields

    prefer_day_first = _is_malaysian_receipt(text)
    invoice_number = _extract_layout_labeled_value(
        layout_lines,
        INVOICE_NUMBER_LABEL_ALIASES,
        value_pattern=r"([A-Z0-9][A-Z0-9._/-]{2,})",
    )
    if invoice_number:
        fields["invoice_number"] = invoice_number.strip().rstrip(".,")

    date_pattern = rf"(\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}[/-]\d{{1,2}}[/-]\d{{2,4}}|\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}}|(?:{MONTHS})\s+\d{{1,2}},\s*\d{{4}})"
    invoice_date_raw = _extract_layout_labeled_value(
        layout_lines, INVOICE_DATE_LABEL_ALIASES, value_pattern=date_pattern
    )
    due_date_raw = _extract_layout_labeled_value(
        layout_lines, ["Due Date", "Payment Due", "Due"], value_pattern=date_pattern
    )
    extra_reasons: set[str] = set()
    if invoice_date_raw:
        invoice_date, ambiguous_invoice = parse_invoice_date(
            invoice_date_raw, prefer_day_first=prefer_day_first
        )
        fields["invoice_date"] = invoice_date
        if ambiguous_invoice:
            extra_reasons.add("ambiguous_date_format")
    if due_date_raw:
        due_date, ambiguous_due = parse_invoice_date(
            due_date_raw, prefer_day_first=prefer_day_first
        )
        fields["due_date"] = due_date
        if ambiguous_due:
            extra_reasons.add("ambiguous_date_format")

    amount_specs = (
        ("subtotal", ["Subtotal", "Sub Total", "Net Amount"]),
        ("tax", ["Tax", "VAT", "Sales Tax", "GST Amount"]),
        ("discount", ["Discount"]),
        ("rounding", ["Rounding", "Rounding Adjustment"]),
        ("total_amount", TOTAL_AMOUNT_LABEL_ALIASES),
    )
    for field_name, labels in amount_specs:
        raw_value = _extract_layout_labeled_value(
            layout_lines, labels, value_pattern=rf"({AMOUNT_TOKEN})"
        )
        amount = parse_amount(raw_value) if raw_value else None
        if amount is not None:
            fields[field_name] = amount  # type: ignore[literal-required]

    line_items = _extract_layout_line_items(layout_lines)
    if line_items:
        fields["line_items"] = line_items

    fields["currency"] = detect_currency(text)
    stale_reasons = {
        "missing_invoice_number",
        "missing_invoice_date",
        "missing_total_amount",
        "currency_not_detected",
        "low_ocr_confidence",
        "line_items_subtotal_mismatch",
        "line_items_total_mismatch",
        "line_items_quantity_mismatch",
    }
    fields["review_reasons"] = [
        reason
        for reason in fields.get("review_reasons", [])
        if reason not in stale_reasons
    ]
    return validate_invoice_fields(fields, extra_review_reasons=sorted(extra_reasons))


def extract_invoice_fields(text: str) -> InvoiceFields:
    fields = empty_invoice_fields()
    lines = text.splitlines()
    fields["document_type"] = detect_document_type(text)
    fields["invoice_number"] = extract_invoice_number(text)
    prefer_day_first = _is_malaysian_receipt(text)
    invoice_date, ambiguous_invoice = _extract_labeled_date(
        text, INVOICE_DATE_LABEL_ALIASES, prefer_day_first=prefer_day_first
    )
    due_date, ambiguous_due = _extract_labeled_date(
        text, ["Due Date", "Payment Due", "Due"], prefer_day_first=prefer_day_first
    )
    fields["invoice_date"] = invoice_date
    fields["due_date"] = due_date
    fields["subtotal"] = _extract_labeled_amount(
        text, ["Subtotal", "Sub Total", "Net Amount"]
    )
    fields["tax"] = _extract_labeled_amount(
        text, ["Tax", "VAT", "Sales Tax", "GST Amount"]
    )
    fields["discount"] = _extract_labeled_amount(text, ["Discount"])
    fields["rounding"] = _extract_labeled_amount(
        text, ["Rounding", "Rounding Adjustment"]
    )
    fields["total_amount"] = extract_total_amount(text)
    fields["total_quantity"] = extract_total_quantity(text)
    fields["cash_received"] = extract_cash_received(text)
    fields["change_amount"] = extract_change_amount(text)
    fields["currency"] = detect_currency(text)
    fields["payment_method"] = extract_payment_method(text)
    fields["document_title"] = extract_document_title(text)
    fields["vendor_registration_number"] = extract_vendor_registration_number(text)
    fields["gst_id"] = extract_gst_id(text)
    fields["cashier"] = extract_cashier(text)
    fields["transaction_time"] = extract_transaction_time(text)
    fields["salesperson"] = extract_salesperson(text)
    fields["reference"] = extract_reference(text)
    fields["line_items"] = extract_line_items(text)
    vendor_name, vendor_address, buyer_name = _extract_vendor_and_buyer(lines)
    vendor_phone, vendor_fax, vendor_email = extract_contact_details(text)
    fields["vendor_name"] = vendor_name
    fields["vendor_address"] = vendor_address
    fields["vendor_phone"] = vendor_phone
    fields["vendor_fax"] = vendor_fax
    fields["vendor_email"] = vendor_email
    fields["buyer_name"] = buyer_name

    reasons = []
    if ambiguous_invoice or ambiguous_due:
        reasons.append("ambiguous_date_format")
    return validate_invoice_fields(fields, extra_review_reasons=reasons)


def extract_invoice_from_result(
    doc_id: str, result: dict, out_dir: Path, ocr_lines: list[dict] | None = None
) -> InvoiceFields:
    """Run invoice extraction after assemble and persist invoice_fields.json."""
    text = result.get("full_text", "") or ""
    fields = (
        extract_invoice_fields_from_lines(ocr_lines)
        if ocr_lines
        else extract_invoice_fields(text)
    )
    invoice_dir = out_dir.parent / "invoice"
    invoice_dir.mkdir(parents=True, exist_ok=True)
    final_dir = out_dir
    final_dir.mkdir(parents=True, exist_ok=True)
    payload = dict(fields)
    payload["doc_id"] = doc_id
    (invoice_dir / "invoice_fields.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (final_dir / "invoice_fields.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return fields
