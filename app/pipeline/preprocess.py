from pathlib import Path
import json
import cv2
import numpy as np


MIN_OCR_WIDTH = 1800


def _resize_for_ocr(gray: np.ndarray, min_width: int = MIN_OCR_WIDTH) -> np.ndarray:
    _, width = gray.shape[:2]
    if width >= min_width:
        return gray

    scale = min_width / float(width)
    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _normalize_contrast(gray: np.ndarray) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    return clahe.apply(gray)


def _deskew(gray: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(thresh)

    if coords is None:
        return gray

    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = 90 + angle
    angle = -angle

    if abs(angle) < 0.15 or abs(angle) > 8.0:
        return gray

    height, width = gray.shape[:2]
    center = (width // 2, height // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    return cv2.warpAffine(
        gray,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _trim_to_content(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return img

    x, y, w, h = cv2.boundingRect(coords)
    if w * h < gray.shape[0] * gray.shape[1] * 0.08:
        return img

    pad = max(12, int(max(gray.shape[:2]) * 0.015))
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(gray.shape[1], x + w + pad)
    y1 = min(gray.shape[0], y + h + pad)

    return img[y0:y1, x0:x1]


def _add_white_border(img: np.ndarray, size: int = 18) -> np.ndarray:
    return cv2.copyMakeBorder(
        img,
        size,
        size,
        size,
        size,
        borderType=cv2.BORDER_CONSTANT,
        value=255,
    )


def _prepare_basic(gray: np.ndarray) -> np.ndarray:
    base = _deskew(gray)
    base = _normalize_contrast(base)
    base = _resize_for_ocr(base)
    return _add_white_border(base)


def _prepare_strong(gray: np.ndarray) -> np.ndarray:
    # Keep the retry variant conservative. The previous aggressive thresholding
    # improved a few missed lines but hurt character shapes on clean typewritten
    # scans, which made OCR markedly worse.
    deskewed = _deskew(gray)
    normalized = _normalize_contrast(deskewed)
    resized = _resize_for_ocr(normalized)
    denoised = cv2.fastNlMeansDenoising(resized, None, h=8, templateWindowSize=7, searchWindowSize=21)
    blurred = cv2.GaussianBlur(denoised, (3, 3), 0)

    thresh = cv2.threshold(
        blurred,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU,
    )[1]

    return _add_white_border(thresh)


def preprocess_page(input_path: Path, output_path: Path, mode: str = "basic") -> None:
    """
    Preprocess one page using the selected mode.

    Modes:
    - basic: deskew + contrast normalization + upscale
    - strong: stronger denoise + thresholding + border cleanup
    """
    img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {input_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if mode == "basic":
        out = _prepare_basic(gray)

    elif mode == "strong":
        out = _prepare_strong(gray)

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
