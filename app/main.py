import uuid
import json
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from rq.job import Job

from app.pipeline.ingest import save_upload
from app.queue import queue, redis_conn
from app.jobs import process_document_job
from app.storage import doc_dir


app = FastAPI(title="Local OCR Service", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/documents")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    doc_id = str(uuid.uuid4())

    # Save original only
    save_upload(doc_id, file.filename, content)

    # Enqueue OCR job
    job = queue.enqueue(process_document_job, doc_id, job_timeout=900)

    return {
        "doc_id": doc_id,
        "job_id": job.id,
        "filename": file.filename,
    }


@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str):
    job = Job.fetch(job_id, connection=redis_conn)
    return {
        "job_id": job.id,
        "status": job.get_status(),
        "result": job.result,
        "meta": job.meta,
        "is_finished": job.is_finished,
        "is_failed": job.is_failed,
        "exc_info": job.exc_info if job.is_failed else None,
    }


@app.get("/v1/documents/{doc_id}/result")
def get_result(doc_id: str):
    out_dir = doc_dir(doc_id) / "out"
    result_path = out_dir / "result.json"
    if not result_path.exists():
        raise HTTPException(status_code=404, detail="Result not ready yet")
    return json.loads(result_path.read_text(encoding="utf-8"))


@app.get("/v1/documents/{doc_id}/text", response_class=PlainTextResponse)
def get_result_text(doc_id: str):
    out_dir = doc_dir(doc_id) / "out"
    txt_path = out_dir / "result.txt"
    if not txt_path.exists():
        raise HTTPException(status_code=404, detail="Result not ready yet")
    return txt_path.read_text(encoding="utf-8")


@app.get("/v1/documents/{doc_id}/original")
def get_original_file(doc_id: str):
    """
    Return the originally uploaded file.
    """
    original_dir = doc_dir(doc_id) / "original"
    if not original_dir.exists():
        raise HTTPException(status_code=404, detail="Original directory not found")

    files = [p for p in original_dir.iterdir() if p.is_file()]
    if not files:
        raise HTTPException(status_code=404, detail="Original file not found")

    return FileResponse(files[0])


@app.get("/v1/documents/{doc_id}/pages")
def list_pages(doc_id: str):
    """
    List rendered page images under storage/<doc_id>/pages
    """
    pages_dir = doc_dir(doc_id) / "pages"
    if not pages_dir.exists():
        raise HTTPException(status_code=404, detail="Pages not ready yet")

    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files = sorted(
        [
            p.name
            for p in pages_dir.iterdir()
            if p.is_file() and p.suffix.lower() in exts
        ]
    )
    return {"pages": files}


@app.get("/v1/documents/{doc_id}/pages/{filename}")
def get_page_image(doc_id: str, filename: str):
    """
    Return rendered page image.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    path = doc_dir(doc_id) / "pages" / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Not found")

    return FileResponse(path)


@app.get("/v1/documents/{doc_id}/processed/{mode}/{filename}")
def get_processed_image(doc_id: str, mode: str, filename: str):
    """
    Return processed page image for a given preprocess mode.
    Example:
      /v1/documents/{doc_id}/processed/basic/page_0001.png
      /v1/documents/{doc_id}/processed/strong/page_0001.png
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    if mode not in {"basic", "strong"}:
        raise HTTPException(status_code=400, detail="Invalid preprocess mode")

    allowed = {".png", ".jpg", ".jpeg", ".webp"}
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    path = doc_dir(doc_id) / "processed" / mode / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Processed image not found")

    return FileResponse(path)


@app.get("/v1/documents/{doc_id}/ocr/{page_no}")
def get_ocr_page_result(doc_id: str, page_no: int):
    """
    Return OCR JSON for one page.
    """
    path = doc_dir(doc_id) / "ocr" / f"page_{page_no:04d}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="OCR page result not found")

    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/v1/documents/{doc_id}/llm/{page_no}")
def get_llm_page_result(doc_id: str, page_no: int):
    """
    Return LLM refined JSON for one page.
    """
    path = doc_dir(doc_id) / "llm" / f"page_{page_no:04d}.json"

    if not path.exists():
        raise HTTPException(status_code=404, detail="LLM page result not found")

    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/v1/documents/{doc_id}/llm")
def get_llm_results(doc_id: str):
    """
    Return all LLM refined pages.
    """
    llm_dir = doc_dir(doc_id) / "llm"

    if not llm_dir.exists():
        raise HTTPException(status_code=404, detail="LLM results not ready")

    pages = sorted(llm_dir.glob("page_*.json"))

    results = []

    for p in pages:
        results.append(json.loads(p.read_text(encoding="utf-8")))

    return {
        "doc_id": doc_id,
        "pages": results,
    }

@app.get("/v1/documents/{doc_id}/pipeline")
def get_pipeline_view(doc_id: str):
    """
    UI helper endpoint:
    returns a summary of available pipeline artifacts per page.
    """
    base = doc_dir(doc_id)
    pages_dir = base / "pages"
    processed_basic_dir = base / "processed" / "basic"
    processed_strong_dir = base / "processed" / "strong"
    ocr_dir = base / "ocr"
    llm_dir = base / "llm"

    manifest_path = pages_dir / "manifest.json"

    if not manifest_path.exists():
        return {
            "doc_id": doc_id,
            "status": "not_ready",
            "pages": []
            }

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    pages = []
    for item in manifest:
        page_no = int(item["page"])
        source = item["source"]
        artifact = item["artifact"]

        page_info = {
            "page": page_no,
            "source": source,
            "rendered": artifact if source == "ocr" else None,
            "native_text_file": artifact if source == "native" else None,
            "processed_basic": artifact if (processed_basic_dir / artifact).exists() else None,
            "processed_strong": artifact if (processed_strong_dir / artifact).exists() else None,
            "ocr_result_exists": (ocr_dir / f"page_{page_no:04d}.json").exists(),
            "llm_result_exists": (llm_dir / f"page_{page_no:04d}.json").exists(),
        }
        pages.append(page_info)

    return {
        "doc_id": doc_id,
        "pages": pages,
    }

