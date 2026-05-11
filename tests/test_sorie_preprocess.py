import json

import numpy as np
import pytest

try:
    import cv2
except ImportError as exc:
    cv2 = None
    CV2_IMPORT_ERROR = exc
else:
    CV2_IMPORT_ERROR = None

if CV2_IMPORT_ERROR is None:
    from app.pipeline.preprocess import preprocess_document_pages, preprocess_page
    from app.pipeline.quality import assess_image_quality

pytestmark = pytest.mark.skipif(
    CV2_IMPORT_ERROR is not None,
    reason=f"OpenCV is unavailable in this environment: {CV2_IMPORT_ERROR}",
)


def _write_distant_receipt(path):
    canvas = np.full((2200, 2200, 3), 255, dtype=np.uint8)
    # Simulate a receipt photographed from far away: useful text is a small
    # centered region on an already-large image, so width-only resizing will
    # not help unless the content is cropped before upscaling.
    cv2.rectangle(canvas, (850, 650), (1350, 1350), (245, 245, 245), -1)
    for row, text in enumerate(
        [
            "SROIE RECEIPT",
            "DATE 11/01/2019",
            "ITEM QTY AMOUNT",
            "1072 1 80.00",
            "TOTAL 80.00",
        ]
    ):
        cv2.putText(
            canvas,
            text,
            (900, 760 + row * 95),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(path), canvas)


def test_sorie_preprocess_crops_and_upscales_distant_receipt(tmp_path):
    source = tmp_path / "page_0001.png"
    basic_out = tmp_path / "basic.png"
    sorie_out = tmp_path / "sorie.png"
    _write_distant_receipt(source)

    preprocess_page(source, basic_out, mode="basic")
    preprocess_page(source, sorie_out, mode="sorie")

    basic = cv2.imread(str(basic_out), cv2.IMREAD_GRAYSCALE)
    sorie = cv2.imread(str(sorie_out), cv2.IMREAD_GRAYSCALE)

    assert basic is not None
    assert sorie is not None
    assert sorie.shape[0] > basic.shape[0]
    assert sorie.shape[1] < basic.shape[1]


def test_preprocess_document_pages_supports_sroie_alias(tmp_path):
    pages_dir = tmp_path / "pages"
    processed_dir = tmp_path / "processed"
    pages_dir.mkdir()
    _write_distant_receipt(pages_dir / "page_0001.png")
    (pages_dir / "manifest.json").write_text(
        json.dumps([{"page": 1, "source": "ocr", "artifact": "page_0001.png"}]),
        encoding="utf-8",
    )

    outputs = preprocess_document_pages(pages_dir, processed_dir, mode="sroie")

    assert outputs == [processed_dir / "sroie" / "page_0001.png"]
    assert outputs[0].exists()


def test_quality_flags_small_document_content(tmp_path):
    source = tmp_path / "page_0001.png"
    _write_distant_receipt(source)

    report = assess_image_quality(source)

    assert report["content_bbox"] is not None
    assert report["content_area_ratio"] < 0.20
    assert "document_content_is_small" in report["warnings"]


def _write_plain_page(path, *, width, height):
    canvas = np.full((height, width, 3), 255, dtype=np.uint8)
    cv2.putText(
        canvas,
        "OCR SCALE TEST",
        (25, max(55, height // 2)),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.imwrite(str(path), canvas)


def test_basic_preprocess_upscales_very_small_images_by_2x(tmp_path):
    source = tmp_path / "small.png"
    output = tmp_path / "small_processed.png"
    _write_plain_page(source, width=800, height=500)

    preprocess_page(source, output, mode="basic")

    processed = cv2.imread(str(output), cv2.IMREAD_GRAYSCALE)
    assert processed is not None
    assert processed.shape == (500 * 2 + 36, 800 * 2 + 36)


def test_basic_preprocess_upscales_medium_images_by_1_5x(tmp_path):
    source = tmp_path / "medium.png"
    output = tmp_path / "medium_processed.png"
    _write_plain_page(source, width=1200, height=500)

    preprocess_page(source, output, mode="basic")

    processed = cv2.imread(str(output), cv2.IMREAD_GRAYSCALE)
    assert processed is not None
    assert processed.shape == (int(500 * 1.5) + 36, int(1200 * 1.5) + 36)


def test_basic_preprocess_leaves_large_images_at_original_scale(tmp_path):
    source = tmp_path / "large.png"
    output = tmp_path / "large_processed.png"
    _write_plain_page(source, width=1900, height=500)

    preprocess_page(source, output, mode="basic")

    processed = cv2.imread(str(output), cv2.IMREAD_GRAYSCALE)
    assert processed is not None
    assert processed.shape == (500 + 36, 1900 + 36)
