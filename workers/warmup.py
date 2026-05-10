import os
import tarfile

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_use_new_executor", "0")

from paddleocr import PaddleOCR

from app.pipeline.paddle_cache import remove_corrupt_paddleocr_archives

if __name__ == "__main__":
    removed = remove_corrupt_paddleocr_archives()
    for archive in removed:
        print(f"[warmup] Removed corrupt PaddleOCR cache archive: {archive}")

    print("[warmup] Initializing PaddleOCR(lang=en)...")
    try:
        PaddleOCR(use_angle_cls=True, lang="en")
    except tarfile.TarError:
        removed = remove_corrupt_paddleocr_archives()
        if not removed:
            raise
        for archive in removed:
            print(f"[warmup] Removed corrupt PaddleOCR cache archive: {archive}")
        print("[warmup] Retrying PaddleOCR initialization after cache cleanup...")
        PaddleOCR(use_angle_cls=True, lang="en")
    print("[warmup] Done. Models are cached.")
