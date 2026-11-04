"""Reading lines out of word boxes, with skew handled and lost OCR spaces tolerated."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from models.schemas import BBox, Document, Word


@dataclass
class LineChar:
    ch: str
    word_index: int
    frac0: float  # position inside the word, 0..1
    frac1: float


@dataclass
class Line:
    page: int
    words: list[Word]
    y: float  # deskewed centre
    height: float
    text: str = ""
    squished: str = ""
    chars: list[LineChar] = field(default_factory=list)

    @property
    def bbox(self) -> BBox:
        return BBox(
            x0=min(w.bbox.x0 for w in self.words),
            y0=min(w.bbox.y0 for w in self.words),
            x1=max(w.bbox.x1 for w in self.words),
            y1=max(w.bbox.y1 for w in self.words),
        )

    def span_bbox(self, start: int, end: int) -> BBox:
        """Pixel box for squished characters start..end, splitting words proportionally."""
        boxes: list[BBox] = []
        for c in self.chars[start:end]:
            b = self.words[c.word_index].bbox
            w = b.x1 - b.x0
            boxes.append(BBox(x0=b.x0 + c.frac0 * w, y0=b.y0, x1=b.x0 + c.frac1 * w, y1=b.y1))
        if not boxes:
            return self.bbox
        return BBox(
            x0=min(b.x0 for b in boxes),
            y0=min(b.y0 for b in boxes),
            x1=max(b.x1 for b in boxes),
            y1=max(b.y1 for b in boxes),
        )

    def span_text(self, start: int, end: int) -> str:
        """Original text for squished characters start..end, with word spaces restored."""
        out: list[str] = []
        last = None
        for c in self.chars[start:end]:
            if last is not None and c.word_index != last:
                out.append(" ")
            out.append(c.ch)
            last = c.word_index
        return "".join(out).strip()

    def span_conf(self, start: int, end: int) -> float:
        idx = {c.word_index for c in self.chars[start:end]}
        if not idx:
            return 0.0
        return float(np.mean([self.words[i].confidence for i in idx]))


def _finish(line: Line) -> Line:
    line.words.sort(key=lambda w: w.bbox.x0)
    chars: list[LineChar] = []
    for i, w in enumerate(line.words):
        n = max(len(w.text), 1)
        for j, ch in enumerate(w.text):
            if ch.isspace():
                continue
            chars.append(LineChar(ch=ch, word_index=i, frac0=j / n, frac1=(j + 1) / n))
    line.chars = chars
    line.text = " ".join(w.text for w in line.words)
    line.squished = "".join(c.ch for c in chars).casefold()
    return line


def group_lines(words: list[Word], skew_deg: float = 0.0, page: int = 0) -> list[Line]:
    """Group words into rows in deskewed coordinates, top to bottom."""
    if not words:
        return []
    tan = math.tan(math.radians(skew_deg))

    def ycenter(w: Word) -> float:
        return (w.bbox.y0 + w.bbox.y1) / 2 - tan * (w.bbox.x0 + w.bbox.x1) / 2

    ordered = sorted(words, key=ycenter)
    lines: list[Line] = []
    for w in ordered:
        y = ycenter(w)
        h = max(w.bbox.y1 - w.bbox.y0, 1.0)
        if lines:
            cur = lines[-1]
            if abs(y - cur.y) <= 0.55 * min(cur.height, h):
                n = len(cur.words)
                cur.words.append(w)
                cur.y = (cur.y * n + y) / (n + 1)
                cur.height = float(np.median([x.bbox.y1 - x.bbox.y0 for x in cur.words]))
                continue
        lines.append(Line(page=page, words=[w], y=y, height=h))
    return [_finish(ln) for ln in lines]


def doc_lines(doc: Document, page_index: int) -> list[Line]:
    page = doc.pages[page_index]
    skew = float((doc.metadata.get("skew_deg") or {}).get(str(page_index), 0.0))
    return group_lines(page.words, skew, page_index)


def squish(text: str) -> str:
    return re.sub(r"\s+", "", text).casefold()
