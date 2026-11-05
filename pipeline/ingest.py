"""Submission stage: identify the real file type and render canonical page images.

Never raises for bad input. A file that can't be used comes back as a Document with
status `unsupported` or `failed` and a message a reviewer can act on.
"""
from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

from config.settings import settings
from models.schemas import DocFormat, Document, Page, ProcessingStatus, new_id
from pipeline.common import log, to_rel

pymupdf.TOOLS.mupdf_display_errors(False)
pymupdf.TOOLS.mupdf_display_warnings(False)

MAX_IMAGE_PIXELS = 80_000_000
SUPPORTED_HINT = "Supported formats are PNG, JPEG and PDF."
# Pages with at least this many text-layer words count as digital text.
DIGITAL_MIN_WORDS = 5
# A page covered this much by one image is a scan, even with a text layer on top of it.
SCAN_IMAGE_COVERAGE = 0.85


def sniff(head: bytes) -> str | None:
    """Real type from magic bytes. File extensions are not trusted."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if b"%PDF-" in head[:1024]:
        return "pdf"
    return None


def _describe_unknown(head: bytes) -> str:
    if head.startswith(b"PK\x03\x04"):
        return "a ZIP-based file such as DOCX or XLSX"
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "a legacy Office file"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "a GIF image"
    if head[:2] in (b"II", b"MM") and head[2:4] in (b"*\x00", b"\x00*"):
        return "a TIFF image"
    if head.startswith((b"RIFF",)) and head[8:12] == b"WEBP":
        return "a WebP image"
    if head.lstrip()[:5].lower() in (b"<html", b"<!doc"):
        return "an HTML page"
    return "an unrecognized file type"


def _copy_source(path: Path, doc: Document, ddir: Path, ext: str) -> None:
    src = ddir / f"source.{ext}"
    shutil.copyfile(path, src)
    doc.metadata["source_path"] = to_rel(src)


def _ingest_image(path: Path, doc: Document, ddir: Path, kind: str) -> None:
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        with Image.open(path) as probe:
            probe.verify()
        with Image.open(path) as im:
            im.load()
            info = {"mode": im.mode, "format": im.format, "size": list(im.size)}
            dpi = im.info.get("dpi")
            if dpi:
                info["dpi"] = [float(dpi[0]), float(dpi[1])]
            if kind == "jpg" and im.info.get("progressive"):
                info["progressive"] = True
            oriented = ImageOps.exif_transpose(im)
            info["exif_orientation_applied"] = oriented.size != im.size
            rgb = oriented.convert("RGB")
    except Image.DecompressionBombError:
        doc.status = ProcessingStatus.failed
        doc.status_message = "Image is too large to process safely (over 80 megapixels)."
        return
    except Exception as exc:  # truncated or corrupt: PIL raises many types here
        doc.status = ProcessingStatus.failed
        doc.status_message = f"The image file is corrupted or truncated and can't be decoded ({type(exc).__name__})."
        return

    doc.format = DocFormat.png if kind == "png" else DocFormat.jpg
    doc.metadata["image"] = info
    if min(rgb.size) < 16:
        doc.status = ProcessingStatus.failed
        doc.status_message = f"Image is too small to analyze ({rgb.size[0]}x{rgb.size[1]} pixels)."
        return
    page_path = ddir / "page_0.png"
    rgb.save(page_path, compress_level=1)
    doc.pages = [Page(index=0, width=rgb.size[0], height=rgb.size[1], image_path=to_rel(page_path))]
    doc.status = ProcessingStatus.processing


def _page_is_scan(page: pymupdf.Page) -> bool:
    """A full-page image with no text painted visibly on top of it. A background image under real
    text (letterhead, watermark) is still a digital page, and an invisible OCR layer is a scan."""
    area = abs(page.rect) or 1.0
    try:
        full_page = any(
            abs(pymupdf.Rect(info["bbox"]) & page.rect) / area >= SCAN_IMAGE_COVERAGE
            for info in page.get_image_info()
        )
        if not full_page:
            return False
        visible = sum(
            len(span.get("chars", [])) for span in page.get_texttrace()
            if span.get("type") != 3 and span.get("opacity", 1) > 0
        )
        return visible < 20
    except Exception:
        return False


def _ingest_pdf(path: Path, doc: Document, ddir: Path) -> None:
    try:
        pdf = pymupdf.open(path)
    except Exception as exc:
        doc.status = ProcessingStatus.failed
        doc.status_message = f"The PDF is corrupted and can't be opened ({type(exc).__name__})."
        return
    try:
        if pdf.needs_pass:
            doc.status = ProcessingStatus.unsupported
            doc.status_message = "The PDF is password protected. Provide an unprotected copy to analyze it."
            return
        if pdf.page_count == 0:
            doc.status = ProcessingStatus.failed
            doc.status_message = "The PDF is corrupted: no readable pages were found."
            return

        raw = path.read_bytes()
        was_repaired = bool(getattr(pdf, "is_repaired", False))
        has_eof = b"%%EOF" in raw[-2048:]
        total = pdf.page_count
        limit = min(total, settings.max_pages_per_doc)
        zoom = settings.render_dpi / 72.0
        pages: list[Page] = []
        digital_pages = 0
        scan_pages = 0
        for i in range(limit):
            try:
                page = pdf[i]
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                image_path = ddir / f"page_{i}.png"
                pix.save(image_path)
                words = page.get_text("words")
                is_scan = _page_is_scan(page)
                if is_scan:
                    scan_pages += 1
                if len(words) >= DIGITAL_MIN_WORDS and not is_scan:
                    digital_pages += 1
                pages.append(Page(index=i, width=pix.width, height=pix.height, image_path=to_rel(image_path)))
            except Exception as exc:
                log.warning("page %d render failed: %s", i, type(exc).__name__)
                doc.metadata.setdefault("unrendered_pages", []).append(i)

        doc.metadata["pdf"] = {
            "page_count": total,
            "repaired_on_open": was_repaired,
            "has_trailing_eof": has_eof,
            "digital_pages": digital_pages,
            "scan_pages": scan_pages,
        }
        if not pages:
            doc.status = ProcessingStatus.failed
            doc.status_message = "The PDF is corrupted: none of its pages could be rendered."
            return

        doc.pages = pages
        doc.format = DocFormat.digital_pdf if digital_pages * 2 >= len(pages) and digital_pages else DocFormat.scanned_pdf
        doc.status = ProcessingStatus.processing
        notes = []
        if total > limit:
            notes.append(f"Only the first {limit} of {total} pages were analyzed (page limit).")
        if doc.metadata.get("unrendered_pages"):
            notes.append(f"Pages {doc.metadata['unrendered_pages']} could not be rendered.")
        if was_repaired or not has_eof:
            notes.append("The PDF structure is damaged or truncated; content was recovered on a best-effort basis.")
        if notes:
            doc.status = ProcessingStatus.degraded
            doc.status_message = " ".join(notes)
    except Exception as exc:
        doc.status = ProcessingStatus.failed
        doc.status_message = f"The PDF could not be processed ({type(exc).__name__})."
    finally:
        pdf.close()


def ingest_file(path: Path, case_id: str, workdir: Path, filename: str | None = None) -> Document:
    path = Path(path)
    name = filename or path.name
    doc = Document(id=new_id("doc"), case_id=case_id, filename=name, sha256="", status=ProcessingStatus.failed)
    try:
        if not path.is_file():
            doc.status_message = "File not found."
            return doc
        size = path.stat().st_size
        doc.size_bytes = size
        hasher = hashlib.sha256()
        with path.open("rb") as fh:
            head = fh.read(4096)
            hasher.update(head)
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                hasher.update(chunk)
        doc.sha256 = hasher.hexdigest()
        doc.mime = mimetypes.guess_type(name)[0]
        if size == 0:
            doc.status_message = "The file is empty (0 bytes)."
            return doc
        if size > settings.max_upload_mb * 1024 * 1024:
            doc.status = ProcessingStatus.unsupported
            doc.status_message = f"The file is larger than the {settings.max_upload_mb} MB limit."
            return doc

        kind = sniff(head)
        if kind is None:
            doc.format = DocFormat.unsupported
            doc.status = ProcessingStatus.unsupported
            doc.status_message = f"This looks like {_describe_unknown(head)}. {SUPPORTED_HINT}"
            return doc

        ext = Path(name).suffix.lower().lstrip(".")
        declared = {"jpeg": "jpg"}.get(ext, ext)
        if declared and declared != kind:
            doc.metadata["extension_mismatch"] = {"extension": ext, "actual": kind}
        doc.mime = {"png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}[kind]

        ddir = Path(workdir) / doc.id
        ddir.mkdir(parents=True, exist_ok=True)
        _copy_source(path, doc, ddir, kind)
        if kind == "pdf":
            _ingest_pdf(path, doc, ddir)
        else:
            _ingest_image(path, doc, ddir, kind)
        if doc.status in (ProcessingStatus.processing, ProcessingStatus.degraded) and doc.metadata.get("extension_mismatch"):
            doc.metadata["extension_mismatch_note"] = (
                f"Extension says .{ext} but the content is {kind.upper()}; the content type was used."
            )
    except Exception as exc:  # last line of defence: ingest never takes a case down
        log.exception("ingest failed")
        doc.status = ProcessingStatus.failed
        doc.status_message = f"The file could not be read ({type(exc).__name__})."
    return doc
