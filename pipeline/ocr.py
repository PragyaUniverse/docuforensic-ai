"""OCR stage. Text layer for digital PDFs, otherwise RapidOCR (PP-OCR models on ONNX Runtime)
with Tesseract used to recover word boundaries and as a full fallback.

RapidOCR reads lines and often drops spaces ("DateofBirth:14/03/1991"). We ask it for character
boxes and align each line against Tesseract's word boxes, which restores word boundaries and gives
tight boxes. All confidences are kept: OCR output is a measurement, never ground truth.
"""
from __future__ import annotations

import math
import re
import threading
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pymupdf
import pytesseract
from PIL import Image

from config.settings import settings
from models.schemas import BBox, Document, DocFormat, Page, ProcessingStatus, TextSource, Word
from pipeline.common import from_rel, is_processable, log, set_degraded, source_path

_engine = None
_engine_failed = False
_lock = threading.Lock()
# Lines tilted more than this are treated as watermarks or stamps, not document content.
MAX_LINE_TILT_DEG = 20.0
TESS_MIN_CONF = 60.0


@dataclass
class OcrLine:
    text: str
    confidence: float
    bbox: BBox
    tilt_deg: float
    chars: list[tuple[str, float, BBox]]  # char, confidence, box (spaces included)


def _get_engine():
    global _engine, _engine_failed
    if _engine is None and not _engine_failed:
        try:
            from rapidocr_onnxruntime import RapidOCR

            _engine = RapidOCR()
        except Exception as exc:
            _engine_failed = True
            log.warning("RapidOCR unavailable: %s", type(exc).__name__)
    return _engine


def rapid_lines(img: np.ndarray) -> list[OcrLine] | None:
    """Line-level OCR with character boxes. None means the engine isn't available."""
    engine = _get_engine()
    if engine is None:
        return None
    try:
        with _lock:
            result = engine(img, return_word_box=True)[0]
    except Exception as exc:
        log.warning("RapidOCR failed: %s", type(exc).__name__)
        return None
    lines: list[OcrLine] = []
    for item in result or []:
        quad, text, conf = item[0], item[1], float(item[2])
        xs = [p[0] for p in quad]
        ys = [p[1] for p in quad]
        tilt = math.degrees(math.atan2(quad[1][1] - quad[0][1], (quad[1][0] - quad[0][0]) or 1e-3))
        bbox = BBox(x0=min(xs), y0=min(ys), x1=max(xs), y1=max(ys))
        chars: list[tuple[str, float, BBox]] = []
        if len(item) >= 5 and len(item[3]) == len(text):
            cconfs = item[4][1] if len(item[4]) > 1 and len(item[4][1]) == len(text) else [conf] * len(text)
            for ch, box, cc in zip(text, item[3], cconfs):
                cx = [p[0] for p in box]
                cy = [p[1] for p in box]
                chars.append((ch, float(cc), BBox(x0=min(cx), y0=min(cy), x1=max(cx), y1=max(cy))))
        else:
            step = (bbox.x1 - bbox.x0) / max(len(text), 1)
            for i, ch in enumerate(text):
                chars.append((ch, conf, BBox(x0=bbox.x0 + i * step, y0=bbox.y0, x1=bbox.x0 + (i + 1) * step, y1=bbox.y1)))
        fixed = repair_text(text)
        if len(fixed) == len(text):
            chars = [(fixed[i], c[1], c[2]) for i, c in enumerate(chars)]
            text = fixed
        lines.append(OcrLine(text=text, confidence=conf, bbox=bbox, tilt_deg=tilt, chars=chars))
    return lines


def tesseract_words(img: np.ndarray) -> list[tuple[str, float, BBox]] | None:
    """Word boxes from Tesseract. None means Tesseract isn't available."""
    try:
        data = pytesseract.image_to_data(
            Image.fromarray(img), config="--psm 11", output_type=pytesseract.Output.DICT, timeout=60
        )
    except Exception as exc:
        log.warning("Tesseract failed: %s", type(exc).__name__)
        return None
    out: list[tuple[str, float, BBox]] = []
    for i, text in enumerate(data["text"]):
        text = (text or "").strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        out.append((text, conf / 100.0, BBox(x0=x, y0=y, x1=x + w, y1=y + h)))
    return out


def repair_text(text: str) -> str:
    """Fix OCR confusions that have only one sensible reading. Everything else stays as read."""
    text = text.translate(str.maketrans({"，": ",", "：": ":", "．": ".", "（": "(", "）": ")", "；": ";"}))
    # A digit zero inside a month name: 12-0ct-2026.
    return re.sub(r"(?<![A-Za-z0-9])0ct(?![a-z])|(?<=[-/\s\d])0ct(?![a-z])", "Oct", text)


def merge_fragments(lines: list[OcrLine], tess: list[tuple[str, float, BBox]]) -> list[OcrLine]:
    """The line detector can shatter one word into pieces, often where a watermark crosses it.
    When one confident Tesseract word covers several pieces, it replaces them."""
    out = list(lines)
    for text, conf, box in tess:
        if conf < 0.8 or sum(c.isalnum() for c in text) < 3:
            continue
        pieces = [ln for ln in out if _center_inside(ln.bbox, box, slack=6) and (ln.bbox.x1 - ln.bbox.x0) < (box.x1 - box.x0)]
        if len(pieces) < 2:
            continue
        step = (box.x1 - box.x0) / max(len(text), 1)
        chars = [
            (ch, conf, BBox(x0=box.x0 + i * step, y0=box.y0, x1=box.x0 + (i + 1) * step, y1=box.y1))
            for i, ch in enumerate(text)
        ]
        out = [ln for ln in out if not any(ln is q for q in pieces)]
        out.append(OcrLine(text=text, confidence=conf, bbox=box, tilt_deg=0.0, chars=chars))
    return out


def _center_inside(b: BBox, outer: BBox, slack: float = 4.0) -> bool:
    cx, cy = (b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2
    return outer.x0 - slack <= cx <= outer.x1 + slack and outer.y0 - slack <= cy <= outer.y1 + slack


def _line_to_words(line: OcrLine, tess: list[tuple[str, float, BBox]], page: int) -> list[Word]:
    """Split one OCR line into words, using Tesseract's boundaries when they align."""
    chars = [(c, conf, box) for c, conf, box in line.chars if not c.isspace()]
    if not chars:
        return []
    height = max(line.bbox.y1 - line.bbox.y0, 1.0)

    # Which Tesseract word does each character belong to?
    owner: list[int | None] = [None] * len(chars)
    inside = sorted((t for t in tess if _center_inside(t[2], line.bbox)), key=lambda t: t[2].x0)
    if inside:
        rapid_s = "".join(c for c, _, _ in chars).casefold()
        tess_s = ""
        tess_owner: list[int] = []
        for idx, (text, _, _) in enumerate(inside):
            tess_s += text.casefold()
            tess_owner += [idx] * len(text.casefold())
        sm = SequenceMatcher(None, rapid_s, tess_s, autojunk=False)
        if sm.ratio() >= 0.7:
            for block in sm.get_matching_blocks():
                for k in range(block.size):
                    owner[block.a + k] = tess_owner[block.b + k]
            last = None
            for i in range(len(owner)):
                if owner[i] is None:
                    owner[i] = last
                else:
                    last = owner[i]
            nxt = None
            for i in range(len(owner) - 1, -1, -1):
                if owner[i] is None:
                    owner[i] = nxt
                else:
                    nxt = owner[i]

    # Break where Rapid saw a space, where the Tesseract word changes, or at a wide char gap.
    spaces_after: set[int] = set()
    nonspace_i = -1
    for c, _, _ in line.chars:
        if c.isspace():
            spaces_after.add(nonspace_i)
        else:
            nonspace_i += 1

    groups: list[list[int]] = [[0]]
    for i in range(1, len(chars)):
        gap = chars[i][2].x0 - chars[i - 1][2].x1
        boundary = (
            (i - 1) in spaces_after
            or (owner[i] != owner[i - 1])
            or (all(o is None for o in owner) and gap > 0.45 * height)
        )
        if boundary:
            groups.append([i])
        else:
            groups[-1].append(i)

    used_counts: dict[int, int] = {}
    for g in groups:
        o = owner[g[0]]
        if o is not None:
            used_counts[o] = used_counts.get(o, 0) + 1

    words: list[Word] = []
    for g in groups:
        text = "".join(chars[i][0] for i in g)
        conf = float(np.mean([chars[i][1] for i in g]))
        o = owner[g[0]]
        if o is not None and used_counts.get(o) == 1:
            box = inside[o][2]  # Tesseract's box is tight on the ink
        else:
            cb = [chars[i][2] for i in g]
            box = BBox(x0=min(b.x0 for b in cb), y0=line.bbox.y0, x1=max(b.x1 for b in cb), y1=line.bbox.y1)
        words.append(Word(text=text, confidence=round(conf, 4), bbox=box, page=page, source=TextSource.ocr_rapid))
    return words


def ocr_image(img: np.ndarray, page: int = 0) -> tuple[list[Word], TextSource | None]:
    """OCR a page image. Returns words and the primary engine used."""
    lines = rapid_lines(img)
    tess = tesseract_words(img)
    if lines is None and tess is None:
        return [], None
    if lines is None:
        words = [
            Word(text=t, confidence=round(c, 4), bbox=b, page=page, source=TextSource.ocr_tesseract)
            for t, c, b in (tess or [])
            if c * 100 >= TESS_MIN_CONF and any(ch.isalnum() for ch in t)
        ]
        return words, TextSource.ocr_tesseract

    tess = tess or []
    lines = merge_fragments(lines, tess)
    kept = [ln for ln in lines if abs(ln.tilt_deg) <= MAX_LINE_TILT_DEG]
    words: list[Word] = []
    for ln in kept:
        words.extend(_line_to_words(ln, tess, page))

    # Text the line recognizer missed, if Tesseract is confident about it.
    for text, conf, box in tess:
        if conf * 100 < 75 or sum(ch.isalnum() for ch in text) < 2:
            continue
        if any(_center_inside(box, ln.bbox, slack=8) for ln in lines):
            continue
        words.append(Word(text=text, confidence=round(conf, 4), bbox=box, page=page, source=TextSource.ocr_tesseract))
    return words, TextSource.ocr_rapid


def _text_layer_words(pdf_page: pymupdf.Page, page: Page) -> list[Word]:
    scale = settings.render_dpi / 72.0
    words = []
    for w in pdf_page.get_text("words", sort=True):
        text = (w[4] or "").strip()
        if not text:
            continue
        words.append(
            Word(
                text=text,
                confidence=1.0,
                bbox=BBox(x0=w[0] * scale, y0=w[1] * scale, x1=w[2] * scale, y1=w[3] * scale),
                page=page.index,
                source=TextSource.text_layer,
            )
        )
    return words


def estimate_skew_deg(words: list[Word]) -> float:
    """Page skew, from how word centres on one text row drift. Positive is clockwise."""
    if len(words) < 6:
        return 0.0
    slopes = []
    ordered = sorted(words, key=lambda w: w.bbox.x0)
    for i, a in enumerate(ordered):
        ah = a.bbox.y1 - a.bbox.y0
        ay = (a.bbox.y0 + a.bbox.y1) / 2
        for b in ordered[i + 1 : i + 25]:
            dx = (b.bbox.x0 + b.bbox.x1) / 2 - (a.bbox.x0 + a.bbox.x1) / 2
            if dx < 40:
                continue
            dy = (b.bbox.y0 + b.bbox.y1) / 2 - ay
            if abs(dy) < 0.09 * dx + ah * 0.5:
                slopes.append(dy / dx)
    if len(slopes) < 5:
        return 0.0
    return float(math.degrees(math.atan(float(np.median(slopes)))))


def _set_page_stats(page: Page, words: list[Word], source: TextSource | None) -> None:
    page.words = words
    page.text_source = source
    if words:
        weights = np.array([max(len(w.text), 1) for w in words], dtype=float)
        page.mean_ocr_confidence = round(float(np.average([w.confidence for w in words], weights=weights)), 4)
    else:
        page.mean_ocr_confidence = None


def extract_words(doc: Document, workdir: Path) -> Document:
    if not is_processable(doc):
        return doc

    pdf = None
    if doc.format == DocFormat.digital_pdf:
        src = source_path(doc)
        try:
            pdf = pymupdf.open(src) if src else None
        except Exception:
            pdf = None

    skew: dict[str, float] = {}
    any_engine = False
    low_pages: list[int] = []
    empty_pages: list[int] = []
    try:
        for page in doc.pages:
            try:
                words: list[Word] = []
                source: TextSource | None = None
                if pdf is not None:
                    words = _text_layer_words(pdf[page.index], page)
                    source = TextSource.text_layer if words else None
                if not words:
                    with Image.open(from_rel(page.image_path)) as im:
                        img = np.asarray(im.convert("RGB"))
                    words, source = ocr_image(img, page.index)
                if source is not None:
                    any_engine = True
                _set_page_stats(page, words, source)
                skew[str(page.index)] = round(estimate_skew_deg(words), 3)
                if not words:
                    empty_pages.append(page.index)
                elif (page.mean_ocr_confidence or 0) < settings.low_ocr_confidence:
                    low_pages.append(page.index)
            except Exception as exc:
                log.warning("OCR failed on page %d: %s", page.index, type(exc).__name__)
                empty_pages.append(page.index)
    finally:
        if pdf is not None:
            pdf.close()

    doc.metadata["skew_deg"] = skew
    if not any_engine and not any(p.words for p in doc.pages):
        if empty_pages and all(p.words == [] for p in doc.pages):
            engines_ok = _get_engine() is not None
            if engines_ok:
                set_degraded(doc, "No readable text was found. The page may be blank or unreadable, so fields could not be extracted.")
            else:
                set_degraded(doc, "No OCR engine is available, so text could not be read.")
    else:
        if empty_pages:
            set_degraded(doc, f"No readable text found on page(s) {[p + 1 for p in empty_pages]}.")
        if low_pages:
            set_degraded(
                doc,
                f"OCR confidence is low on page(s) {[p + 1 for p in low_pages]}, so extracted values may be wrong and need manual checking.",
            )
    if doc.status == ProcessingStatus.processing:
        doc.status = ProcessingStatus.ok
    return doc
