import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from rq.job import Job

from app.pipeline.ingest import save_upload
from app.queue import queue, redis_conn
from app.jobs import process_document_job
from app.storage import doc_dir
import json

app = FastAPI(title="Local OCR Service", version="0.1.0")


@app.post("/v1/documents")
async def upload_document(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    doc_id = str(uuid.uuid4())

    # 1) save original only 
    save_upload(doc_id, file.filename, content)

    # 2) enqueue background OCR job
    job = queue.enqueue(process_document_job, doc_id)

    return {"doc_id": doc_id, "job_id": job.id, "filename": file.filename}

@app.get("/v1/jobs/{job_id}")
def job_status(job_id: str):
    job = Job.fetch(job_id, connection=redis_conn)
    return {
        "job_id": job.id,
        "status": job.get_status(),
        "result": job.result,
        "meta": job.meta,  # stage/progress/message
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