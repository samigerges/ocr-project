from pathlib import Path

from rq import get_current_job

from app.storage import doc_dir
from app.pipeline.render import render_document
from app.pipeline.preprocess import preprocess_document_pages
from app.pipeline.ocr import run_ocr_from_manifest
from app.pipeline.assemble import assemble_results


def _set_progress(stage: str, progress: int, message: str = ""):
    """
        to update the progress status 
    """
    job = get_current_job()
    if job is None:
        return
    job.meta["stage"] = stage
    job.meta["progress"] = int(progress)
    if message:
        job.meta["message"] = message
    job.save_meta()


def process_document_job(doc_id: str) -> dict:
    """
    Background job: run pipeline and return results.json and results.txt
    """
    base = doc_dir(doc_id)
    original_dir = base / "original"
    pages_dir = base / "pages"
    processed_dir = base / "processed"
    ocr_dir = base / "ocr"
    out_dir = base / "out"

    _set_progress("start", 5, "Starting pipeline")

    # 1) pick original file (pdf/png/jpg)
    originals = list(original_dir.glob("*"))
    if not originals:
        raise FileNotFoundError(f"No original files found in {original_dir}")

    input_path = originals[0]

    # 2) render
    _set_progress("render", 20, "Rendering pages / extracting native text")
    render_document(input_path, pages_dir)

    # 3) preprocess
    _set_progress("preprocess", 45, "Preprocessing OCR pages")
    preprocess_document_pages(pages_dir, processed_dir)

    # 4) OCR
    _set_progress("ocr", 80, "Running OCR")
    run_ocr_from_manifest(pages_dir, processed_dir, ocr_dir)

    # 5) assemble
    _set_progress("assemble", 95, "Assembling final outputs")
    result = assemble_results(doc_id, pages_dir, ocr_dir, out_dir)

    _set_progress("done", 100, "Done")
    return {"doc_id": doc_id, "out_dir": str(out_dir), "full_text_len": len(result.get("full_text", ""))}