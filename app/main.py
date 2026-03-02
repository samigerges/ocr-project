import uuid
import json
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException

from app.pipeline.ingest import save_upload
from app.pipeline.render import render_document
from app.pipeline.preprocess import preprocess_document_pages
from app.pipeline.ocr import run_ocr_from_manifest
from app.storage import doc_dir


app = FastAPI(title="Local OCR Service", version="0.1.0")


@app.get("/")
def root():
    return {"message": "OCR API is running. Visit /docs to test."}


@app.get("/health")
def health():
    return {"status": "ok"}


def _manifest_summary(pages_dir: Path) -> dict:
    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        return {"native_pages": 0, "ocr_pages": 0, "total_pages": 0}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native_pages = sum(1 for x in manifest if x.get("source") == "native")
    ocr_pages = sum(1 for x in manifest if x.get("source") == "ocr")
    return {"native_pages": native_pages, "ocr_pages": ocr_pages, "total_pages": len(manifest)}


@app.post("/v1/documents")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    doc_id = str(uuid.uuid4())
    base = doc_dir(doc_id)

    # 1) Save original
    try:
        saved_path = save_upload(doc_id, file.filename, content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingest failed: {e}")

    # 2) Render (creates manifest.json + artifacts in pages/)
    pages_dir = base / "pages"
    try:
        render_document(saved_path, pages_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")

    # 3) Preprocess only OCR pages
    processed_dir = base / "processed"
    try:
        processed_outputs = preprocess_document_pages(pages_dir, processed_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preprocess failed: {e}")

    # 4) OCR only OCR pages; native pages are read directly
    ocr_dir = base / "ocr"
    try:
        ocr_results = run_ocr_from_manifest(pages_dir, processed_dir, ocr_dir, lang="en")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    summary = _manifest_summary(pages_dir)

    return {
        "doc_id": doc_id,
        "filename": file.filename,
        "summary": summary,
        "artifacts": {
            "base_dir": str(base),
            "original_dir": str(base / "original"),
            "pages_dir": str(pages_dir),
            "processed_dir": str(processed_dir),
            "ocr_dir": str(ocr_dir),
        },
        "processed_images": [p.name for p in processed_outputs],
        "pages_in_results": len(ocr_results),
    }