# OCR Document Processing Pipeline

A **production-style OCR pipeline** for processing documents (PDF/images), extracting structured invoice fields, and visualizing processing artifacts through a web UI.

The system is designed with **modern backend architecture**:

* FastAPI (API service)
* Redis (job queue)
* RQ Worker (background processing)
* PaddleOCR (text recognition)
* Docker Compose (containerized services)
* React + Vite (UI for pipeline visualization)

---

# Architecture

The system is built as an **asynchronous document processing pipeline**.

```
User
  │
  ▼
React UI
  │
  ▼
FastAPI API
  │
  ▼
Redis Queue
  │
  ▼
RQ Worker
  │
  ▼
OCR Pipeline
  │
  ▼
Storage + Results
```

---

# OCR Processing Pipeline

Each uploaded document goes through several stages.

```
Upload
   │
   ▼
Ingest
   │
   ▼
Render
(PDF → Images)
   │
   ▼
Preprocess
(Basic smart upscale / Receipt / Strong)
   │
   ▼
OCR
(PaddleOCR)
   │
   ▼
Post-processing
(Text assembly)
   │
   ▼
Invoice/Receipt extraction
(Fields + line items + validation)
   │
   ▼
Results
(JSON + invoice_fields.json)
```

---

# Features

* Upload **PDF or image documents**
* Automatic **PDF page rendering**
* Multiple **image preprocessing strategies**, including smart 1.5x/2x OCR upscaling, thermal receipt handling, and SORIE/SROIE distant-receipt upscale modes
* **Retry OCR pipeline** if confidence is low and compare basic/receipt/sorie/strong variants
* **Layout-aware text assembly**
* **Pipeline visualization UI**
* Asynchronous processing with **Redis + RQ**
* Dockerized environment for reproducibility

---

# Project Structure

```
ocr-project
│
├── app
│   ├── main.py                 # FastAPI application
│   ├── jobs.py                 # background OCR job
│   ├── queue.py                # Redis queue configuration
│   ├── storage.py              # storage helpers
│   │
│   └── pipeline
│       ├── ingest.py           # save uploaded files
│       ├── render.py           # convert PDF → images
│       ├── preprocess.py       # image preprocessing
│       ├── ocr.py              # OCR execution
│       └── assemble.py         # assemble final text
│
├── workers
│   └── worker.py               # RQ worker process
│
├── ui                          # React UI
│   ├── src
│   │   ├── App.jsx
│   │   └── App.css
│
├── storage                     # document artifacts
│
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

# Storage Layout

Each document gets its own directory where all artifacts are stored.

```
storage/
   doc_id/
      original/
      pages/
      processed/
         basic/
         receipt/
         sorie/
         strong/
      ocr/
      postprocessed/
      out/
         result.json
```

This allows the system to **inspect every stage of the OCR pipeline**.

---

# API Endpoints

## Upload Document

```
POST /v1/documents
```

Returns:

```json
{
  "doc_id": "...",
  "job_id": "...",
  "filename": "file.pdf"
}
```

---

## Check Job Status

```
GET /v1/jobs/{job_id}
```

Returns job progress, stage, and status.

---

## Get OCR Result

```
GET /v1/documents/{doc_id}/result
```

Returns structured JSON output.

---

## Get Page Images

```
GET /v1/documents/{doc_id}/pages
GET /v1/documents/{doc_id}/pages/{filename}
```

Used by the UI to visualize the processing pipeline.

---


# Invoice and Receipt Extraction

After OCR assembly, the pipeline extracts structured invoice fields and persists them to
`out/invoice_fields.json`. The extractor includes receipt-specific logic for thermal
cash-sales layouts like Malaysian receipts:

* detects `cash_sales_receipt` documents from `CASH SALES`, `CASH BILL`, or `RECEIPT` text
* normalizes Malaysian day-first dates such as `11/01/2019` to `2019-01-11`
* groups item-code rows with following description lines
* extracts receipt totals including `Total Qty`, `Total Sales`, `CASH`, and `Change`
* validates line-item amount totals, quantity totals, and cash/change arithmetic

The OCR retry metadata records which preprocess variant was selected for each page, so
you can inspect whether `basic`, `receipt`, `sorie`, or `strong` produced the best text.

The `sorie` preprocess variant is tuned for SORIE/SROIE-style receipt photos where
the receipt appears small because the camera was too far away. It crops foreground
content before applying capped bicubic upscaling, denoising, sharpening, and a clean
white border so OCR sees larger characters instead of an already-large full canvas.

# Running the Project

## Requirements

* Docker
* Docker Compose

---

## Start the System

```
docker compose up --build
```

This starts the following services:

| Service | Port |
| ------- | ---- |
| API     | 8000 |
| Redis   | 6379 |
| UI      | 5173 |

---

## Access the System

API documentation:

```
http://localhost:8000/docs
```

UI interface:

```
http://localhost:5173
```

---

# Learning Goals of This Project

This project demonstrates:

* Building **production-style AI pipelines**
* Asynchronous job processing
* Background workers
* Dockerized ML services
* Document AI architecture
* OCR system design

---


---

# Invoice Extraction Layer

After the existing OCR assemble stage, the worker now runs a local-first invoice extraction layer. The original OCR flow is preserved, and the invoice layer reads the assembled `full_text`, extracts structured fields with deterministic rules, validates the result, and writes JSON artifacts.

Updated pipeline:

```
upload
-> render/native-text routing
-> preprocess basic
-> preprocess receipt
-> preprocess SORIE/SROIE upscale
-> preprocess strong
-> OCR with retry
-> postprocess
-> assemble
-> invoice field extraction
-> invoice validation
-> invoice_fields.json
-> final API/UI display
```

Invoice artifacts are saved in both locations for convenient API and storage-first inspection:

```
storage/<doc_id>/invoice/invoice_fields.json
storage/<doc_id>/out/invoice_fields.json
```

The invoice extractor uses regex and rules for invoice numbers, dates, totals, subtotal, tax, discounts, currency, vendor/buyer clues, payment methods, and simple table-like line items. Validation lowers confidence and marks `needs_review` when required fields are missing, ambiguous dates are detected, currency is unknown, or totals do not reconcile.

## Invoice API

Existing endpoints continue to work. `GET /v1/documents/{doc_id}/result` now includes `invoice_fields` when available. A dedicated endpoint is also available:

```
GET /v1/documents/{doc_id}/invoice
```

## Example `invoice_fields.json`

```json
{
  "doc_id": "example-doc-id",
  "document_type": "invoice",
  "vendor_name": "Acme Supplies LLC",
  "vendor_address": "123 Market Street",
  "buyer_name": "Beta Co",
  "invoice_number": "INV-1001",
  "invoice_date": "2026-05-09",
  "due_date": "2026-05-30",
  "subtotal": 100.0,
  "tax": 10.0,
  "discount": 5.0,
  "total_amount": 105.0,
  "currency": "USD",
  "payment_method": "bank transfer",
  "line_items": [
    {
      "description": "Consulting",
      "quantity": 2,
      "unit_price": 50.0,
      "amount": 100.0
    }
  ],
  "confidence": 1.0,
  "needs_review": false,
  "review_reasons": []
}
```

## Invoice Evaluation

A lightweight evaluation harness is available under `evaluation/`. Add document IDs and expected values to `evaluation/ground_truth.csv`, ensure each document has an extracted `invoice_fields.json` in `storage/<doc_id>/`, then run:

```
python evaluation/run_invoice_evaluation.py
```

The script writes:

```
evaluation/reports/invoice_evaluation_summary.json
evaluation/reports/invoice_evaluation_summary.csv
```
