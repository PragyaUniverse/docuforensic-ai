"""PDF structure and metadata forensics, plus metadata checks for images.

The main check here is the text layer against the rendered pixels. A digital PDF carries two
versions of its content: what a parser reads and what a person sees. OCR on the render lets us
compare them region by region. Disagreement is invisible to a text-only pipeline.
"""
from __future__ import annotations

import io
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
import pikepdf
import pymupdf
from PIL import ExifTags, Image
from rapidfuzz import fuzz

from config.settings import settings
from models.schemas import (
    BBox,
    DocFormat,
    Document,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingCategory,
    Severity,
    TextSource,
    ValueType,
    new_id,
)
from pipeline.common import (
    crop_evidence,
    is_processable,
    load_page_rgb,
    log,
    make_finding,
    measurement,
    save_crop,
    save_heatmap,
    union_bbox,
)
from pipeline.layout import group_lines
from pipeline.normalize import norm_money
from pipeline.ocr import rapid_lines

BENIGN_PDF = [
    "PDF tools sometimes rewrite content without changing its meaning, for example when optimizing or signing.",
    "Form-filling and e-signature software can add content in later revisions.",
]
VERIFY_PDF = [
    "Ask the issuer for a newly generated copy and compare the two.",
    "Check the value against the issuer's system of record.",
]
# Tools commonly used to edit existing PDFs by hand. Presence is a fact, not an accusation.
EDITOR_RE = re.compile(
    r"(photoshop|gimp|illustrator|inkscape|acrobat\s+(pro|standard)|foxit\s*phantom|pdf\s*xchange|ilovepdf|smallpdf|"
    r"sejda|pdfescape|nitro|pdfelement|wondershare|pdf-?xchange|canva|libreoffice\s+draw|pdfsam|pypdf|pikepdf|pymupdf|mupdf)",
    re.IGNORECASE,
)
_CONFUSABLE = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1", "|": "1", "S": "5", "B": "8", "Z": "2", "—": "-", "–": "-"})


def _comparable(text: str) -> str:
    return re.sub(r"[\s.,:;'\"`_\-/\\()]+", "", text).translate(_CONFUSABLE).casefold()


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text.translate(_CONFUSABLE))


# ----------------------------------------------------------------------------- text vs pixels
def _text_layer_words(pdf_page: pymupdf.Page):
    from models.schemas import Word

    scale = settings.render_dpi / 72.0
    out = []
    for w in pdf_page.get_text("words", sort=True):
        text = (w[4] or "").strip()
        if text:
            out.append(Word(text=text, confidence=1.0, bbox=BBox(x0=w[0] * scale, y0=w[1] * scale, x1=w[2] * scale, y1=w[3] * scale), page=pdf_page.number, source=TextSource.text_layer))
    return out


def _overlap(a: BBox, b: BBox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    if w <= 0 or h <= 0 or a.area <= 0:
        return 0.0
    return w * h / a.area


def _record_visible_value(doc: Document, page_index: int, row: dict) -> None:
    """A reader sees the rendered value, so keep it beside the text-layer value of the same field.
    Later stages then see both, with their sources, and neither is silently treated as true."""
    box = row["bbox"]
    for f in list(doc.fields):
        if f.page != page_index or f.source != TextSource.text_layer or _overlap(f.bbox, box) < 0.5:
            continue
        visible = _visible_value(f.value_type, row["ocr"])
        if not visible or _comparable(visible) == _comparable(f.value_raw):
            continue
        doc.fields.append(
            f.model_copy(update={
                "id": new_id("fld"), "value_raw": visible, "value_norm": norm_money(visible) if f.value_type == ValueType.money else visible,
                "confidence": round(float(row["ocr_conf"]), 3), "source": TextSource.ocr_rapid, "bbox": box,
                "label_raw": f"{f.label_raw or f.name} (as visible in the rendered page)",
            })
        )
        if f.name not in doc.duplicated_fields:
            doc.duplicated_fields = sorted({*doc.duplicated_fields, f.name})


def _visible_value(vtype: ValueType, text: str) -> str | None:
    if vtype == ValueType.money:
        m = re.search(r"\d[\d,]*(?:\.\d{1,2})?", text)
        return m.group(0) if m else None
    return text.strip() or None


def text_vs_pixels(doc: Document, pdf: pymupdf.Document, page_index: int, workdir: Path) -> list[Finding]:
    img = load_page_rgb(doc, page_index)
    layer = _text_layer_words(pdf[page_index])
    if len(layer) < 3:
        return []
    ocr = rapid_lines(img)
    if ocr is None:
        doc.metadata.setdefault("forensics_failures", []).append("text-vs-pixels: no OCR engine available")
        return []
    findings: list[Finding] = []
    compared = 0
    mismatches = 0
    used_layer: set[int] = set()
    rows: list[dict] = []
    for ln in ocr:
        if abs(ln.tilt_deg) > 20 or sum(c.isalnum() for c in ln.text) < 3:
            continue
        inside = [i for i, w in enumerate(layer) if _overlap(w.bbox, ln.bbox) > 0.5]
        if not inside:
            continue
        used_layer.update(inside)
        layer_text = " ".join(layer[i].text for i in sorted(inside, key=lambda k: layer[k].bbox.x0))
        a, b = _comparable(ln.text), _comparable(layer_text)
        compared += 1
        ratio = fuzz.ratio(a, b)
        da, db = _digits(ln.text), _digits(layer_text)
        digit_diff = bool(da or db) and da != db
        if ratio >= 92 and not digit_diff:
            continue
        # OCR makes mistakes, so low-confidence lines and tiny differences carry little weight.
        if ln.confidence < 0.8:
            continue
        if digit_diff or ratio < 80:
            mismatches += 1
            rows.append({"ocr": ln.text, "layer": layer_text, "ratio": ratio, "ocr_conf": ln.confidence, "digit_diff": digit_diff, "bbox": ln.bbox, "words": inside})

    # Text-layer words nothing visible accounts for: hidden or covered text.
    hidden = [i for i, w in enumerate(layer) if i not in used_layer and sum(c.isalnum() for c in w.text) >= 2]
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    invisible = []
    for i in hidden:
        b = layer[i].bbox
        crop = gray[int(max(b.y0, 0)) : int(b.y1) + 1, int(max(b.x0, 0)) : int(b.x1) + 1]
        if crop.size and int(crop.max()) - int(crop.min()) < 30:
            invisible.append(i)

    def confidence_of(row: dict) -> float:
        base = 0.93 if row["digit_diff"] else 0.75
        return min(0.97, base * (0.6 + 0.4 * row["ocr_conf"]))

    heat = np.zeros(gray.shape, dtype=np.float32)
    for row in rows:
        b = row["bbox"]
        heat[int(b.y0) : int(b.y1) + 1, int(b.x0) : int(b.x1) + 1] = 0.9
    for i in invisible:
        b = layer[i].bbox
        heat[int(max(b.y0, 0)) : int(b.y1) + 1, int(max(b.x0, 0)) : int(b.x1) + 1] = 0.9
    uri = save_heatmap(heat, workdir, doc, "text_vs_pixels", page_index) if rows or invisible else None

    for row in rows[:6]:
        box = row["bbox"]
        _record_visible_value(doc, page_index, row)
        crop = save_crop(img, box, workdir, doc, f"tvp_p{page_index}_{int(box.x0)}_{int(box.y0)}", margin=16)
        findings.append(
            make_finding(
                doc, "pdf.text_vs_pixels", "Visible text differs from the PDF text layer",
                f"A person reading the page sees '{row['ocr']}', but the PDF text layer says '{row['layer']}'. "
                "A system that reads only the text layer would take in the second value.",
                category=FindingCategory.structural, severity=Severity.medium,
                confidence=confidence_of(row), page=page_index, bbox=box,
                evidence=[
                    EvidenceItem(kind=EvidenceKind.raw_value, label="Text-layer vs OCR comparison", doc_id=doc.id, page=page_index, bbox=box, data={"text_layer": row["layer"], "rendered_ocr": row["ocr"], "similarity": round(float(row["ratio"]), 1), "ocr_confidence": round(row["ocr_conf"], 3), "digits_differ": row["digit_diff"]}),
                    crop_evidence("Rendered region", crop, doc, page_index, box),
                    EvidenceItem(kind=EvidenceKind.heatmap, label="Mismatch map", uri=uri, doc_id=doc.id, page=page_index),
                ],
                benign=["OCR misread the rendered text. Check the crop by eye.", *BENIGN_PDF],
                verify=VERIFY_PDF,
            )
        )
    if invisible:
        groups: dict[int, list[int]] = {}
        for i in invisible:
            groups.setdefault(int(layer[i].bbox.y0 // 30), []).append(i)
        for items in list(groups.values())[:4]:
            box = union_bbox([layer[i].bbox for i in items])
            text = " ".join(layer[i].text for i in items)
            findings.append(
                make_finding(
                    doc, "pdf.text_vs_pixels", "Text layer holds words that aren't visible",
                    f"The PDF text layer contains '{text}' here, but nothing is visible in the rendered page. "
                    "Covered or hidden text can be left behind when a value is replaced.",
                    category=FindingCategory.structural, severity=Severity.medium,
                    confidence=0.85, page=page_index, bbox=box,
                    evidence=[
                        EvidenceItem(kind=EvidenceKind.raw_value, label="Invisible text-layer content", doc_id=doc.id, page=page_index, bbox=box, data={"text_layer": text}),
                        EvidenceItem(kind=EvidenceKind.heatmap, label="Mismatch map", uri=uri, doc_id=doc.id, page=page_index),
                    ],
                    benign=["Accessibility tags or hidden OCR layers can add invisible text.", *BENIGN_PDF],
                    verify=VERIFY_PDF,
                )
            )
    doc.metadata.setdefault("text_vs_pixels", {})[str(page_index)] = {"lines_compared": compared, "mismatches": mismatches, "invisible_words": len(invisible)}
    return findings


# ------------------------------------------------------------------------ incremental updates
def incremental_update(doc: Document, raw: bytes, pdf: pymupdf.Document, workdir: Path) -> list[Finding]:
    """Saved revisions stay inside the file. Render the earlier one and diff it against the final."""
    eofs = [m.end() for m in re.finditer(rb"%%EOF", raw)]
    xrefs = len(re.findall(rb"(?:^|[\r\n])startxref", raw))
    if len(eofs) < 2:
        return []
    # A linearized file legitimately has two %%EOF markers, with the first near the start.
    linearized = b"/Linearized" in raw[:2048]
    if linearized and len(eofs) == 2 and eofs[0] < len(raw) * 0.5:
        return []
    revisions = len(eofs)
    prev_end = eofs[-2]
    tail_bytes = len(raw) - prev_end
    findings: list[Finding] = []
    changed: list[tuple[int, BBox, float]] = []
    prev = None
    try:
        prev = pymupdf.open(stream=raw[:prev_end], filetype="pdf")
        zoom = settings.render_dpi / 72.0
        for i in range(min(prev.page_count, len(doc.pages))):
            pix = prev[i].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            before = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
            after = load_page_rgb(doc, i)
            if before.shape != after.shape:
                continue
            diff = cv2.absdiff(before, after).max(axis=2)
            mask = diff > 24
            if mask.sum() < 20:
                continue
            ys, xs = np.nonzero(cv2.dilate(mask.astype(np.uint8), np.ones((9, 9), np.uint8)))
            changed.append((i, BBox(x0=float(xs.min()), y0=float(ys.min()), x1=float(xs.max() + 1), y1=float(ys.max() + 1)), float(mask.mean())))
            save_heatmap(np.clip(cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 3) * 3, 0, 1), workdir, doc, "revision_diff", i)
    except Exception as exc:
        log.info("earlier revision could not be rendered: %s", type(exc).__name__)
    finally:
        if prev is not None:
            prev.close()

    data = {"revisions": revisions, "eof_offsets": eofs, "startxref_count": xrefs, "last_update_bytes": tail_bytes, "file_bytes": len(raw)}
    if changed:
        for i, box, share in changed[:4]:
            img = load_page_rgb(doc, i)
            crop = save_crop(img, box, workdir, doc, f"revision_p{i}_{int(box.x0)}_{int(box.y0)}", margin=16)
            findings.append(
                make_finding(
                    doc, "pdf.incremental_update", "This area changed in a later saved revision of the PDF",
                    f"The file contains {revisions} saved revisions. Rendering the previous revision and comparing it with the final one "
                    f"shows visible changes here. The last update added {tail_bytes} bytes at offset {prev_end}.",
                    category=FindingCategory.structural, severity=Severity.medium,
                    confidence=0.9, page=i, bbox=box,
                    evidence=[
                        measurement("PDF revision history", doc, i, box, changed_pixel_share=share, **data),
                        crop_evidence("Region in the final revision", crop, doc, i, box),
                    ],
                    benign=BENIGN_PDF, verify=VERIFY_PDF,
                )
            )
    else:
        findings.append(
            make_finding(
                doc, "pdf.incremental_update", "The PDF was saved more than once",
                f"The file contains {revisions} saved revisions, with no visible change found between the last two. "
                "This records the file's history and doesn't by itself mean anything was altered.",
                category=FindingCategory.structural, confidence=0.4,
                evidence=[measurement("PDF revision history", doc, None, None, **data)],
                benign=BENIGN_PDF, verify=VERIFY_PDF,
            )
        )
    return findings


# ------------------------------------------------------------------------------ overlay objects
def overlay_objects(doc: Document, pdf: pymupdf.Document, workdir: Path) -> list[Finding]:
    findings: list[Finding] = []
    scale = settings.render_dpi / 72.0
    for page_index in range(min(pdf.page_count, len(doc.pages))):
        page = pdf[page_index]
        counts = {}
        try:
            contents = page.get_contents()
            counts["content_streams"] = len(contents)
        except Exception:
            contents = []
        # Later paint over earlier text: a fill or image that covers text drawn before it.
        covers: list[tuple[pymupdf.Rect, str]] = []
        try:
            log_entries = page.get_bboxlog()
            seen_text: list[pymupdf.Rect] = []
            for op, rect in log_entries:
                r = pymupdf.Rect(rect)
                if op in ("fill-text", "stroke-text", "ignore-text"):
                    seen_text.append(r)
                elif op in ("fill-path", "fill-image", "fill-imgmask", "fill-shade"):
                    if r.is_empty or abs(r) >= 0.6 * abs(page.rect):
                        continue
                    hidden = [t for t in seen_text if abs(t & r) >= 0.5 * max(abs(t), 0.1)]
                    if hidden:
                        covers.append((r, op))
        except Exception as exc:
            log.info("bbox log unavailable: %s", type(exc).__name__)

        # Merge heavily overlapping cover boxes.
        unique: list[tuple[pymupdf.Rect, str]] = []
        for r, op in covers:
            if not any(abs(r & u[0]) >= 0.8 * abs(r) for u in unique):
                unique.append((r, op))
        # A table's row shading painted after its text would repeat; only few covers are local edits.
        if 0 < len(unique) <= 6:
            img = load_page_rgb(doc, page_index)
            for r, op in unique:
                box = BBox(x0=r.x0 * scale, y0=r.y0 * scale, x1=r.x1 * scale, y1=r.y1 * scale)
                crop = save_crop(img, box, workdir, doc, f"overlay_p{page_index}_{int(box.x0)}_{int(box.y0)}", margin=16)
                findings.append(
                    make_finding(
                        doc, "pdf.overlay_object", "An object was painted over existing text",
                        f"The page's drawing order paints a {'picture' if 'image' in op else 'filled shape'} on top of text that was drawn earlier, "
                        "which hides that text from a reader while it stays in the file.",
                        category=FindingCategory.structural, severity=Severity.medium,
                        confidence=0.82, page=page_index, bbox=box,
                        evidence=[
                            measurement("Drawing order", doc, page_index, box, operator=op, content_streams=counts.get("content_streams", 0)),
                            crop_evidence("Covered region", crop, doc, page_index, box),
                        ],
                        benign=["Some PDF generators draw backgrounds out of order.", "Redaction tools intentionally cover text."],
                        verify=VERIFY_PDF,
                    )
                )
        # Annotations and form widgets are separate layers that display over the page.
        try:
            annots = list(page.annots() or [])
            widgets = list(page.widgets() or [])
        except Exception:
            annots, widgets = [], []
        for annot in annots[:6]:
            kind = annot.type[1] if annot.type else "annotation"
            if kind in ("Link",):
                continue
            r = annot.rect
            box = BBox(x0=r.x0 * scale, y0=r.y0 * scale, x1=r.x1 * scale, y1=r.y1 * scale)
            info = annot.info or {}
            findings.append(
                make_finding(
                    doc, "pdf.overlay_object", f"The page has a {kind} annotation on it",
                    f"A {kind} annotation sits on top of the page content. Text it displays isn't part of the page itself.",
                    category=FindingCategory.structural, confidence=0.75 if kind in ("FreeText", "Stamp", "Square") else 0.5,
                    page=page_index, bbox=box,
                    evidence=[measurement("Annotation", doc, page_index, box, annotation_type=kind, content=(info.get("content") or "")[:120], title=(info.get("title") or "")[:60])],
                    benign=["Reviewers and form tools add comments and stamps legitimately."],
                    verify=VERIFY_PDF,
                )
            )
        for widget in widgets[:8]:
            r = widget.rect
            box = BBox(x0=r.x0 * scale, y0=r.y0 * scale, x1=r.x1 * scale, y1=r.y1 * scale)
            findings.append(
                make_finding(
                    doc, "pdf.overlay_object", "The page has an editable form field",
                    f"Form field '{widget.field_name}' holds '{(widget.field_value or '')[:60]}'. Its value can be changed without altering the page.",
                    category=FindingCategory.structural, confidence=0.35, page=page_index, bbox=box,
                    evidence=[measurement("Form field", doc, page_index, box, field=str(widget.field_name), value=str(widget.field_value or "")[:120])],
                    benign=["Fillable forms are common."], verify=VERIFY_PDF,
                )
            )
    return findings


# ----------------------------------------------------------------------------------- font names
def pdf_font_outliers(doc: Document, pdf: pymupdf.Document, workdir: Path) -> list[Finding]:
    """Exact font names from the file: a value whose font appears almost nowhere else on the page."""
    findings: list[Finding] = []
    scale = settings.render_dpi / 72.0
    for page_index in range(min(pdf.page_count, len(doc.pages))):
        spans = []
        try:
            blocks = pdf[page_index].get_text("dict")["blocks"]
        except Exception:
            continue
        for block in blocks:
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if text:
                        spans.append((span["font"], round(span["size"], 1), text, pymupdf.Rect(span["bbox"])))
        if len(spans) < 8:
            continue
        counts: dict[str, int] = {}
        for font, _, text, _ in spans:
            counts[font] = counts.get(font, 0) + len(text)
        total = sum(counts.values())
        rare = {f for f, c in counts.items() if c / total <= 0.06 and c <= 60}
        for font, size, text, rect in spans:
            if font not in rare or not any(ch.isdigit() for ch in text):
                continue
            box = BBox(x0=rect.x0 * scale, y0=rect.y0 * scale, x1=rect.x1 * scale, y1=rect.y1 * scale)
            img = load_page_rgb(doc, page_index)
            crop = save_crop(img, box, workdir, doc, f"pdffont_p{page_index}_{int(box.x0)}_{int(box.y0)}", margin=16)
            findings.append(
                make_finding(
                    doc, "visual.font_consistency", "This value uses a font that's rare on the page",
                    f"'{text}' is set in {font} ({size}pt). That font makes up only {100 * counts[font] / total:.1f}% of the characters on this page.",
                    category=FindingCategory.structural, confidence=0.72, page=page_index, bbox=box,
                    evidence=[
                        measurement("Embedded font usage", doc, page_index, box, font=font, size_pt=size, share_of_page_chars=counts[font] / total, fonts_on_page=len(counts)),
                        crop_evidence("Value", crop, doc, page_index, box),
                    ],
                    benign=["Templates may set amounts or headings in a separate font."],
                    verify=VERIFY_PDF,
                )
            )
    return findings[:6]


# ------------------------------------------------------------------------------------- metadata
def _parse_pdf_date(value: str | None) -> datetime | None:
    if not value:
        return None
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([+\-Z])?(\d{2})?'?(\d{2})?", str(value))
    if not m:
        return None
    y, mo, d, hh, mm, ss = (int(m.group(i) or default) for i, default in zip(range(1, 7), (0, 1, 1, 0, 0, 0)))
    try:
        tz = UTC
        if m.group(7) in ("+", "-") and m.group(8):
            offset = timedelta(hours=int(m.group(8)), minutes=int(m.group(9) or 0))
            tz = timezone(offset if m.group(7) == "+" else -offset)
        return datetime(y, mo, d, hh, mm, ss, tzinfo=tz)
    except ValueError:
        return None


def pdf_metadata(doc: Document, source: Path, pdf: pymupdf.Document) -> list[Finding]:
    findings: list[Finding] = []
    info: dict[str, str] = {}
    xmp: dict[str, str] = {}
    try:
        with pikepdf.open(source) as pk:
            for key, value in (pk.docinfo or {}).items():
                info[str(key).lstrip("/")] = str(value)
            try:
                with pk.open_metadata() as meta:
                    for key in ("xmp:CreatorTool", "pdf:Producer", "xmp:CreateDate", "xmp:ModifyDate"):
                        if key in meta:
                            xmp[key] = str(meta[key])
            except Exception:
                pass
    except Exception:
        for key, value in (pdf.metadata or {}).items():
            if value:
                info[{"producer": "Producer", "creator": "Creator", "creationDate": "CreationDate", "modDate": "ModDate"}.get(key, key)] = str(value)
    doc.metadata.setdefault("pdf", {}).update({"info": info, "xmp": xmp})

    producer = info.get("Producer", "")
    creator = info.get("Creator", "")
    created = _parse_pdf_date(info.get("CreationDate"))
    modified = _parse_pdf_date(info.get("ModDate"))

    # Producer: the software that wrote the file. Creator: the software that first authored it.
    if producer and creator:
        editor_p = EDITOR_RE.search(producer)
        same_family = _family(producer) == _family(creator)
        if editor_p and not EDITOR_RE.search(creator) and not same_family:
            findings.append(
                make_finding(
                    doc, "pdf.producer_mismatch", "The PDF was last written by different software from the one that created it",
                    f"Metadata says the document was created by '{creator}', but the file was written by '{producer}', a tool that can edit existing PDFs.",
                    category=FindingCategory.metadata, confidence=0.65,
                    evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="PDF metadata", doc_id=doc.id, data={"creator": creator, "producer": producer})],
                    benign=["Many organisations convert or optimize PDFs before sending them.", *BENIGN_PDF],
                    verify=VERIFY_PDF,
                )
            )
    if xmp.get("xmp:CreatorTool") and creator and _family(xmp["xmp:CreatorTool"]) != _family(creator):
        findings.append(
            make_finding(
                doc, "pdf.producer_mismatch", "PDF metadata records disagree about the creating software",
                f"The document info says '{creator}', while XMP metadata says '{xmp['xmp:CreatorTool']}'.",
                category=FindingCategory.metadata, confidence=0.5,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="PDF metadata", doc_id=doc.id, data={"info_creator": creator, "xmp_creator_tool": xmp["xmp:CreatorTool"]})],
                benign=BENIGN_PDF, verify=VERIFY_PDF,
            )
        )
    if created and modified and modified - created > timedelta(minutes=2):
        findings.append(
            make_finding(
                doc, "metadata.pdf_dates", "The PDF was modified after it was created",
                f"Metadata shows creation at {created.isoformat()} and modification at {modified.isoformat()}, {_human(modified - created)} later.",
                category=FindingCategory.metadata, confidence=0.5,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="PDF dates", doc_id=doc.id, data={"created": created.isoformat(), "modified": modified.isoformat(), "seconds_between": int((modified - created).total_seconds())})],
                benign=["Documents are often re-saved or signed after creation.", *BENIGN_PDF],
                verify=VERIFY_PDF,
            )
        )
    elif created and modified and modified < created - timedelta(minutes=2):
        findings.append(
            make_finding(
                doc, "metadata.pdf_dates", "The PDF's modification date is earlier than its creation date",
                f"Metadata shows creation at {created.isoformat()} but modification at {modified.isoformat()}.",
                category=FindingCategory.metadata, confidence=0.5,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="PDF dates", doc_id=doc.id, data={"created": created.isoformat(), "modified": modified.isoformat()})],
                benign=["Clock differences between systems."], verify=VERIFY_PDF,
            )
        )
    return findings


def _family(name: str) -> str:
    m = re.match(r"[A-Za-z]+", name.strip())
    return (m.group(0) if m else name).casefold()


def _human(delta: timedelta) -> str:
    s = int(delta.total_seconds())
    if s >= 86400:
        return f"{s // 86400} day(s)"
    if s >= 3600:
        return f"{s // 3600} hour(s)"
    return f"{max(s // 60, 1)} minute(s)"


def image_metadata(doc: Document, source: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        with Image.open(source) as im:
            exif = im.getexif()
            tags = {ExifTags.TAGS.get(k, str(k)): v for k, v in exif.items()} if exif else {}
            try:
                sub = exif.get_ifd(0x8769) if exif else {}
                tags.update({ExifTags.TAGS.get(k, str(k)): v for k, v in sub.items()})
            except Exception:
                pass
            extra = {k: str(v)[:120] for k, v in im.info.items() if k.lower() in ("software", "comment", "creation time", "author")}
    except Exception:
        return findings
    clean = {k: (v.decode("latin-1", "ignore") if isinstance(v, bytes) else v) for k, v in tags.items()}
    keep = {k: str(clean[k])[:120] for k in ("Software", "Make", "Model", "DateTime", "DateTimeOriginal", "DateTimeDigitized", "ProcessingSoftware") if k in clean}
    doc.metadata["exif"] = {**keep, **extra}

    software = keep.get("Software") or keep.get("ProcessingSoftware") or extra.get("Software") or extra.get("software") or ""
    if software and EDITOR_RE.search(software):
        findings.append(
            make_finding(
                doc, "metadata.exif", "Image metadata names image-editing software",
                f"The file's metadata names '{software}' as the software that last wrote it.",
                category=FindingCategory.metadata, confidence=0.6,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="Image metadata", doc_id=doc.id, data=doc.metadata["exif"])],
                benign=["Scans are sometimes cropped or rotated in an editor before upload."],
                verify=["Ask for the original scan or a copy from the issuer."],
            )
        )
    original, changed = keep.get("DateTimeOriginal"), keep.get("DateTime")
    if original and changed and original != changed:
        findings.append(
            make_finding(
                doc, "metadata.exif", "Image was saved after it was captured",
                f"The capture time is {original}, while the last save time is {changed}.",
                category=FindingCategory.metadata, confidence=0.35,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="Image metadata", doc_id=doc.id, data=doc.metadata["exif"])],
                benign=["Phones and scanners may rewrite the file when rotating it."],
                verify=["Ask for the original capture."],
            )
        )
    return findings


def analyze_pdf(doc: Document, source_path: Path, workdir: Path) -> list[Finding]:
    if not is_processable(doc):
        return []
    workdir = Path(workdir)
    source_path = Path(source_path)
    findings: list[Finding] = []
    if doc.format in (DocFormat.png, DocFormat.jpg):
        try:
            return image_metadata(doc, source_path)
        except Exception as exc:
            doc.metadata.setdefault("forensics_failures", []).append(f"image metadata: {type(exc).__name__}")
            return []
    if doc.format not in (DocFormat.digital_pdf, DocFormat.scanned_pdf):
        return []
    try:
        raw = source_path.read_bytes()
        pdf = pymupdf.open(stream=io.BytesIO(raw).getvalue(), filetype="pdf")
    except Exception as exc:
        doc.metadata.setdefault("forensics_failures", []).append(f"PDF structure: {type(exc).__name__}")
        return []
    try:
        steps = [
            ("incremental update", lambda: incremental_update(doc, raw, pdf, workdir)),
            ("overlay objects", lambda: overlay_objects(doc, pdf, workdir)),
            ("metadata", lambda: pdf_metadata(doc, source_path, pdf)),
            ("font names", lambda: pdf_font_outliers(doc, pdf, workdir)),
        ]
        for page in doc.pages:
            steps.append((f"text vs pixels p{page.index + 1}", lambda p=page.index: text_vs_pixels(doc, pdf, p, workdir)))
        for name, step in steps:
            try:
                findings.extend(step())
            except Exception as exc:
                log.warning("%s failed: %s", name, type(exc).__name__)
                doc.metadata.setdefault("forensics_failures", []).append(f"{name}: {type(exc).__name__}")
    finally:
        pdf.close()
    return findings


__all__ = ["analyze_pdf", "group_lines"]
