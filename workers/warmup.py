import os

os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_enable_pir_api", "0")
os.environ.setdefault("FLAGS_use_new_executor", "0")

from paddleocr import PaddleOCR

if __name__ == "__main__":
    print("[warmup] Initializing PaddleOCR(lang=en)...")
    PaddleOCR(use_angle_cls=True, lang="en")
    print("[warmup] Done. Models are cached.")