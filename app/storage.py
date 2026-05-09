from pathlib import Path
from .settings import settings


def storage_root() -> Path:
    return Path(settings.storage_dir)


def doc_dir(doc_id: str) -> Path:
    return storage_root() / doc_id


def ensure_doc_dirs(doc_id: str) -> None:
    """
    Creates the canonical folder structure for a document.
    """
    base = doc_dir(doc_id)
    (base / "original").mkdir(parents=True, exist_ok=True)
    (base / "pages").mkdir(parents=True, exist_ok=True)
    (base / "processed").mkdir(parents=True, exist_ok=True)
    (base / "ocr").mkdir(parents=True, exist_ok=True)


def original_path(doc_id: str, filename: str) -> Path:
    return doc_dir(doc_id) / "original" / filename


def result_json_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "result.json"
