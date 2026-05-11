from pathlib import Path
import json
import cv2
import numpy as np

MIN_OCR_WIDTH = 1800
OCR_DOUBLE_UPSCALE_MAX_WIDTH = 900
SORIE_MIN_RECEIPT_WIDTH = 2600
SORIE_MIN_RECEIPT_HEIGHT = 3600
SORIE_MAX_UPSCALE = 4.0

SUPPORTED_PREPROCESS_MODES = {"basic", "receipt", "strong", "sorie", "sroie"}


def _ocr_upscale_factor(width: int, min_width: int = MIN_OCR_WIDTH) -> float:
    """Choose a conservative OCR upscale multiplier for undersized images.

    OCR accuracy drops quickly when character strokes are too small. Rather than
    resizing to arbitrary dimensions, keep scaling predictable: very small pages
    get a 2x pass, while pages that are below the OCR width target get a 1.5x
    pass. Images that already meet the target are left untouched.
    """
    if width <= 0 or width >= min_width:
        return 1.0
    if width <= OCR_DOUBLE_UPSCALE_MAX_WIDTH:
        return 2.0
    return 1.5


def _resize_for_ocr(gray: np.ndarray, min_width: int = MIN_OCR_WIDTH) -> np.ndarray:
    _, width = gray.shape[:2]
    scale = _ocr_upscale_factor(width, min_width=min_width)
    if scale <= 1.0:
        return gray

    return cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)


def _resize_to_receipt_target(
    gray: np.ndarray,
    *,
    min_width: int = SORIE_MIN_RECEIPT_WIDTH,
    min_height: int = SORIE_MIN_RECEIPT_HEIGHT,
    max_scale: float = SORIE_MAX_UPSCALE,
) -> np.ndarray:
    """Upscale distant receipt crops before OCR while capping memory growth."""
    height, width = gray.shape[:2]
    if width <= 0 or height <= 0:
        return gray

    scale = max(min_width / float(width), min_height / float(height), 1.0)
    scale = min(scale, max_scale)
    if scale <= 1.01:
        return gray

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


def _trim_to_content(
    img: np.ndarray, min_content_area_ratio: float = 0.08
) -> np.ndarray:
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img

    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return img

    x, y, w, h = cv2.boundingRect(coords)
    if w * h < gray.shape[0] * gray.shape[1] * min_content_area_ratio:
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


def _prepare_receipt(gray: np.ndarray) -> np.ndarray:
    """Prepare faded thermal receipts without destroying thin characters."""
    deskewed = _deskew(gray)
    trimmed = _trim_to_content(deskewed)
    normalized = _normalize_contrast(trimmed)
    resized = _resize_for_ocr(normalized)
    denoised = cv2.fastNlMeansDenoising(
        resized, None, h=5, templateWindowSize=7, searchWindowSize=21
    )
    blurred = cv2.GaussianBlur(denoised, (0, 0), 1.0)
    sharpened = cv2.addWeighted(denoised, 1.45, blurred, -0.45, 0)
    return _add_white_border(sharpened)


def _prepare_sorie(gray: np.ndarray) -> np.ndarray:
    """Prepare SROIE/SORIE receipt photos where the receipt is small or far away.

    The standard OCR resize checks the full image width, which can miss dataset
    samples photographed from a distance: the overall canvas is already large,
    but the useful receipt/text crop is not. This variant trims to foreground
    content first, then upscales the crop toward receipt-sized OCR targets.
    """
    deskewed = _deskew(gray)
    trimmed = _trim_to_content(deskewed, min_content_area_ratio=0.005)
    normalized = _normalize_contrast(trimmed)
    upscaled = _resize_to_receipt_target(normalized)
    denoised = cv2.fastNlMeansDenoising(
        upscaled, None, h=4, templateWindowSize=7, searchWindowSize=21
    )
    blurred = cv2.GaussianBlur(denoised, (0, 0), 0.9)
    sharpened = cv2.addWeighted(denoised, 1.6, blurred, -0.6, 0)
    return _add_white_border(sharpened, size=24)


def _prepare_strong(gray: np.ndarray) -> np.ndarray:
    # Keep the retry variant conservative. The previous aggressive thresholding
    # improved a few missed lines but hurt character shapes on clean typewritten
    # scans, which made OCR markedly worse.
    deskewed = _deskew(gray)
    normalized = _normalize_contrast(deskewed)
    resized = _resize_for_ocr(normalized)
    denoised = cv2.fastNlMeansDenoising(
        resized, None, h=8, templateWindowSize=7, searchWindowSize=21
    )
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
    - basic: deskew + contrast normalization + smart 1.5x/2x upscale
    - receipt: thermal receipt crop + conservative contrast/sharpening
    - strong: stronger denoise + thresholding + border cleanup
    - sorie/sroie: crop distant receipt content + high-quality upscale
    """
    img = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Could not read image: {input_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if mode == "basic":
        out = _prepare_basic(gray)

    elif mode == "receipt":
        out = _prepare_receipt(gray)

    elif mode == "strong":
        out = _prepare_strong(gray)

    elif mode in {"sorie", "sroie"}:
        out = _prepare_sorie(gray)

    else:
        raise ValueError(f"Unknown preprocess mode: {mode}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), out)


def preprocess_document_pages(
    pages_dir: Path, processed_dir: Path, mode: str = "basic"
) -> list[Path]:
    """
    Reads pages_dir/manifest.json and preprocesses ONLY OCR pages.

    Output goes to:
      processed_dir/<mode>/page_XXXX.png

    Supported modes are basic, receipt, strong, and sorie/sroie.
    """
    if mode not in SUPPORTED_PREPROCESS_MODES:
        raise ValueError(f"Unknown preprocess mode: {mode}")

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
