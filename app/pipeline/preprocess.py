from pathlib import Path
import json
import cv2


def preprocess_page(input_path: Path, output_path: Path, mode: str = "basic") -> None:
    """
    Preprocess one page using the selected mode.

    Modes:
    - basic: grayscale only
    - strong: grayscale + denoise + adaptive threshold
    """
    img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {input_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if mode == "basic":
        out = gray

    elif mode == "strong":
        den = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
        out = cv2.adaptiveThreshold(
            den,
            maxValue=255,
            adaptiveMethod=cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            thresholdType=cv2.THRESH_BINARY,
            blockSize=31,
            C=10,
        )

    else:
        raise ValueError(f"Unknown preprocess mode: {mode}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), out)


def preprocess_document_pages(pages_dir: Path, processed_dir: Path, mode: str = "basic") -> list[Path]:
    """
    Reads pages_dir/manifest.json and preprocesses ONLY OCR pages.

    Output goes to:
      processed_dir/<mode>/page_XXXX.png
    """
    manifest_path = pages_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    out_base = processed_dir / mode
    out_base.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []

    for item in manifest:
        if item.get("source") != "ocr":
            continue

        artifact = item["artifact"]
        inp = pages_dir / artifact
        out = out_base / artifact

        preprocess_page(inp, out, mode=mode)
        outputs.append(out)

    return outputs