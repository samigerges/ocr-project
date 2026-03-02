from pathlib import Path
from app.storage import ensure_doc_dirs, original_path


def save_upload(doc_id: str, filename: str, content: bytes) -> Path:
    """
    Save uploaded bytes into:
      storage/{doc_id}/original/{filename}
    Returns the saved file path.
    """
    ensure_doc_dirs(doc_id)
    out_path = original_path(doc_id, filename)
    out_path.write_bytes(content)
    return out_path
