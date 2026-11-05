"""Finds handwritten values and reads them with a local vision model.

OCR stays confident even when it misreads handwriting, so its confidence can't be the trigger. The
trigger is the writing itself: printed characters sit on a straight baseline at a steady height, and
handwritten ones don't. Printed fields are never sent to the model.

Readings come from an AI model, so they always carry low confidence and ask to be checked. The field's
box comes from the ink on the page, never from the model.
"""
from __future__ import annotations

import io
import re

import cv2
import numpy as np
from PIL import Image

from llm import vision
from models.schemas import BBox, Document, Field, TextSource, ValueType
from pipeline.common import from_rel, is_processable, log
from pipeline.extract import _find_labels, _label_table, _normalize
from pipeline.forensics_visual import ink_mask
from pipeline.layout import doc_lines

# Median across a page's values. See docs/LIMITATIONS.md for how this was calibrated.
HANDWRITTEN_SCORE = 0.2
AI_READING_CONFIDENCE = 0.5


def _row_score(mask: np.ndarray) -> float | None:
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    boxes = [stats[i] for i in range(1, count) if stats[i][cv2.CC_STAT_AREA] >= 12 and stats[i][cv2.CC_STAT_HEIGHT] >= 8]
    if len(boxes) < 3:
        return None
    heights = np.array([b[cv2.CC_STAT_HEIGHT] for b in boxes], dtype=np.float32)
    bottoms = np.array([b[cv2.CC_STAT_TOP] + b[cv2.CC_STAT_HEIGHT] for b in boxes], dtype=np.float32)
    lefts = np.array([b[cv2.CC_STAT_LEFT] for b in boxes], dtype=np.float32)
    typical = max(float(np.median(heights)), 1.0)
    # A straight baseline fits a line. Slope alone doesn't count, since a scan can be slightly skewed.
    fit = np.polyval(np.polyfit(lefts, bottoms, 1), lefts) if len(set(lefts.tolist())) > 1 else bottoms
    return float(np.median(np.abs(bottoms - fit))) / typical + 0.5 * float(np.std(heights)) / typical


def handwriting_score(gray: np.ndarray) -> float:
    """How irregular the letters are, row by row: baseline wander plus height variation."""
    if gray.size == 0:
        return 0.0
    mask = ink_mask(gray).astype(np.uint8)
    inked = mask.sum(axis=1) > 0
    # Stacked printed lines would otherwise look like a wandering baseline, so score each row alone.
    edges = np.flatnonzero(np.diff(np.concatenate(([0], inked.astype(np.int8), [0]))))
    scores = [_row_score(mask[y0:y1]) for y0, y1 in zip(edges[0::2], edges[1::2], strict=True) if y1 - y0 >= 8]
    scores = [v for v in scores if v is not None]
    return float(np.mean(scores)) if scores else 0.0


def page_is_handwritten(gray: np.ndarray, fields: list[Field]) -> tuple[bool, float]:
    """One odd value can't tip a page. It takes most of the page's values looking handwritten."""
    scores = [handwriting_score(_crop(gray, f.bbox)) for f in fields]
    scores = [v for v in scores if v > 0]
    if len(scores) < 3:
        return False, 0.0
    typical = float(np.median(scores))
    return typical >= HANDWRITTEN_SCORE, typical


def _crop(gray: np.ndarray, box: BBox, pad: int = 14) -> np.ndarray:
    return gray[max(int(box.y0) - pad, 0) : int(box.y1) + pad, max(int(box.x0) - pad, 0) : int(box.x1) + pad]


def _png(gray: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(gray).save(buf, "PNG")
    return buf.getvalue()


def _same_text(a: str, b: str) -> bool:
    squish = lambda s: re.sub(r"[^0-9a-z]", "", s.casefold())  # noqa: E731
    return squish(a) == squish(b)


def _plausible(reading: str, vtype: ValueType) -> bool:
    """A reading has to look like the kind of value the label asks for."""
    if vtype in (ValueType.money, ValueType.date):
        return _normalize("", vtype, reading) is not None
    if vtype in (ValueType.id_number, ValueType.account_number):
        return any(c.isdigit() for c in reading)
    return True


def _unread_rows(doc: Document, page: int, gray: np.ndarray) -> list[tuple[str, ValueType, str, BBox]]:
    """Labelled rows with no extracted value but with ink where the value should be."""
    have = {f.name for f in doc.fields}
    table = _label_table(doc.doc_type)
    out = []
    for line in doc_lines(doc, page):
        for hit in _find_labels(line, table):
            if hit.name.startswith("!") or hit.name in have or hit.name.startswith("_"):
                continue
            label = line.span_bbox(hit.start, hit.end)
            pad = 0.9 * line.height
            x0, x1 = int(label.x1 + 10), gray.shape[1] - 40
            y0, y1 = max(int(label.y0 - pad), 0), min(int(label.y1 + pad), gray.shape[0])
            ys, xs = np.where(ink_mask(gray[y0:y1, x0:x1]))
            if len(xs) < 60:
                continue
            box = BBox(x0=x0 + int(xs.min()), y0=y0 + int(ys.min()), x1=x0 + int(xs.max()) + 1, y1=y0 + int(ys.max()) + 1)
            out.append((hit.name, hit.vtype, hit.synonym, box))
    return out


def read_handwriting(doc: Document) -> Document:
    """Re-reads handwritten values. Never raises, and without a model it says what it couldn't read."""
    if not is_processable(doc):
        return doc
    model = vision.available()
    notes: list[dict] = []
    disagreements: list[dict] = []
    for page in doc.pages:
        if page.text_source == TextSource.text_layer:
            continue  # a PDF's text layer is typed by definition
        try:
            with Image.open(from_rel(page.image_path)) as im:
                gray = np.asarray(im.convert("L"))
        except OSError as exc:
            log.warning("handwriting: page unreadable: %s", type(exc).__name__)
            continue
        fields = [f for f in doc.fields if f.page == page.index]
        handwritten, typical = page_is_handwritten(gray, fields)
        if not handwritten:
            continue
        notes.append({"page": page.index, "typical_score": round(typical, 3)})
        for field in fields:
            reading = vision.read_image(_png(_crop(gray, field.bbox))) if model else None
            notes.append({"field": field.name, "ocr_read": field.value_raw, "ai_read": reading})
            # Measured: replacing OCR with the AI reading lost accuracy (53/80 against 59/80). So OCR's
            # value stands, and a disagreement is shown to the reviewer rather than resolved here.
            if reading and _plausible(reading, field.value_type) and not _same_text(reading, field.value_raw):
                disagreements.append({"field_id": field.id, "field": field.name, "ocr_read": field.value_raw, "ai_read": reading})
            field.confidence = min(field.confidence, AI_READING_CONFIDENCE)
        for name, vtype, label, box in _unread_rows(doc, page.index, gray) if handwritten else []:
            reading = vision.read_image(_png(_crop(gray, box))) if model else None
            notes.append({"field": name, "ocr_read": None, "ai_read": reading})
            if reading and _plausible(reading, vtype):
                doc.fields.append(Field(
                    doc_id=doc.id, name=name, label_raw=label, value_raw=reading,
                    value_norm=_normalize(name, vtype, reading), value_type=vtype,
                    confidence=AI_READING_CONFIDENCE, page=page.index, bbox=box, source=TextSource.llm,
                ))
    if notes:
        doc.metadata["handwriting"] = {"model": model, "fields": notes, "disagreements": disagreements}
    return doc
