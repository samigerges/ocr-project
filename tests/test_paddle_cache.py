import tarfile
from pathlib import Path

from app.pipeline.paddle_cache import remove_corrupt_paddleocr_archives


def test_remove_corrupt_paddleocr_archives_deletes_truncated_tar(tmp_path: Path):
    corrupt = tmp_path / "whl" / "rec" / "en" / "broken_model.tar"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_bytes(b"not a complete tar archive")

    removed = remove_corrupt_paddleocr_archives(tmp_path)

    assert removed == [corrupt]
    assert not corrupt.exists()


def test_remove_corrupt_paddleocr_archives_keeps_valid_tar(tmp_path: Path):
    valid = tmp_path / "whl" / "rec" / "en" / "valid_model.tar"
    valid.parent.mkdir(parents=True)
    payload = tmp_path / "model.txt"
    payload.write_text("model data")
    with tarfile.open(valid, "w") as tar_obj:
        tar_obj.add(payload, arcname="model.txt")

    removed = remove_corrupt_paddleocr_archives(tmp_path)

    assert removed == []
    assert valid.exists()
