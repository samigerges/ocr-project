from pathlib import Path

from rq import get_current_job

from app.storage import doc_dir
from app.pipeline.render import render_document
from app.pipeline.preprocess import preprocess_document_pages
from app.pipeline.ocr import run_ocr_from_manifest
from app.pipeline.postprocess import postprocess_ocr_dir
from app.pipeline.llm_refine import refine_ocr_dir
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
    _set_progress("render", 10, "Rendering pages / extracting native text")
    render_document(input_path, pages_dir)

    # 3) preprocess basic
    _set_progress("preprocess_basic", 25, "Preprocessing OCR pages (basic)")
    preprocess_document_pages(pages_dir, processed_dir, mode="basic")

    # 4) preprocess strong retry variant
    _set_progress("preprocess_strong", 40, "Preparing retry preprocess variant")
    preprocess_document_pages(pages_dir, processed_dir, mode="strong")

    # 5) OCR with retry logic
    _set_progress("ocr", 55, "Running OCR with retry methodology")
    run_ocr_from_manifest(pages_dir, processed_dir, ocr_dir, lang="en", confidence_threshold=0.90)

    # 6) postprocess
    _set_progress("postprocess", 70, "Postprocessing OCR results")

    post_dir = base / "postprocessed"
    postprocess_ocr_dir(ocr_dir, post_dir)

    # 7) LLM refine
    _set_progress("llm_refine", 85, "Refining low-confidence lines with LLM")

    llm_dir = base / "llm"
    refine_ocr_dir(post_dir, llm_dir)

    # 8) assemble
    _set_progress("assemble", 95, "Assembling final outputs")

    result = assemble_results(doc_id, pages_dir, llm_dir, out_dir)

    _set_progress("done", 100, "Done")
    return {"doc_id": doc_id, "out_dir": str(out_dir), "full_text_len": len(result.get("full_text", ""))}