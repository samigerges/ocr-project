import cv2
import numpy as np 
from pathlib import Path
from pathlib import Path
import json

def preprocess_page(input_path: Path, output_path: Path) -> None:
    """
    Safe default preprocessing:
    1) Read image
    2) Convert to grayscale
    3) Light denoise
    4) Adaptive threshold (handles uneven lighting)
    5) Save output
    """
    img = cv2.imread(str(input_path),cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(f'Could not read image: {input_path}')
    
    gray = cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)

    # light denoise (keeps edges fairly well)
    gray = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)

    # adaptive threshold
    # blockSize must be odd; C is a constant subtracted from mean
    binary = cv2.adaptiveThreshold(
        gray,
        maxValue=255,
        adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresholdType=cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), binary)


def preprocess_document_pages(pages_dir: Path, processed_dir: Path) -> list[Path]:
    """
    Reads pages_dir/manifest.json and preprocesses ONLY OCR pages (source == 'ocr').

    Returns list of processed image paths created.
    """
    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    processed_dir.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []

    for item in manifest:
        if item.get("source") != "ocr":
            continue  # native pages: skip

        artifact = item["artifact"]  # e.g. page_0001.png
        inp = pages_dir / artifact
        out = processed_dir / artifact

        preprocess_page(inp, out)
        outputs.append(out)

    return outputs