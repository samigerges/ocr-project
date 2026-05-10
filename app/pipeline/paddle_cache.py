from __future__ import annotations

import tarfile
from pathlib import Path


DEFAULT_PADDLEOCR_CACHE_DIR = Path.home() / ".paddleocr"


def remove_corrupt_paddleocr_archives(cache_dir: Path | None = None) -> list[Path]:
    """
    Delete incomplete PaddleOCR model tar archives from the local cache.

    PaddleOCR's downloader skips a model archive when a .tar file already exists,
    even if a previous download was interrupted and left a truncated archive. The
    next startup then fails while extracting the stale tar with
    ``tarfile.ReadError: unexpected end of data``. Removing only unreadable tar
    files lets PaddleOCR download a clean copy on the next initialization while
    preserving valid cached models.
    """
    root = cache_dir or DEFAULT_PADDLEOCR_CACHE_DIR
    if not root.exists():
        return []

    removed: list[Path] = []
    for archive in root.rglob("*.tar"):
        if _is_valid_tar_archive(archive):
            continue

        archive.unlink(missing_ok=True)
        removed.append(archive)

    return removed


def _is_valid_tar_archive(path: Path) -> bool:
    try:
        with tarfile.open(path) as tar_obj:
            for member in tar_obj:
                # Iterating validates the complete archive without keeping the
                # full member list in memory.
                pass
    except (tarfile.TarError, OSError, EOFError):
        return False

    return True
