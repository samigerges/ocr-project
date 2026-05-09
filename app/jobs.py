from pathlib import Path
import json

from rq import get_current_job

from app.storage import doc_dir
from app.pipeline.render import render_document
from app.pipeline.preprocess import preprocess_document_pages
from app.pipeline.ocr import run_ocr_from_manifest
from app.pipeline.postprocess import postprocess_ocr_dir
from app.pipeline.assemble import assemble_results
from app.pipeline.invoice_extract import extract_invoice_from_result
from app.pipeline.quality import assess_pages_from_manifest
from app.pipeline.receipt_layout import build_receipt_layout
from app.pipeline.receipt_extract import extract_receipt_from_layout


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
    Background job: run pipeline and return result.json plus invoice fields.
    """
    base = doc_dir(doc_id)
    original_dir = base / "original"
    pages_dir = base / "pages"
    processed_dir = base / "processed"
    ocr_dir = base / "ocr"
    layout_dir = base / "layout"
    extracted_dir = base / "extracted"
    validation_dir = base / "validation"
    quality_dir = base / "quality"
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

    # 3) quality assessment
    _set_progress("quality", 20, "Assessing image quality")
    quality_report = assess_pages_from_manifest(pages_dir, quality_dir)

    # 4) preprocess basic
    _set_progress("preprocess_basic", 25, "Preprocessing OCR pages (basic)")
    preprocess_document_pages(pages_dir, processed_dir, mode="basic")

    # 5) preprocess thermal receipt + strong retry variants
    _set_progress("preprocess_receipt", 35, "Preparing thermal receipt preprocess variant")
    preprocess_document_pages(pages_dir, processed_dir, mode="receipt")

    _set_progress("preprocess_strong", 40, "Preparing retry preprocess variant")
    preprocess_document_pages(pages_dir, processed_dir, mode="strong")

    # 6) OCR with retry logic
    _set_progress("ocr", 55, "Running OCR with retry methodology")
    run_ocr_from_manifest(pages_dir, processed_dir, ocr_dir, lang="en", confidence_threshold=0.90)

    # 7) postprocess
    _set_progress("postprocess", 70, "Postprocessing OCR results")

    post_dir = base / "postprocessed"
    postprocess_ocr_dir(ocr_dir, post_dir)

    # 8) assemble
    _set_progress("assemble", 85, "Assembling final outputs")
    result = assemble_results(doc_id, pages_dir, post_dir, out_dir)

    # 9) invoice extraction
    _set_progress("invoice_extract", 97, "Extracting structured invoice fields")
    invoice_fields = extract_invoice_from_result(doc_id, result, out_dir)
    result["invoice_fields"] = invoice_fields

    _set_progress("receipt_layout", 98, "Grouping receipt layout and extracting receipt fields")
    receipt_layout = build_receipt_layout(post_dir, layout_dir)
    receipt_fields = extract_receipt_from_layout(doc_id, receipt_layout, extracted_dir, validation_dir)
    result["receipt_fields"] = receipt_fields.model_dump() if hasattr(receipt_fields, "model_dump") else receipt_fields.dict()
    result["quality"] = quality_report
    (out_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    _set_progress("done", 100, "Done")
    return {
        "doc_id": doc_id,
        "out_dir": str(out_dir),
        "full_text_len": len(result.get("full_text", "")),
        "invoice_confidence": invoice_fields.get("confidence"),
        "invoice_needs_review": invoice_fields.get("needs_review"),
        "quality_status": quality_report.get("status"),
        "receipt_validation": str(validation_dir / "report.json"),
    }
