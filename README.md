# OCR Document Processing Pipeline

A **production-style OCR pipeline** for processing documents (PDF/images), extracting text, and visualizing the full processing pipeline through a web UI.

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
(Basic / Strong)
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
Results
(JSON + TXT)
```

---

# Features

* Upload **PDF or image documents**
* Automatic **PDF page rendering**
* Multiple **image preprocessing strategies**
* **Retry OCR pipeline** if confidence is low
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
         strong/
      ocr/
      out/
         result.json
         result.txt
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

## Get Extracted Text

```
GET /v1/documents/{doc_id}/text
```

Returns plain text output.

---

## Get Page Images

```
GET /v1/documents/{doc_id}/pages
GET /v1/documents/{doc_id}/pages/{filename}
```

Used by the UI to visualize the processing pipeline.

---

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

