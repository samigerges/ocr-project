from pathlib import Path
import json

import fitz  # PyMuPDF
from PIL import Image

from app.pipeline.router import should_use_native_text


def render_document(input_path: Path, pages_dir: Path, dpi: int = 300) -> list[Path]:
    """
    Convert input document into per-page artifacts inside pages_dir.

    For PDFs (per-page decision):
      - If native text is good: write page_XXXX.native.txt
      - Else: render page_XXXX.png (needs OCR)

    For images:
      - write page_0001.png (needs OCR)

    Always writes: pages_dir/manifest.json

    Returns:
      List of artifact paths created (txt/png files), not including manifest.json.
    """
    pages_dir.mkdir(parents=True, exist_ok=True)

    suffix = input_path.suffix.lower()
    output_paths: list[Path] = []
    manifest: list[dict] = []

    # -------------------------
    # Case 1: PDF
    # -------------------------
    if suffix == ".pdf":
        doc = fitz.open(str(input_path))

        for i in range(doc.page_count):
            page_no = i + 1
            page = doc.load_page(i)

            extracted = page.get_text("text") or ""

            # Decide: native vs OCR
            if should_use_native_text(extracted):
                out_txt = pages_dir / f"page_{page_no:04d}.native.txt"
                out_txt.write_text(extracted, encoding="utf-8")

                manifest.append({
                    "page": page_no,
                    "source": "native",
                    "artifact": out_txt.name,
                })
                output_paths.append(out_txt)
            else:
                pix = page.get_pixmap(dpi=dpi)
                out_img = pages_dir / f"page_{page_no:04d}.png"
                pix.save(str(out_img))

                manifest.append({
                    "page": page_no,
                    "source": "ocr",
                    "artifact": out_img.name,
                })
                output_paths.append(out_img)

        # Write manifest
        (pages_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return output_paths

    # -------------------------
    # Case 2: Image input
    # -------------------------
    img = Image.open(input_path).convert("RGB")
    out_img = pages_dir / "page_0001.png"
    img.save(out_img)
    output_paths.append(out_img)

    manifest.append({
        "page": 1,
        "source": "ocr",
        "artifact": out_img.name,
    })

    (pages_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return output_paths
