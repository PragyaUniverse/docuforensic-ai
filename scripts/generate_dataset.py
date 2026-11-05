#!/usr/bin/env python3
"""Deterministic generator for the DocuForensic AI demo dataset.

Every person, number and organisation is fictional and every page carries a SYNTHETIC mark.

Usage (from the repo root):
    .venv/bin/python scripts/generate_dataset.py            # generate everything
    .venv/bin/python scripts/generate_dataset.py --verify   # also OCR-check ground truth boxes
    .venv/bin/python scripts/generate_dataset.py --overlays DIR  # draw ground truth for review

Output layout and ground truth schema: docs/CONTRACTS.md section 6. Additive ground truth keys:
`raw`, `label`, `tables`, `regions`, `within_document`, `benign_variations`, `source_bbox`.
Fields use `value` = normalized value and `raw` = text as visible on the page. For an edited
PDF, `text_layer_value` holds what the text layer still says.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date
from functools import cache, lru_cache, partial
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import reportlab
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas as RLCanvas

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "data" / "synthetic_cases"
SEED = 20261104
W, H, DPI = 1654, 2339, 200
PT = 72 / DPI  # canonical pixels to PDF points
INK = (28, 28, 34)
LABEL = (70, 74, 84)
MUTED = (110, 114, 122)
RULE = (170, 174, 182)
SCAN_DEVICE = "DocuScan Firmware 2.1"
JPEG_Q = 88

BBox = list  # [x0, y0, x1, y1] in canonical pixels


def rng_for(*parts) -> np.random.Generator:
    digest = hashlib.sha256("|".join(map(str, (SEED, *parts))).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


# ----------------------------------------------------------------------------------------------
# Fonts. Vera ships with ReportLab; the URW base-14 clones ship inside MuPDF. No system fonts.
# ----------------------------------------------------------------------------------------------
VERA = Path(reportlab.__file__).parent / "fonts"
PDF_FONT = {
    "sans": "Vera", "sansb": "VeraBd", "sansi": "VeraIt",
    "serif": "Times-Roman", "serifb": "Times-Bold",
    "mono": "Courier", "monob": "Courier-Bold",
}
_FITZ = {"serif": "tiro", "serifb": "tibo", "mono": "cour", "monob": "cobo",
         "helv": "helv", "helvb": "hebo"}
_VERA = {"sans": "Vera.ttf", "sansb": "VeraBd.ttf", "sansi": "VeraIt.ttf"}
for _n, _f in (("Vera", "Vera.ttf"), ("VeraBd", "VeraBd.ttf"), ("VeraIt", "VeraIt.ttf")):
    pdfmetrics.registerFont(TTFont(_n, str(VERA / _f)))


@cache
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    if name in _VERA:
        return ImageFont.truetype(str(VERA / _VERA[name]), size)
    return ImageFont.truetype(io.BytesIO(pymupdf.Font(_FITZ[name]).buffer), size)


def ink_bbox(text: str, name: str, size: int, x: float, y: float) -> BBox:
    b = font(name, size).getbbox(text, anchor="ls")
    return [round(x + b[0], 1), round(y + b[1], 1), round(x + b[2], 1), round(y + b[3], 1)]


def union(boxes: list[BBox]) -> BBox:
    return [min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes)]


# ----------------------------------------------------------------------------------------------
# Drawing backends. One layout code path renders either to pixels or to a real digital PDF.
# ----------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def watermark_layer() -> Image.Image:
    layer = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    tile = Image.new("RGBA", (1500, 260), (255, 255, 255, 0))
    ImageDraw.Draw(tile).text((750, 130), "SYNTHETIC", font=font("sansb", 200),
                              fill=(120, 124, 132, 34), anchor="mm")
    tile = tile.rotate(35, expand=True, resample=Image.BICUBIC)
    for cy in (560, 1270, 1980):
        layer.alpha_composite(tile, (W // 2 - tile.width // 2, cy - tile.height // 2))
    return layer


class BaseCanvas:
    page = 0

    def text(self, x, y, s, name="sans", size=28, fill=INK, anchor="l") -> BBox:
        if anchor == "r":
            x -= font(name, size).getlength(s)
        elif anchor == "c":
            x -= font(name, size).getlength(s) / 2
        self._text(x, y, s, name, size, fill)
        return ink_bbox(s, name, size, x, y)

    def begin_page(self):
        self._watermark()
        self.text(W / 2, 46, "SYNTHETIC SPECIMEN - FICTIONAL DATA - NOT A REAL DOCUMENT",
                  "sansb", 20, (168, 40, 40), "c")


class ImgCanvas(BaseCanvas):
    def __init__(self):
        self.pages = [Image.new("RGB", (W, H), (255, 255, 255))]
        self.d = ImageDraw.Draw(self.pages[0])

    def next_page(self):
        raise ValueError("image formats hold exactly one page")

    def _watermark(self):
        im = self.pages[-1].convert("RGBA")
        im.alpha_composite(watermark_layer())
        self.pages[-1] = im.convert("RGB")
        self.d = ImageDraw.Draw(self.pages[-1])

    def _text(self, x, y, s, name, size, fill):
        self.d.text((x, y), s, font=font(name, size), fill=fill, anchor="ls")

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=2):
        self.d.rectangle([x0, y0, x1, y1], fill=fill, outline=outline, width=width)

    def rrect(self, x0, y0, x1, y1, r=24, fill=None, outline=None, width=3):
        self.d.rounded_rectangle([x0, y0, x1, y1], r, fill=fill, outline=outline, width=width)

    def line(self, x0, y0, x1, y1, fill=RULE, width=2):
        self.d.line([x0, y0, x1, y1], fill=fill, width=width)

    def image(self, im: Image.Image, x, y):
        rgba = im.convert("RGBA")
        self.pages[-1].paste(rgba.convert("RGB"), (int(x), int(y)), rgba)


class PdfCanvas(BaseCanvas):
    def __init__(self, path: Path):
        self.c = RLCanvas(str(path), pagesize=(W * PT, H * PT), invariant=1, pageCompression=1)

    def _y(self, y):
        return (H - y) * PT

    def next_page(self):
        self.c.showPage()
        self.page += 1

    def _watermark(self):
        # Raster, beneath all content, so that the watermark never pollutes the text layer.
        im = watermark_layer().resize((W // 2, H // 2), Image.BILINEAR)
        self.c.drawImage(ImageReader(im), 0, 0, W * PT, H * PT, mask="auto")

    def _text(self, x, y, s, name, size, fill):
        self.c.setFillColorRGB(*[v / 255 for v in fill])
        self.c.setFont(PDF_FONT[name], size * PT)
        self.c.drawString(x * PT, self._y(y), s)

    def _style(self, fill, outline, width):
        if fill:
            self.c.setFillColorRGB(*[v / 255 for v in fill])
        if outline:
            self.c.setStrokeColorRGB(*[v / 255 for v in outline])
            self.c.setLineWidth(width * PT)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=2):
        self._style(fill, outline, width)
        self.c.rect(x0 * PT, self._y(y1), (x1 - x0) * PT, (y1 - y0) * PT,
                    stroke=int(bool(outline)), fill=int(bool(fill)))

    def rrect(self, x0, y0, x1, y1, r=24, fill=None, outline=None, width=3):
        self._style(fill, outline, width)
        self.c.roundRect(x0 * PT, self._y(y1), (x1 - x0) * PT, (y1 - y0) * PT, r * PT,
                         stroke=int(bool(outline)), fill=int(bool(fill)))

    def line(self, x0, y0, x1, y1, fill=RULE, width=2):
        self._style(None, fill, width)
        self.c.line(x0 * PT, self._y(y0), x1 * PT, self._y(y1))

    def image(self, im: Image.Image, x, y):
        rgba = im.convert("RGBA")
        self.c.drawImage(ImageReader(rgba), x * PT, self._y(y + rgba.height),
                         rgba.width * PT, rgba.height * PT, mask="auto")

    def save(self):
        self.c.showPage()
        self.c.save()


@dataclass
class Rec:
    """Ground truth recorded while a document is drawn."""

    fields: dict = field(default_factory=dict)
    tables: dict = field(default_factory=dict)
    regions: dict = field(default_factory=dict)

    def add(self, name, value, raw, bbox, page=0, label=None):
        self.fields.setdefault(name, {"value": value, "raw": raw, "page": page, "bbox": bbox,
                                      "label": label})


# ----------------------------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------------------------
def inr(x: float) -> str:
    whole, frac = f"{x:.2f}".split(".")
    sign = "-" if whole.startswith("-") else ""
    whole = whole.lstrip("-")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return f"{sign}{whole}.{frac}"


def money(x: float) -> str:
    return f"{x:.2f}"


def dmy(iso: str, style="/") -> str:
    d = date.fromisoformat(iso)
    if style == "Mon":
        return d.strftime("%d-%b-%Y")
    return d.strftime(f"%d{style}%m{style}%Y")


ONES = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
TENS = ["x", "x", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def words(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + (f" {ONES[n % 10]}" if n % 10 else "")
    if n < 1000:
        return f"{ONES[n // 100]} Hundred" + (f" {words(n % 100)}" if n % 100 else "")
    if n < 100000:
        return f"{words(n // 1000)} Thousand" + (f" {words(n % 1000)}" if n % 1000 else "")
    return f"{words(n // 100000)} Lakh" + (f" {words(n % 100000)}" if n % 100000 else "")


# Verhoeff checksum, used for Aadhaar-format numbers. The 9999 prefix marks them as test values.
_VD = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
       [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
       [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
       [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
       [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]]
_VP = [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
       [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
       [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
       [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8]]
_VINV = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


def verhoeff_check_digit(body: str) -> str:
    c = 0
    for i, ch in enumerate(reversed(body)):
        c = _VD[c][_VP[(i + 1) % 8][int(ch)]]
    return str(_VINV[c])


def verhoeff_valid(num: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = _VD[c][_VP[i % 8][int(ch)]]
    return c == 0


def fake_aadhaar(seed: str) -> str:
    r = rng_for("aadhaar", seed)
    body = "9999" + "".join(str(int(d)) for d in r.integers(0, 10, 7))
    return body + verhoeff_check_digit(body)


def spaced_id(n: str) -> str:
    return f"{n[:4]} {n[4:8]} {n[8:]}"


# ----------------------------------------------------------------------------------------------
# Generated imagery: abstract avatars, bezier signatures, stamps
# ----------------------------------------------------------------------------------------------
def avatar(seed: str, size=(270, 330)) -> Image.Image:
    """Abstract geometric portrait placeholder. Deliberately not a face."""
    r = rng_for("avatar", seed)
    w, h = size
    base = r.integers(150, 215, 3)
    ramp = np.linspace(0, 1, h)[:, None, None] * r.integers(-40, 40, 3)[None, None, :]
    arr = np.clip(np.ones((h, w, 3)) * base + ramp + r.normal(0, 3, (h, w, 3)), 0, 255)
    im = Image.fromarray(arr.astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    tone = tuple(int(v) for v in r.integers(70, 130, 3))
    head = tuple(int(v) for v in r.integers(120, 190, 3))
    d.ellipse([w * 0.08, h * 0.62, w * 0.92, h * 1.35], fill=tone)
    d.ellipse([w * 0.27, h * 0.16, w * 0.73, h * 0.60], fill=head)
    for _ in range(3):
        cx, cy = r.uniform(0.3, 0.7) * w, r.uniform(0.2, 0.55) * h
        rad = r.uniform(8, 20)
        d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                  outline=tuple(int(v) for v in r.integers(40, 110, 3)), width=2)
    return im


def signature_model(seed: str) -> list[np.ndarray]:
    r = rng_for("signature", seed)
    strokes = []
    x = 0.04
    for _ in range(int(r.integers(3, 5))):
        pts = np.column_stack([
            np.clip(x + np.cumsum(r.uniform(0.03, 0.14, 4)), 0, 0.98),
            r.uniform(0.15, 0.85, 4),
        ])
        strokes.append(pts)
        x = float(pts[-1, 0]) - 0.04
    flourish = np.array([[0.05, 0.75], [0.35, r.uniform(0.85, 1.0)],
                         [0.7, r.uniform(0.55, 0.8)], [0.97, r.uniform(0.3, 0.6)]])
    strokes.append(flourish)
    return strokes


def signature(seed: str, instance: str, size=(420, 130), ink=(25, 35, 95)) -> Image.Image:
    """The same person's strokes with natural per-instance variation, never pixel identical."""
    r = rng_for("sig-instance", seed, instance)
    w, h = size
    ss = 4
    im = Image.new("RGBA", (w * ss, h * ss), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    slant = r.normal(0, 0.03)
    scale = r.uniform(0.94, 1.0)
    for pts in signature_model(seed):
        p = pts + r.normal(0, 0.018, pts.shape)
        ts = np.linspace(0, 1, 70)
        cu = np.column_stack([(1 - ts) ** 3, 3 * (1 - ts) ** 2 * ts, 3 * (1 - ts) * ts ** 2, ts ** 3])
        xy = cu @ p
        xy[:, 0] = (xy[:, 0] * scale + slant * (1 - xy[:, 1])) * w * ss
        xy[:, 1] = (0.05 + xy[:, 1] * 0.9) * h * ss
        pressure = r.uniform(1.8, 2.6)
        for i in range(len(xy) - 1):
            lw = max(2, int(ss * pressure * (0.75 + 0.45 * math.sin(i / 9))))
            d.line([tuple(xy[i]), tuple(xy[i + 1])], fill=(*ink, 255), width=lw)
    return im.resize(size, Image.LANCZOS)


def stamp(text: str, seed: str, size=250, ink=(40, 60, 150)) -> Image.Image:
    r = rng_for("stamp", seed)
    ss = 3
    s = size * ss
    im = Image.new("RGBA", (s, s), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    color = (*ink, 170)
    d.ellipse([12, 12, s - 12, s - 12], outline=color, width=4 * ss)
    d.ellipse([70, 70, s - 70, s - 70], outline=color, width=2 * ss)
    d.text((s / 2, s / 2 - 34), text, font=font("sansb", 16 * ss), fill=color, anchor="mm")
    d.text((s / 2, s / 2 + 34), "AUTHORISED", font=font("sansb", 13 * ss), fill=color, anchor="mm")
    im = im.rotate(float(r.uniform(-14, 14)), resample=Image.BICUBIC)
    return im.resize((size, size), Image.LANCZOS)


# ----------------------------------------------------------------------------------------------
# Acquisition simulation and tampering primitives
# ----------------------------------------------------------------------------------------------
def jpeg_roundtrip(im: Image.Image, q: int) -> Image.Image:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def scan(im: Image.Image, key: str) -> Image.Image:
    """One consistent acquisition pipeline: paper tone, illumination, optics, sensor, JPEG."""
    r = rng_for("scan", key)
    arr = np.asarray(im, dtype=np.float32)
    illum = cv2.resize(r.uniform(0.968, 0.992, (5, 4)).astype(np.float32), (W, H),
                       interpolation=cv2.INTER_CUBIC)
    tint = np.array([1.0, 0.994, 0.982], dtype=np.float32)
    arr = arr * illum[..., None] * tint
    arr = cv2.GaussianBlur(arr, (0, 0), 0.65)
    arr = arr + r.normal(0, 2.2, (H, W, 1)) + r.normal(0, 0.8, (H, W, 3))
    return jpeg_roundtrip(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB"), JPEG_Q)


def ring_median(img: Image.Image, box: BBox, pad=10) -> tuple[int, int, int]:
    a = np.asarray(img)
    x0, y0, x1, y1 = [int(v) for v in box]
    mask = np.zeros(a.shape[:2], bool)
    mask[max(0, y0 - pad):y1 + pad, max(0, x0 - pad):x1 + pad] = True
    mask[y0:y1, x0:x1] = False
    return tuple(int(v) for v in np.median(a[mask], axis=0))


def overwrite_value(img: Image.Image, old: BBox, baseline: float, x: float, text: str,
                    name: str, size: int, key: str) -> tuple[BBox, BBox]:
    """Paint a local background patch over a value and retype it in a different font.

    The patch has only faint noise compared with the scan around it, and the new glyphs skip the
    scanner's optics, which are the real traces an amateur edit leaves.
    """
    r = rng_for("overwrite", key)
    patch = [int(old[0]) - 8, int(old[1]) - 7, int(old[2]) + 10, int(old[3]) + 7]
    tone = np.array(ring_median(img, patch), dtype=np.float32) + 1
    h, w = patch[3] - patch[1], patch[2] - patch[0]
    fill = np.clip(tone + r.normal(0, 0.45, (h, w, 1)), 0, 255).astype(np.uint8)
    img.paste(Image.fromarray(fill, "RGB"), (patch[0], patch[1]))
    ImageDraw.Draw(img).text((x, baseline), text, font=font(name, size), fill=(12, 12, 16),
                             anchor="ls")
    glyphs = ink_bbox(text, name, size, x, baseline)
    return patch, glyphs


def paste_photo(img: Image.Image, frame: BBox, seed: str, key: str) -> BBox:
    """Replace a printed photo with a sharper, untreated image, slightly off the original frame."""
    r = rng_for("paste", key)
    w, h = int(frame[2] - frame[0]), int(frame[3] - frame[1])
    new = avatar(seed, (w + 6, h + 6))
    arr = np.asarray(new, dtype=np.float32) * np.array([1.03, 1.0, 0.95], dtype=np.float32)
    new = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    x, y = int(frame[0]) - 2 + int(r.integers(0, 3)), int(frame[1]) - 3 + int(r.integers(0, 3))
    img.paste(new, (x, y))
    return [x, y, x + new.width, y + new.height]


def copy_region(img: Image.Image, src: BBox, dst_xy: tuple[int, int]) -> BBox:
    x0, y0, x1, y1 = [int(v) for v in src]
    img.paste(img.crop((x0, y0, x1, y1)), dst_xy)
    return [dst_xy[0], dst_xy[1], dst_xy[0] + x1 - x0, dst_xy[1] + y1 - y0]


# ----------------------------------------------------------------------------------------------
# Applicant profiles. `over` applies per-document overrides for variation and discrepancies.
# ----------------------------------------------------------------------------------------------
@dataclass
class Profile:
    key: str
    name: str
    dob: str
    gender: str
    address: list[str]
    phone: str
    email: str
    aadhaar: str
    pan: str
    employer: str
    employer_short: str
    designation: str
    employee_id: str
    doj: str
    basic: float
    hra: float
    other: float
    pf: float
    ptax: float
    tds: float
    declared_income: float
    loan: float
    bank: str
    ifsc: str
    branch: str
    account: str
    consumer_no: str
    utility: str
    place: str
    app_id: str
    salary_credit: float
    opening: float = 142380.25
    extra_rows: int = 0
    over: dict = field(default_factory=dict)

    def get(self, doc: str, attr: str):
        return self.over.get(doc, {}).get(attr, getattr(self, attr))

    @property
    def gross(self) -> float:
        return round(self.basic + self.hra + self.other, 2)

    @property
    def deductions(self) -> float:
        return round(self.pf + self.ptax + self.tds, 2)

    @property
    def net(self) -> float:
        return round(self.gross - self.deductions, 2)


def banner(c, org: str, title: str, color, sub: str | None = None) -> int:
    c.rect(0, 70, W, 78, fill=color)
    c.text(110, 140, org, "sansb", 40, color)
    if sub:
        c.text(110, 178, sub, "sans", 22, MUTED)
    c.text(W - 110, 140, title, "sansb", 28, INK, "r")
    return 210


def section(c, y: int, title: str, color=(232, 236, 244), x0=110, x1=W - 110) -> int:
    c.rect(x0, y, x1, y + 44, fill=color)
    c.text(x0 + 14, y + 31, title, "sansb", 24, (32, 40, 64))
    return y + 86


def kv(c, rec, name, label, raw, y, x=124, vx=540, value=None, size=27, vfont="sans", lsize=25,
       underline=False, page=0):
    c.text(x, y, f"{label}:", "sansb", lsize, LABEL)
    box = c.text(vx, y, raw, vfont, size)
    if underline:
        c.line(vx - 4, y + 10, W - 124, y + 10, RULE, 1)
    if name:
        rec.add(name, raw if value is None else value, raw, box, page, label)
    return box


def kv_lines(c, rec, name, label, lines, y, x=124, vx=540, lead=40, size=27, vfont="sans", lsize=25,
             page=0):
    c.text(x, y, f"{label}:", "sansb", lsize, LABEL)
    boxes = [c.text(vx, y + i * lead, ln, vfont, size) for i, ln in enumerate(lines)]
    raw = ", ".join(lines)
    rec.add(name, raw, raw, union(boxes), page, label)
    return y + lead * (len(lines) - 1)


def para(c, x, y, text, width, name="sans", size=24, lead=36, fill=INK) -> int:
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font(name, size).getlength(trial) > width:
            c.text(x, y, line, name, size, fill)
            y += lead
            line = word
        else:
            line = trial
    if line:
        c.text(x, y, line, name, size, fill)
        y += lead
    return y


# ----------------------------------------------------------------------------------------------
# Document layouts
# ----------------------------------------------------------------------------------------------
def draw_application_form(c, p: Profile, rec: Rec):
    d = "application_form"
    c.begin_page()
    color = (24, 66, 120)
    y = banner(c, "Meridian Finserv Ltd.", "PERSONAL LOAN APPLICATION", color,
               "Registered lender (fictional) - Application Processing Centre")
    photo_box = [W - 110 - 270, y + 6, W - 110, y + 6 + 330]
    c.image(avatar(p.key), photo_box[0], photo_box[1])
    c.rect(*photo_box, outline=(60, 60, 70), width=2)
    rec.regions["photo"] = {"page": 0, "bbox": photo_box}

    y += 30
    kv(c, rec, "application_id", "Application ID", p.app_id, y, vx=470)
    y += 64
    c.rect(110, y, 1230, y + 44, fill=(232, 236, 244))
    c.text(124, y + 31, "A. Applicant Details", "sansb", 24, (32, 40, 64))
    y += 86
    name = p.get(d, "name")
    kv(c, rec, "person_name", "Applicant Name", name, y, vx=470)
    y += 52
    dob = p.get(d, "dob")
    kv(c, rec, "date_of_birth", "Date of Birth", dmy(dob), y, vx=470, value=dob)
    y += 52
    kv(c, rec, "gender", "Gender", p.gender, y, vx=470)
    y += 52
    aad = p.get(d, "aadhaar")
    kv(c, rec, "id_number", "Aadhaar No.", spaced_id(aad), y, vx=470, value=aad)
    y = photo_box[3] + 62 if y < photo_box[3] else y + 62
    kv(c, rec, "pan_number", "PAN", p.get(d, "pan"), y, vx=470)
    y += 40

    y = section(c, y, "B. Contact Details")
    y = kv_lines(c, rec, "address", "Residential Address", p.get(d, "address"), y)
    y += 52
    kv(c, rec, "phone", "Mobile", p.phone, y)
    y += 52
    kv(c, rec, "email", "Email", p.email, y)
    y += 40

    y = section(c, y, "C. Employment Details")
    kv(c, rec, "employer_name", "Employer Name", p.get(d, "employer"), y)
    y += 52
    kv(c, rec, "designation", "Designation", p.designation, y)
    y += 52
    doj = p.get(d, "doj")
    kv(c, rec, "date_of_joining", "Date of Joining", dmy(doj), y, value=doj)
    y += 52
    inc = p.get(d, "declared_income")
    kv(c, rec, "declared_monthly_income", "Monthly Income (Rs.)", inr(inc), y, value=money(inc))
    y += 40

    y = section(c, y, "D. Loan and Repayment Details")
    kv(c, rec, "loan_amount", "Loan Amount (Rs.)", inr(p.loan), y, value=money(p.loan))
    y += 52
    kv(c, rec, None, "Tenure", "48 months", y)
    y += 52
    kv(c, rec, "bank_account_number", "Bank A/c No.", p.get(d, "account"), y)
    y += 52
    kv(c, rec, None, "Bank / IFSC", f"{p.bank} / {p.ifsc}", y)
    y += 40

    y = section(c, y, "E. Applicant Undertaking")
    y = para(c, 124, y, "I confirm that the information given above is true and complete to the "
             "best of my knowledge, and I authorise the lender to verify it with the issuers of "
             "the supporting documents.", W - 248, size=23, lead=34)
    y += 34
    app_date = p.get(d, "app_date") if "app_date" in p.over.get(d, {}) else "2026-11-02"
    kv(c, rec, "application_date", "Application Date", dmy(app_date), y, vx=420, value=app_date)
    kv(c, rec, None, "Place", p.place, y + 52, vx=420)
    sig = signature(p.key, "application_form")
    sx, sy = 1000, y - 66
    c.image(sig, sx, sy)
    rec.regions["signature"] = {"page": 0, "bbox": [sx, sy, sx + sig.width, sy + sig.height]}
    c.line(sx, sy + sig.height + 4, sx + sig.width, sy + sig.height + 4, (60, 60, 70), 2)
    c.text(sx, sy + sig.height + 36, "Signature of Applicant", "sans", 22, MUTED)


def draw_id_proof(c, p: Profile, rec: Rec):
    d = "id_proof"
    c.begin_page()
    y = banner(c, "Identity Document Copy", "ID PROOF", (60, 70, 90),
               "Self-attested photocopy of identity cards (synthetic specimens)")
    x0, x1 = 170, W - 170
    y0 = y + 40
    c.rrect(x0, y0, x1, y0 + 780, fill=(247, 248, 244), outline=(90, 95, 105))
    c.rect(x0 + 3, y0 + 3, x1 - 3, y0 + 80, fill=(214, 228, 216))
    c.text((x0 + x1) / 2, y0 + 55, "AADHAAR-STYLE IDENTITY CARD (SYNTHETIC SPECIMEN)", "sansb", 27,
           (30, 70, 50), "c")
    rec.add("id_type", "AADHAAR-STYLE", "AADHAAR-STYLE",
            ink_bbox("AADHAAR-STYLE", "sansb", 27,
                     (x0 + x1) / 2 - font("sansb", 27).getlength(
                         "AADHAAR-STYLE IDENTITY CARD (SYNTHETIC SPECIMEN)") / 2, y0 + 55),
            0, "Card title")
    fx, fy = x0 + 44, y0 + 120
    c.image(avatar(p.key), fx, fy)
    c.rect(fx, fy, fx + 270, fy + 330, outline=(60, 60, 70), width=2)
    rec.regions["photo"] = {"page": 0, "bbox": [fx, fy, fx + 270, fy + 330]}
    lx, vx = fx + 310, fx + 490
    yy = fy + 40
    name = p.get(d, "name")
    kv(c, rec, "person_name", "Name", name, yy, x=lx, vx=vx, vfont="sansb")
    yy += 66
    dob = p.get(d, "dob")
    kv(c, rec, "date_of_birth", "DOB", dmy(dob), yy, x=lx, vx=vx, value=dob)
    yy += 66
    kv(c, rec, "gender", "Gender", p.gender, yy, x=lx, vx=vx)
    yy += 66
    addr = p.get(d, "address")
    kv_lines(c, rec, "address", "Address", addr, yy, x=lx, vx=vx, lead=38, size=25)
    aad = p.get(d, "aadhaar")
    yy = y0 + 650
    c.text((x0 + x1) / 2 - 340, yy, "ID No:", "sansb", 34, LABEL)
    box = c.text((x0 + x1) / 2 - 200, yy, spaced_id(aad), "sansb", 46)
    rec.add("id_number", aad, spaced_id(aad), box, 0, "ID No")

    y1 = y0 + 850
    c.rrect(x0, y1, x1, y1 + 560, fill=(244, 246, 250), outline=(90, 95, 105))
    c.rect(x0 + 3, y1 + 3, x1 - 3, y1 + 80, fill=(214, 222, 238))
    c.text((x0 + x1) / 2, y1 + 55, "PAN-STYLE TAX ID CARD (SYNTHETIC SPECIMEN)", "sansb", 27,
           (30, 50, 100), "c")
    lx, vx = x0 + 60, x0 + 420
    yy = y1 + 150
    # Agreeing repeats of name and DOB appear on the second card, as on real document copies.
    c.text(lx, yy, "Name:", "sansb", 25, LABEL)
    c.text(vx, yy, name, "sansb", 27)
    yy += 66
    c.text(lx, yy, "Date of Birth:", "sansb", 25, LABEL)
    c.text(vx, yy, dmy(dob), "sans", 27)
    yy += 66
    pan = p.get(d, "pan")
    kv(c, rec, "pan_number", "Permanent Account No", pan, yy, x=lx, vx=vx + 40, vfont="sansb",
       size=33)
    yy += 56
    sig = signature(p.key, "id_proof")
    sx, sy = vx, yy
    c.image(sig, sx, sy)
    c.text(lx, sy + 80, "Signature:", "sansb", 25, LABEL)
    rec.regions["signature"] = {"page": 0, "bbox": [sx, sy, sx + sig.width, sy + sig.height]}
    c.text(x0, y1 + 620, "Self-attested true copy. Issuer marks omitted on synthetic specimens.",
           "sansi", 22, MUTED)


def draw_salary_slip(c, p: Profile, rec: Rec):
    d = "salary_slip"
    c.begin_page()
    color = (22, 96, 88)
    employer = p.get(d, "employer")
    y = banner(c, employer, "PAYSLIP", color, "Human Resources and Payroll")
    y += 8
    c.text(W / 2, y, "Payslip for the month of October 2026", "sansb", 30, INK, "c")
    y += 54
    lx2, vx1, vx2 = 860, 400, 1150
    name = p.get(d, "name")
    kv(c, rec, "person_name", "Employee Name", name, y, vx=vx1)
    kv(c, rec, "employee_id", "Employee ID", p.employee_id, y, x=lx2, vx=vx2)
    y += 52
    kv(c, rec, "designation", "Designation", p.designation, y, vx=vx1)
    kv(c, rec, "pay_period", "Pay Period", "October 2026", y, x=lx2, vx=vx2, value="2026-10")
    y += 52
    doj = p.get(d, "doj")
    kv(c, rec, "date_of_joining", "Date of Joining", dmy(doj, "Mon"), y, vx=vx1, value=doj)
    kv(c, rec, "pan_number", "PAN", p.get(d, "pan"), y, x=lx2, vx=vx2)
    y += 52
    kv(c, rec, "employer_name", "Employer", employer, y, vx=vx1)
    y += 52
    kv(c, rec, "bank_account_number", "Salary A/c No.", p.get(d, "account"), y, vx=vx1)
    y += 46

    x0, x1, xm = 110, W - 110, W // 2
    c.rect(x0, y, x1, y + 50, fill=(226, 238, 234))
    c.text(x0 + 16, y + 35, "Earnings", "sansb", 25, (20, 60, 55))
    c.text(xm - 16, y + 35, "Amount (Rs.)", "sansb", 25, (20, 60, 55), "r")
    c.text(xm + 16, y + 35, "Deductions", "sansb", 25, (20, 60, 55))
    c.text(x1 - 16, y + 35, "Amount (Rs.)", "sansb", 25, (20, 60, 55), "r")
    top = y
    y += 92
    earn = [("basic_pay", "Basic Pay", p.basic), ("hra", "HRA", p.hra),
            ("other_allowances", "Other Allowances", p.other)]
    ded = [("Provident Fund", p.pf), ("Professional Tax", p.ptax), ("Income Tax (TDS)", p.tds)]
    rows_e, rows_d = [], []
    for (nm, lb, val), (dl, dv) in zip(earn, ded):
        c.text(x0 + 16, y, lb, "sans", 26)
        box = c.text(xm - 16, y, inr(val), "sans", 26, anchor="r")
        rec.add(nm, money(val), inr(val), box, 0, lb)
        c.text(xm + 16, y, dl, "sans", 26)
        c.text(x1 - 16, y, inr(dv), "sans", 26, anchor="r")
        rows_e.append([lb, inr(val)])
        rows_d.append([dl, inr(dv)])
        y += 56
    c.line(x0, y - 30, x1, y - 30, RULE, 2)
    y += 16
    c.text(x0 + 16, y, "Gross Pay", "sansb", 26)
    box = c.text(xm - 16, y, inr(p.gross), "sansb", 26, anchor="r")
    rec.add("gross_pay", money(p.gross), inr(p.gross), box, 0, "Gross Pay")
    c.text(xm + 16, y, "Total Deductions", "sansb", 26)
    box = c.text(x1 - 16, y, inr(p.deductions), "sansb", 26, anchor="r")
    rec.add("total_deductions", money(p.deductions), inr(p.deductions), box, 0, "Total Deductions")
    y += 26
    c.rect(x0, top, x1, y, outline=(100, 110, 110), width=2)
    c.line(xm, top, xm, y, (100, 110, 110), 2)
    rec.tables["earnings"] = {"page": 0, "headers": ["component", "amount"], "rows": rows_e}
    rec.tables["deductions"] = {"page": 0, "headers": ["component", "amount"], "rows": rows_d}
    y += 76
    net = p.net
    c.text(x0 + 16, y, "Net Pay (Rs.):", "sansb", 32, LABEL)
    box = c.text(470, y, inr(net), "sansb", 34)
    rec.add("net_pay", money(net), inr(net), box, 0, "Net Pay (Rs.)")
    rec.regions["net_pay_baseline"] = {"page": 0, "x": 470, "y": y, "font": "sansb", "size": 34}
    y += 56
    c.text(x0 + 16, y, f"Net Pay in words: Rupees {words(int(net))} Only", "sansi", 24, INK)
    y += 170
    c.image(stamp(p.employer_short, p.key), 1010, y - 130)
    auth = signature(p.key + "-hr", "salary_slip", ink=(20, 20, 30))
    c.image(auth, 110, y - 60)
    c.line(110, y + 74, 530, y + 74, (60, 60, 70), 2)
    c.text(110, y + 106, "Authorised Signatory", "sans", 22, MUTED)
    rec.regions["authorised_signature"] = {
        "page": 0, "bbox": [110, y - 60, 110 + auth.width, y - 60 + auth.height]}
    c.text(110, y + 190, "This is a system generated payslip for a fictional employee.",
           "sansi", 22, MUTED)


def transactions(p: Profile) -> list[dict]:
    r = rng_for("txn", p.key)
    rows: list[dict] = []
    months = [(2026, 5, 29), (2026, 6, 30), (2026, 7, 31), (2026, 8, 31), (2026, 9, 30),
              (2026, 10, 30)]
    credit = p.get("bank_statement", "salary_credit")
    desc_employer = p.get("bank_statement", "employer_short")
    for yr, m, last in months:
        rows.append({"date": date(yr, m, 3), "desc": "UPI-RENT-HOUSE OWNER",
                     "debit": float(int(r.integers(16, 24)) * 1000), "credit": 0.0})
        rows.append({"date": date(yr, m, int(r.integers(6, 11))), "desc": "ELECTRICITY BILL PAY",
                     "debit": round(float(r.uniform(900, 2400)), 2), "credit": 0.0})
        rows.append({"date": date(yr, m, int(r.integers(12, 19))), "desc": "UPI-GROCERY STORE",
                     "debit": round(float(r.uniform(1800, 5200)), 2), "credit": 0.0})
        if p.extra_rows:
            rows.append({"date": date(yr, m, int(r.integers(19, 24))), "desc": "ATM CASH WITHDRAWAL",
                         "debit": float(int(r.integers(2, 9)) * 1000), "credit": 0.0})
            rows.append({"date": date(yr, m, int(r.integers(24, 28))), "desc": "INSURANCE PREMIUM ECS",
                         "debit": round(float(r.uniform(1200, 3100)), 2), "credit": 0.0})
        rows.append({"date": date(yr, m, last), "desc": f"NEFT CR-{desc_employer}-SALARY",
                     "debit": 0.0, "credit": credit, "is_salary": True})
    rows.sort(key=lambda t: t["date"])
    bal = p.opening
    for row in rows:
        bal = round(bal + row["credit"] - row["debit"], 2)
        row["balance"] = bal
    return rows


def draw_bank_statement(c, p: Profile, rec: Rec, multipage=False):
    d = "bank_statement"
    c.begin_page()
    color = (120, 44, 58)
    y = banner(c, p.bank, "ACCOUNT STATEMENT", color, f"{p.branch} Branch")
    rows = transactions(p)
    closing = rows[-1]["balance"]
    y += 16
    kv(c, rec, "person_name", "Account Holder", p.get(d, "name"), y, vx=480)
    y += 50
    y = kv_lines(c, rec, "address", "Address", p.get(d, "address"), y, vx=480, lead=38)
    y += 50
    kv(c, rec, "bank_name", "Bank", p.bank, y, vx=480)
    kv(c, rec, "ifsc", "IFSC", p.ifsc, y, x=1000, vx=1140)
    y += 50
    kv(c, rec, "bank_account_number", "Account No.", p.get(d, "account"), y, vx=480)
    y += 50
    period = "01-May-2026 to 31-Oct-2026"
    kv(c, rec, "statement_period", "Statement Period", period, y, vx=480,
       value="2026-05-01/2026-10-31")
    y += 50
    kv(c, rec, "opening_balance", "Opening Balance (Rs.)", inr(p.opening), y, vx=480,
       value=money(p.opening), lsize=24)
    y += 50
    kv(c, rec, "closing_balance", "Closing Balance (Rs.)", inr(closing), y, vx=480,
       value=money(closing), lsize=24)
    y += 44

    cols = {"date": 124, "desc": 340, "debit_r": 1100, "credit_r": 1320, "balance_r": W - 124}

    def table_head(yy):
        c.rect(110, yy, W - 110, yy + 48, fill=(240, 228, 230))
        c.text(cols["date"], yy + 34, "Date", "sansb", 24, (80, 30, 40))
        c.text(cols["desc"], yy + 34, "Description", "sansb", 24, (80, 30, 40))
        c.text(cols["debit_r"], yy + 34, "Debit", "sansb", 24, (80, 30, 40), "r")
        c.text(cols["credit_r"], yy + 34, "Credit", "sansb", 24, (80, 30, 40), "r")
        c.text(cols["balance_r"], yy + 34, "Balance", "sansb", 24, (80, 30, 40), "r")
        return yy + 50

    y = table_head(y)
    row_h = 46
    gt_rows = []
    page = 0
    for row in rows:
        if y + row_h > H - 120:
            if not multipage:
                raise ValueError("statement overflowed a single page")
            c.text(W / 2, H - 70, f"Page {page + 1}", "sans", 22, MUTED, "c")
            c.next_page()
            page += 1
            c.begin_page()
            c.text(110, 130, f"{p.bank} - Account Statement (continued)", "sansb", 28, color)
            y = table_head(160)
        base = y + 33
        date_s = row["date"].strftime("%d-%b-%Y")
        debit = inr(row["debit"]) if row["debit"] else ""
        credit_s = inr(row["credit"]) if row["credit"] else ""
        boxes = [c.text(cols["date"], base, date_s, "mono", 26),
                 c.text(cols["desc"], base, row["desc"], "mono", 23)]
        credit_box = None
        if debit:
            boxes.append(c.text(cols["debit_r"], base, debit, "mono", 26, anchor="r"))
        if credit_s:
            credit_box = c.text(cols["credit_r"], base, credit_s, "mono", 26, anchor="r")
            boxes.append(credit_box)
        boxes.append(c.text(cols["balance_r"], base, inr(row["balance"]), "mono", 26, anchor="r"))
        c.line(110, y + row_h, W - 110, y + row_h, (214, 216, 222), 1)
        gt_rows.append({"cells": [date_s, row["desc"], debit, credit_s, inr(row["balance"])],
                        "page": page, "bbox": union(boxes), "credit_bbox": credit_box,
                        "row_top": y, "row_h": row_h, "baseline": base,
                        "is_salary": bool(row.get("is_salary"))})
        y += row_h
    c.text(W / 2, min(y + 60, H - 70), "*** End of Statement ***", "sans", 22, MUTED, "c")
    rec.tables["transactions"] = {"page": 0, "headers": ["date", "description", "debit", "credit",
                                                         "balance"], "rows": gt_rows}
    rec.regions["table_columns"] = {"page": 0, **cols}


def draw_address_proof(c, p: Profile, rec: Rec):
    d = "address_proof"
    c.begin_page()
    color = (150, 96, 20)
    y = banner(c, p.utility, "ELECTRICITY BILL", color, "Tax invoice cum demand notice (fictional issuer)")
    rec.add("issuer_name", p.utility, p.utility, ink_bbox(p.utility, "sansb", 40, 110, 140), 0, None)
    y += 26
    y = section(c, y, "Consumer Details", (246, 236, 220))
    kv(c, rec, "person_name", "Consumer Name", p.get(d, "name"), y)
    y += 52
    y = kv_lines(c, rec, "address", "Service Address", p.get(d, "address"), y)
    y += 52
    kv(c, rec, "consumer_number", "Consumer No.", p.consumer_no, y)
    y += 52
    kv(c, rec, None, "Tariff Category", "LT-2A Domestic", y)
    y += 40
    y = section(c, y, "Bill Summary", (246, 236, 220))
    kv(c, rec, "bill_date", "Bill Date", dmy("2026-10-12", "Mon"), y, value="2026-10-12")
    y += 52
    kv(c, rec, None, "Billing Period", "01-Sep-2026 to 30-Sep-2026", y)
    y += 52
    kv(c, rec, None, "Due Date", dmy("2026-10-27", "Mon"), y)
    y += 52
    amount = {"prya": 1842.0}.get(p.key, 1496.0)
    kv(c, rec, "amount_due", "Amount Due (Rs.)", inr(amount), y, value=money(amount), vfont="sansb")
    y += 44
    y = section(c, y, "Meter Reading and Charges", (246, 236, 220))
    table = [("Previous Reading", "18,204"), ("Current Reading", "18,396"), ("Units Consumed", "192"),
             ("Energy Charges (Rs.)", "1,152.00"), ("Fixed Charges (Rs.)", "210.00"),
             ("Taxes and Duty (Rs.)", inr(amount - 1362.0))]
    rows = []
    for lb, val in table:
        c.text(124, y, lb, "sans", 26)
        c.text(W - 124, y, val, "sans", 26, anchor="r")
        c.line(110, y + 14, W - 110, y + 14, (224, 224, 228), 1)
        rows.append([lb, val])
        y += 54
    rec.tables["charges"] = {"page": 0, "headers": ["item", "value"], "rows": rows}
    y += 40
    para(c, 124, y, "This bill is accepted as proof of address only for the service connection "
         "shown above. Pay by the due date to avoid a late fee. Issued for a fictional consumer.",
         W - 248, size=23, lead=34, fill=MUTED)


DECLARATION_CLAUSES = (
    ("1. I declare that the particulars stated above are true and correct, and that the "
     "documents I have submitted in support of my loan application are genuine."),
    ("2. I understand that the lender may verify these particulars with my employer, my bank "
     "and the issuing authorities, and may rely on them while assessing my application."),
    ("3. I undertake to inform the lender promptly of any material change in my employment, "
     "my income or my residential address while the application is under consideration."),
)


def draw_declaration(c, p: Profile, rec: Rec):
    d = "declaration"
    c.begin_page()
    y = 150
    c.text(W / 2, y, "SELF-DECLARATION OF INCOME AND EMPLOYMENT", "serifb", 42, INK, "c")
    y += 40
    c.line(320, y, W - 320, y, INK, 2)
    y += 70
    c.text(150, y, "To: The Credit Manager, Meridian Finserv Ltd.", "serif", 32)
    y += 72
    vx = 560
    name = p.get(d, "name")
    kv(c, rec, "person_name", "Name", name, y, x=150, vx=vx, vfont="serif", size=33)
    y += 58
    dob = p.get(d, "dob")
    kv(c, rec, "date_of_birth", "Date of Birth", dmy(dob, "-"), y, x=150, vx=vx, value=dob,
       vfont="serif", size=33)
    y += 58
    y = kv_lines(c, rec, "address", "Residential Address", p.get(d, "address"), y, x=150, vx=vx,
                 vfont="serif", size=33, lead=44)
    y += 58
    kv(c, rec, "employer_name", "Employer", p.get(d, "employer"), y, x=150, vx=vx, vfont="serif",
       size=33)
    y += 58
    inc = p.get(d, "declared_income")
    kv(c, rec, "declared_monthly_income", "Monthly Income (Rs.)", inr(inc), y, x=150, vx=vx,
       value=money(inc), vfont="serif", size=33)
    y += 90
    for clause in DECLARATION_CLAUSES:
        y = para(c, 150, y, clause, W - 300, "serif", 32, 46)
        y += 22
    y += 70
    dec_date = p.over.get(d, {}).get("dec_date", "2026-11-02")
    kv(c, rec, "declaration_date", "Date", dmy(dec_date, "-"), y, x=150, vx=330, value=dec_date,
       vfont="serif", size=33)
    kv(c, rec, "place", "Place", p.place, y + 58, x=150, vx=330, vfont="serif", size=33)
    sig = signature(p.key, "declaration")
    sx, sy = 1010, y - 70
    c.image(sig, sx, sy)
    rec.regions["signature"] = {"page": 0, "bbox": [sx, sy, sx + sig.width, sy + sig.height]}
    c.line(sx, sy + sig.height + 4, sx + sig.width, sy + sig.height + 4, INK, 2)
    c.text(sx, sy + sig.height + 38, "Signature of Declarant", "serif", 28, MUTED)


LAYOUTS = {"application_form": draw_application_form, "id_proof": draw_id_proof,
           "salary_slip": draw_salary_slip, "bank_statement": draw_bank_statement,
           "address_proof": draw_address_proof, "declaration": draw_declaration}
CREATORS = {"application_form": "Loan Origination Portal 3.4", "salary_slip": "PayrollDesk HRMS 6.1",
            "bank_statement": "CoreBank Statement Service 9.2", "declaration": "Loan Origination Portal 3.4",
            "address_proof": "Utility Billing Engine 2.8", "id_proof": "Loan Origination Portal 3.4"}


def stabilize_incremental_id(path: Path, key: str) -> None:
    """saveIncr writes a random second /ID into its trailer. Make that value reproducible.

    Trailer length may change safely: it sits after the xref section that startxref points to.
    """
    data = path.read_bytes()
    at = data.rindex(b"trailer")
    start = data.index(b"/ID[", at)
    first_end = data.index(b">", start) + 1
    end = data.index(b"]/Prev", first_end)
    stable = hashlib.md5(key.encode()).hexdigest().upper().encode()
    path.write_bytes(data[:first_end] + b"<" + stable + b">" + data[end:])


def pdf_date(iso: str, hhmm="1030") -> str:
    return f"D:{iso.replace('-', '')}{hhmm}00+05'30'"


def render_raster(doc_type: str, p: Profile) -> tuple[Image.Image, Rec]:
    c, rec = ImgCanvas(), Rec()
    LAYOUTS[doc_type](c, p, rec)
    return c.pages[0], rec


def render_digital(doc_type: str, p: Profile, path: Path, multipage=False) -> Rec:
    tmp = path.with_suffix(".tmp.pdf")
    c, rec = PdfCanvas(tmp), Rec()
    if doc_type == "bank_statement":
        draw_bank_statement(c, p, rec, multipage=multipage)
    else:
        LAYOUTS[doc_type](c, p, rec)
    c.save()
    doc = pymupdf.open(tmp)
    stamp_iso = "2026-10-31" if doc_type in {"salary_slip", "bank_statement"} else "2026-11-02"
    doc.set_metadata({"title": doc_type.replace("_", " ").title() + " (Synthetic)",
                      "author": "Synthetic Dataset", "subject": "Fictional sample document",
                      "creator": CREATORS[doc_type],
                      "producer": "ReportLab PDF Library", "keywords": "SYNTHETIC",
                      "creationDate": pdf_date(stamp_iso), "modDate": pdf_date(stamp_iso)})
    path.write_bytes(doc.tobytes(garbage=3, deflate=True, no_new_id=True))
    doc.close()
    tmp.unlink()
    return rec


def jpeg_bytes(im: Image.Image, q=JPEG_Q) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return buf.getvalue()


def write_scanned_pdf(im: Image.Image, path: Path, doc_type: str, iso="2026-11-01"):
    doc = pymupdf.open()
    page = doc.new_page(width=W * PT, height=H * PT)
    page.insert_image(page.rect, stream=jpeg_bytes(im))
    doc.set_metadata({"title": f"Scan - {doc_type} (Synthetic)", "creator": SCAN_DEVICE,
                      "producer": SCAN_DEVICE, "keywords": "SYNTHETIC",
                      "creationDate": pdf_date(iso, "0915"), "modDate": pdf_date(iso, "0915")})
    path.write_bytes(doc.tobytes(garbage=3, deflate=True, no_new_id=True))
    doc.close()


def write_jpg(im: Image.Image, path: Path, software=SCAN_DEVICE, dt="2026:11:01 09:15:00"):
    exif = Image.Exif()
    exif[0x010F] = "DocuScan"
    exif[0x0110] = "DS-200"
    exif[0x0131] = software
    exif[0x0132] = dt
    im.save(path, "JPEG", quality=JPEG_Q, exif=exif)


def render_page(path: Path, page=0) -> Image.Image:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        doc = pymupdf.open(path)
        pix = doc[page].get_pixmap(dpi=DPI, alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        doc.close()
        return im
    return Image.open(path).convert("RGB")


# ----------------------------------------------------------------------------------------------
# Case definitions
# ----------------------------------------------------------------------------------------------
PA = Profile(
    key="prya", name="Priya Raman Menon", dob="1991-03-14", gender="Female",
    address=["Flat 304, Lakeview Residency,", "12th Main Road, Indiranagar,",
             "Bengaluru, Karnataka 560038"],
    phone="+91 90000 01234", email="priya.menon@example.com", aadhaar=fake_aadhaar("prya"),
    pan="ZZAPM4821K", employer="Brightleaf Analytics Private Limited",
    employer_short="BRIGHTLEAF", designation="Senior Data Analyst", employee_id="BLA-20417",
    doj="2021-08-02", basic=36000.0, hra=14400.0, other=13200.50, pf=4320.0, ptax=200.0, tds=650.0,
    declared_income=63600.0, loan=800000.0, bank="Aravali National Bank", ifsc="ARVL0002214",
    branch="Indiranagar", account="40212208841730", consumer_no="BPD-77120394",
    utility="Cauvery Urban Power Distribution", place="Bengaluru", app_id="MF-2026-118204",
    salary_credit=58430.0,
    over={
        # Benign variation that a good system must not treat as a conflict.
        "salary_slip": {"name": "Priya R. Menon", "employer": "Brightleaf Analytics Pvt. Ltd."},
        "bank_statement": {"name": "PRIYA RAMAN MENON"},
        "id_proof": {"address": ["Flat 304, Lakeview Residency, 12th Main Rd,",
                                 "Indiranagar, Bengaluru,", "Karnataka - 560038"]},
        "address_proof": {"name": "Priya R Menon",
                          "address": ["Flat No 304, Lakeview Residency,",
                                      "12th Main Rd., Indiranagar,",
                                      "Bengaluru, Karnataka 560038"]},
        "declaration": {"employer": "Brightleaf Analytics Pvt Ltd"},
    },
)

PB = Profile(
    key="arjn", name="Arjun Vikram Desai", dob="1989-11-05", gender="Male",
    address=["B-17, Shanti Nagar Society,", "Paud Road, Kothrud,", "Pune, Maharashtra 411038"],
    phone="+91 90000 05678", email="arjun.desai@example.com", aadhaar=fake_aadhaar("arjn"),
    pan="ZZBPD7316L", employer="Kestrel Logistics Pvt. Ltd.", employer_short="KESTREL",
    designation="Operations Executive", employee_id="KL-08812", doj="2022-01-17", basic=30000.0,
    hra=12000.0, other=12000.0, pf=3600.0, ptax=200.0, tds=1880.0, declared_income=84320.0,
    loan=1500000.0, bank="Sahyadri Cooperative Bank", ifsc="SHYD0000917", branch="Kothrud",
    account="30088172640055", consumer_no="WMP-55102873", utility="Western Metro Power Supply",
    place="Pune", app_id="MF-2026-118377", salary_credit=48320.0, opening=31890.40,
)

PC = Profile(
    key="meen", name="Meenakshi Sundaram Iyer", dob="1988-07-19", gender="Female",
    address=["Flat 12B, Sai Krupa Apartments,", "4th Cross, Malleshwaram,",
             "Bengaluru, Karnataka 560003"],
    phone="+91 90000 09012", email="meenakshi.iyer@example.com", aadhaar=fake_aadhaar("meen"),
    pan="ZZCPI5502R", employer="Zenvora Technologies Pvt. Ltd.", employer_short="ZENVORA",
    designation="Project Manager", employee_id="ZT-33105", doj="2019-06-15", basic=44000.0,
    hra=17600.0, other=26400.0, pf=5280.0, ptax=200.0, tds=4270.0, declared_income=120000.0,
    loan=2500000.0, bank="Aravali National Bank", ifsc="ARVL0001108", branch="Malleshwaram",
    account="50100234567812", consumer_no="BPD-77998120", utility="Cauvery Urban Power Distribution",
    place="Bengaluru", app_id="MF-2026-118512", salary_credit=61250.0, opening=204115.75,
    extra_rows=1,
    over={
        "id_proof": {"dob": "1986-07-19", "pan": "ZZCPI5520R"},
        "salary_slip": {"name": "Minakshi S. Iyengar", "employer": "Zenvora Infotech Solutions",
                        "doj": "2024-02-01", "account": "50100234567821"},
        "address_proof": {"address": ["Flat 21B, Sai Krupa Apartments,", "4th Cross, Malleswaram,",
                                      "Bengaluru, Karnataka 560055"]},
    },
)

PD = Profile(
    key="rohn", name="Rohan Aditya Kulkarni", dob="1993-02-27", gender="Male",
    address=["House 88, Sector 21,", "Vashi, Navi Mumbai,", "Maharashtra 400703"],
    phone="+91 90000 03456", email="rohan.kulkarni@example.com", aadhaar=fake_aadhaar("rohn"),
    pan="ZZDPK9144M", employer="Vantage Point Systems Pvt. Ltd.", employer_short="VANTAGE",
    designation="Software Engineer", employee_id="VPS-14590", doj="2020-09-01", basic=40000.0,
    hra=16000.0, other=12000.0, pf=4800.0, ptax=200.0, tds=600.0, declared_income=86400.0,
    loan=1800000.0, bank="Sahyadri Cooperative Bank", ifsc="SHYD0000433", branch="Vashi",
    account="30088199127764", consumer_no="WMP-55640018", utility="Western Metro Power Supply",
    place="Navi Mumbai", app_id="MF-2026-118640", salary_credit=62400.0, opening=88215.10,
)

ORDER = ["application_form", "id_proof", "salary_slip", "bank_statement", "address_proof",
         "declaration"]
FORMATS = {
    "case_a_clean": {"application_form": "png", "id_proof": "jpg", "salary_slip": "digital_pdf",
                     "bank_statement": "scanned_pdf", "address_proof": "jpg",
                     "declaration": "digital_pdf"},
    "case_b_visual": {"application_form": "png", "id_proof": "jpg", "salary_slip": "png",
                      "bank_statement": "scanned_pdf", "address_proof": "digital_pdf",
                      "declaration": "png"},
    "case_c_crossdoc": {"application_form": "digital_pdf", "id_proof": "png",
                        "salary_slip": "scanned_pdf", "bank_statement": "digital_pdf",
                        "address_proof": "jpg", "declaration": "png"},
    "case_d_pdf": {"application_form": "digital_pdf", "id_proof": "jpg",
                   "salary_slip": "digital_pdf", "bank_statement": "digital_pdf",
                   "address_proof": "scanned_pdf", "declaration": "png"},
}
EXT = {"png": "png", "jpg": "jpg", "scanned_pdf": "pdf", "digital_pdf": "pdf"}
MANIFEST = [
    ("case_a_clean", "Case A: Consistent application",
     "All documents agree, apart from everyday formatting differences."),
    ("case_b_visual", "Case B: Visual investigation",
     "Image-level examination of a salary-backed application."),
    ("case_c_crossdoc", "Case C: Cross-document investigation",
     "Visually ordinary documents compared with each other."),
    ("case_d_pdf", "Case D: PDF structure investigation",
     "Digital PDFs examined at the file-structure level."),
]


@dataclass
class Built:
    doc_type: str
    fmt: str
    path: Path
    rec: Rec
    image: Image.Image | None = None  # final raster for non-digital documents
    pages: int = 1


def build_case(case: str, p: Profile, multipage_bank=False,
               tamper_raster=None) -> dict[str, Built]:
    """Render, scan, then apply tamper_raster(built) before encoding the final files."""
    out = OUT / case
    out.mkdir(parents=True, exist_ok=True)
    built: dict[str, Built] = {}
    for dt in ORDER:
        fmt = FORMATS[case][dt]
        path = out / f"{dt}.{EXT[fmt]}"
        if fmt == "digital_pdf":
            rec = render_digital(dt, p, path, multipage=multipage_bank and dt == "bank_statement")
            with pymupdf.open(path) as d:
                built[dt] = Built(dt, fmt, path, rec, pages=d.page_count)
        else:
            im, rec = render_raster(dt, p)
            built[dt] = Built(dt, fmt, path, rec, image=scan(im, f"{case}/{dt}"))
    if tamper_raster:
        tamper_raster(built)
    for b in built.values():
        if b.fmt == "png":
            b.image.save(b.path, "PNG", compress_level=9)
        elif b.fmt == "jpg":
            write_jpg(b.image, b.path, **getattr(b, "jpg_kwargs", {}))
        elif b.fmt == "scanned_pdf":
            write_scanned_pdf(b.image, b.path, b.doc_type)
    return built


def strip_table(t: dict) -> dict:
    rows = []
    for r in t["rows"]:
        if isinstance(r, dict):
            keep = {"cells", "page", "bbox", "text_layer_values"}
            rows.append({k: v for k, v in r.items() if k in keep})
        else:
            rows.append(r)
    return {"page": t["page"], "headers": t["headers"], "rows": rows}


def doc_gt(b: Built) -> dict:
    regions = {k: v for k, v in b.rec.regions.items() if k in
               {"photo", "signature", "authorised_signature"}}
    return {"filename": b.path.name, "doc_type": b.doc_type, "format": b.fmt, "pages": b.pages,
            "page_size": [W, H], "fields": b.rec.fields,
            "tables": {k: strip_table(v) for k, v in b.rec.tables.items()}, "regions": regions}


def write_gt(case: str, p: Profile, built: dict[str, Built], manipulations=(), discrepancies=(),
             within_document=(), benign=()):
    gt = {"case": case, "synthetic": True,
          "applicant": {"person_name": p.name, "date_of_birth": p.dob},
          "documents": [doc_gt(built[d]) for d in ORDER],
          "manipulations": list(manipulations), "discrepancies": list(discrepancies),
          "within_document": list(within_document), "benign_variations": list(benign)}
    (OUT / case / "ground_truth.json").write_text(json.dumps(gt, indent=2) + "\n")
    return gt


def gen_case_a():
    case = "case_a_clean"
    built = build_case(case, PA)
    benign = [
        {"kind": "name_format", "values": ["Priya Raman Menon", "Priya R. Menon", "Priya R Menon",
                                           "PRIYA RAMAN MENON"],
         "description": "Middle name, initial and upper-case forms of one name."},
        {"kind": "address_abbreviation", "values": ["12th Main Road", "12th Main Rd", "12th Main Rd.",
                                                    "Flat 304", "Flat No 304"],
         "description": "Common abbreviations and line breaks of one address."},
        {"kind": "employer_suffix", "values": ["Private Limited", "Pvt. Ltd.", "Pvt Ltd"],
         "description": "Legal suffix abbreviations of one employer."},
        {"kind": "rounding", "values": ["58,430.50", "58,430.00"],
         "description": "Net pay is rounded to the rupee by the salary credit."},
        {"kind": "date_format", "values": ["14/03/1991", "14-03-1991"],
         "description": "Date formats differ, the date does not."},
        {"kind": "agreeing_repeat", "values": ["person_name", "date_of_birth"],
         "description": "Name and DOB repeat, with the same values, on both ID cards."},
    ]
    return write_gt(case, PA, built, benign=benign), built


def gen_case_b():
    case = "case_b_visual"
    p = PB
    manipulations, within = [], []
    forged_net = 84320.0

    def tamper(built: dict[str, Built]):
        # m1: overwritten net pay on the salary slip.
        slip = built["salary_slip"]
        f = slip.rec.fields["net_pay"]
        base = slip.rec.regions["net_pay_baseline"]
        patch, glyphs = overwrite_value(slip.image, f["bbox"], base["y"], base["x"], inr(forged_net),
                                        "helvb", 35, "case_b/net")
        f.update(value=money(forged_net), raw=inr(forged_net), bbox=glyphs,
                 original_value=money(p.net))
        manipulations.append({
            "id": "m1", "type": "overwrite", "filename": slip.path.name, "page": 0, "bbox": patch,
            "expected_detectors": ["visual.overwrite", "visual.font_consistency", "visual.noise",
                                   "visual.ela"],
            "description": f"Net pay retyped from {inr(p.net)} to {inr(forged_net)} on a local "
                           "background patch in a different font.",
        })
        # m2: pasted photo on the ID.
        idp = built["id_proof"]
        frame = idp.rec.regions["photo"]["bbox"]
        pasted = paste_photo(idp.image, frame, p.key + "-other", "case_b/photo")
        idp.jpg_kwargs = {"software": "PhotoFix Express 4.1", "dt": "2026:11:01 22:41:09"}
        manipulations.append({
            "id": "m2", "type": "photo_insert", "filename": idp.path.name, "page": 0, "bbox": pasted,
            "expected_detectors": ["visual.photo_insert", "visual.ela", "visual.noise",
                                   "metadata.exif"],
            "description": "Printed photo replaced by a sharper image with a different tone, "
                           "slightly off the original frame. EXIF software differs from the "
                           "scanner used for the other documents.",
        })
        # m3: identical signature pixels reused from the application form.
        app, dec = built["application_form"], built["declaration"]
        src = app.rec.regions["signature"]["bbox"]
        dst = dec.rec.regions["signature"]["bbox"]
        placed = copy_between(app.image, src, dec.image, (int(dst[0]), int(dst[1])))
        dec.rec.regions["signature"]["bbox"] = placed
        manipulations.append({
            "id": "m3", "type": "signature_reuse", "filename": dec.path.name, "page": 0,
            "bbox": placed, "source_filename": app.path.name, "source_page": 0, "source_bbox": src,
            "expected_detectors": ["visual.signature_reuse"],
            "description": "Declaration signature is a pixel-identical copy of the application "
                           "form signature. Genuine signatures vary between documents.",
        })
        # m4: copy-move inside the bank statement, duplicating a salary credit over a small debit.
        bank = built["bank_statement"]
        rows = bank.rec.tables["transactions"]["rows"]
        cols = bank.rec.regions["table_columns"]
        salary = [i for i, r in enumerate(rows) if r["is_salary"]]
        src_row = rows[salary[1]]
        dst_i = next(i for i in range(salary[3] + 1, salary[4])
                     if rows[i]["cells"][1].startswith("UPI-GROCERY"))
        dst_row = rows[dst_i]
        x0, x1 = cols["desc"] - 6, cols["credit_r"] + 8
        src_box = [x0, src_row["row_top"] + 4, x1, src_row["row_top"] + src_row["row_h"] - 2]
        dst_box = copy_region(bank.image, src_box, (x0, dst_row["row_top"] + 4))
        dst_row["cells"][1:4] = src_row["cells"][1:4]
        dst_row["bbox"] = union([dst_row["bbox"], dst_box])
        manipulations.append({
            "id": "m4", "type": "copy_move", "filename": bank.path.name, "page": 0, "bbox": dst_box,
            "source_bbox": src_box,
            "expected_detectors": ["visual.copy_move"],
            "description": "A salary-credit row was copied over a small debit row, adding an "
                           "apparent extra credit.",
        })
        within.extend([
            {"id": "w1", "detector": "context.arithmetic_salary", "filename": slip.path.name,
             "description": f"Gross {inr(p.gross)} less deductions {inr(p.deductions)} is "
                            f"{inr(p.net)}, not the visible {inr(forged_net)}. Amount in words "
                            "also still states the original figure."},
            {"id": "w2", "detector": "context.arithmetic_balance", "filename": bank.path.name,
             "description": "Running balance does not reconcile on the copied row."},
            {"id": "w3", "detector": "context.amount_in_words", "filename": slip.path.name,
             "description": f"The words still state {inr(p.net)}, the figure says {inr(forged_net)}."},
        ])

    built = build_case(case, p, tamper_raster=tamper)
    discrepancies = [
        {"id": "d1", "discrepancy_type": "salary_vs_bank_credit",
         "documents": ["salary_slip.png", "bank_statement.pdf"],
         "description": f"Visible net pay {inr(forged_net)}; monthly credits {inr(p.salary_credit)}."},
        {"id": "d2", "discrepancy_type": "declared_vs_actual_income",
         "documents": ["application_form.png", "declaration.png", "bank_statement.pdf"],
         "description": f"Declared {inr(p.declared_income)}; salary credits {inr(p.salary_credit)}, "
                        f"payslip gross {inr(p.gross)}."},
    ]
    return write_gt(case, p, built, manipulations, discrepancies, within), built


def copy_between(src_img, src_box, dst_img, dst_xy) -> BBox:
    x0, y0, x1, y1 = [int(v) for v in src_box]
    dst_img.paste(src_img.crop((x0, y0, x1, y1)), dst_xy)
    return [dst_xy[0], dst_xy[1], dst_xy[0] + x1 - x0, dst_xy[1] + y1 - y0]


def gen_case_c():
    case = "case_c_crossdoc"
    p = PC
    built = build_case(case, p, multipage_bank=True)
    disc = [
        ("dob_mismatch", ["application_form.pdf", "id_proof.png"],
         "Date of birth 19/07/1988 on the application and declaration, 19/07/1986 on the ID."),
        ("salary_vs_bank_credit", ["salary_slip.pdf", "bank_statement.pdf"],
         f"Net pay {inr(p.net)} on the payslip, monthly credits of {inr(p.salary_credit)}."),
        ("address_variant", ["application_form.pdf", "address_proof.jpg"],
         "Flat 12B / PIN 560003 on the application, Flat 21B / PIN 560055 on the utility bill."),
        ("employer_mismatch", ["application_form.pdf", "salary_slip.pdf"],
         "Zenvora Technologies Pvt. Ltd. against Zenvora Infotech Solutions."),
        ("declared_vs_actual_income", ["application_form.pdf", "salary_slip.pdf"],
         f"Declared {inr(p.declared_income)} against payslip gross {inr(p.gross)}."),
        ("name_variant", ["application_form.pdf", "salary_slip.pdf"],
         "Meenakshi Sundaram Iyer against Minakshi S. Iyengar: the surname differs."),
        ("account_number_mismatch", ["salary_slip.pdf", "bank_statement.pdf"],
         "Salary account ends 7821 on the payslip, 7812 on the statement and the application."),
        ("id_number_mismatch", ["application_form.pdf", "id_proof.png"],
         "PAN ZZCPI5502R on the application, ZZCPI5520R on the ID card."),
        ("employment_date_conflict", ["application_form.pdf", "salary_slip.pdf"],
         "Date of joining 15/06/2019 on the application, 01-Feb-2024 on the payslip."),
    ]
    discrepancies = [{"id": f"d{i + 1}", "discrepancy_type": t, "documents": docs, "description": s}
                     for i, (t, docs, s) in enumerate(disc)]
    return write_gt(case, p, built, discrepancies=discrepancies), built


def gen_case_d():
    case = "case_d_pdf"
    p = PD
    built = build_case(case, p)
    forged_net = 86400.0
    manipulations, within = [], []

    # m1: a real incremental update on the salary slip. A raster patch hides the value, so the
    # text layer keeps the original while the rendered page shows the new figure.
    slip = built["salary_slip"]
    f = slip.rec.fields["net_pay"]
    x0, y0, x1, y1 = f["bbox"]
    box = [x0 - 6, y0 - 6, x1 + 14, y1 + 8]
    bw, bh = int(box[2] - box[0]), int(box[3] - box[1])
    patch = Image.new("RGB", (bw * 3, bh * 3), (255, 255, 255))
    ImageDraw.Draw(patch).text((6 * 3, (y1 - box[1]) * 3), inr(forged_net),
                               font=font("helvb", 35 * 3), fill=INK, anchor="ls")
    buf = io.BytesIO()
    patch.save(buf, "PNG")
    doc = pymupdf.open(slip.path)
    doc[0].insert_image(pymupdf.Rect(*[v * PT for v in box]), stream=buf.getvalue(), overlay=True)
    meta = dict(doc.metadata)
    meta.update(producer="PDF Editor Pro 11.2", modDate=pdf_date("2026-11-01", "2312"))
    doc.set_metadata(meta)
    doc.saveIncr()
    doc.close()
    stabilize_incremental_id(slip.path, "case_d/salary_slip")
    glyphs = ink_bbox(inr(forged_net), "helvb", 35, box[0] + 6, y1)
    f.update(value=money(forged_net), raw=inr(forged_net), bbox=glyphs,
             text_layer_value=inr(p.net), original_value=money(p.net))
    manipulations.append({
        "id": "m1", "type": "pdf_raster_patch", "filename": slip.path.name, "page": 0, "bbox": box,
        "expected_detectors": ["pdf.text_vs_pixels", "pdf.incremental_update",
                               "pdf.producer_mismatch", "pdf.overlay_object", "metadata.pdf_dates"],
        "description": f"Incremental update places an image over net pay. Pixels read "
                       f"{inr(forged_net)}, the text layer still reads {inr(p.net)}. Producer and "
                       "modified date changed in the same update.",
    })

    # m2: a real overlay on the bank statement: a form XObject with a white box and new text, also
    # saved as an incremental update, so the text layer holds both the old and new values.
    bank = built["bank_statement"]
    rows = bank.rec.tables["transactions"]["rows"]
    row = [r for r in rows if r["is_salary"]][-1]
    cx0, cy0, cx1, cy1 = row["credit_bbox"]
    new_s = inr(forged_net)
    wbox = [cx0 - 6, cy0 - 5, cx1 + 6, cy1 + 7]
    ov = pymupdf.open()
    op = ov.new_page(width=W * PT, height=H * PT)
    op.draw_rect(pymupdf.Rect(*[v * PT for v in wbox]), color=(1, 1, 1), fill=(1, 1, 1))
    tw = pymupdf.get_text_length(new_s, fontname="helv", fontsize=26 * PT)
    op.insert_text(((cx1 * PT) - tw, row["baseline"] * PT), new_s, fontname="helv", fontsize=26 * PT)
    doc = pymupdf.open(bank.path)
    doc[row["page"]].show_pdf_page(doc[row["page"]].rect, ov, 0, overlay=True)
    meta = dict(doc.metadata)
    meta.update(producer="PDF Editor Pro 11.2", modDate=pdf_date("2026-11-01", "2327"))
    doc.set_metadata(meta)
    doc.saveIncr()
    doc.close()
    ov.close()
    stabilize_incremental_id(bank.path, "case_d/bank_statement")
    old_s = row["cells"][3]
    row["cells"][3] = new_s
    row["text_layer_values"] = [old_s, new_s]
    manipulations.append({
        "id": "m2", "type": "pdf_overlay", "filename": bank.path.name, "page": row["page"],
        "bbox": wbox,
        "expected_detectors": ["pdf.overlay_object", "pdf.incremental_update",
                               "pdf.producer_mismatch", "pdf.text_vs_pixels", "metadata.pdf_dates"],
        "description": f"An overlay object covers the October salary credit with {new_s}. The "
                       f"text layer holds both {old_s} and {new_s} at that location.",
    })
    within.extend([
        {"id": "w1", "detector": "context.arithmetic_salary", "filename": slip.path.name,
         "description": f"Gross {inr(p.gross)} less deductions {inr(p.deductions)} is {inr(p.net)}, "
                        f"not the visible {inr(forged_net)}."},
        {"id": "w2", "detector": "context.arithmetic_balance", "filename": bank.path.name,
         "description": "The balance column reflects the original October credit, not the overlay."},
        {"id": "w3", "detector": "context.amount_in_words", "filename": slip.path.name,
         "description": f"The words still state {inr(p.net)}, the visible figure says {inr(forged_net)}."},
    ])
    discrepancies = [
        {"id": "d1", "discrepancy_type": "salary_vs_bank_credit",
         "documents": ["salary_slip.pdf", "bank_statement.pdf"],
         "description": f"Visible net pay {inr(forged_net)}, while five of six monthly credits are "
                        f"{inr(p.salary_credit)}."},
        {"id": "d2", "discrepancy_type": "declared_vs_actual_income",
         "documents": ["application_form.pdf", "salary_slip.pdf"],
         "description": f"Declared {inr(p.declared_income)} against payslip gross {inr(p.gross)}."},
    ]
    return write_gt(case, p, built, manipulations, discrepancies, within), built


# ----------------------------------------------------------------------------------------------
# Noise variants
# ----------------------------------------------------------------------------------------------
VARIANT_DOCS = {
    "case_a_clean": ["application_form", "id_proof", "salary_slip"],
    "case_b_visual": ["salary_slip", "id_proof", "declaration"],
    "case_c_crossdoc": ["salary_slip"],
}


def _identity(box):
    return box


def rotate_box(box, M):
    x0, y0, x1, y1 = box
    pts = np.array([[x0, y0, 1], [x1, y0, 1], [x1, y1, 1], [x0, y1, 1]], dtype=np.float64)
    out = pts @ M.T
    return [round(float(out[:, 0].min()), 1), round(float(out[:, 1].min()), 1),
            round(float(out[:, 0].max()), 1), round(float(out[:, 1].max()), 1)]


def map_boxes(obj, fn):
    if isinstance(obj, dict):
        return {k: (fn(v) if k in {"bbox", "source_bbox"} and v else map_boxes(v, fn))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [map_boxes(v, fn) for v in obj]
    return obj


def gen_noise_variants(gts: dict):
    root = OUT / "noise_variants"
    for case, docs in VARIANT_DOCS.items():
        out = root / case
        out.mkdir(parents=True, exist_ok=True)
        gt = gts[case]
        entries, mans = [], []
        for dt in docs:
            src_doc = next(d for d in gt["documents"] if d["doc_type"] == dt)
            src = OUT / case / src_doc["filename"]
            base = render_page(src)
            arr = np.asarray(base)
            for kind in ("rot", "blur", "jpeg"):
                r = rng_for("variant", case, dt, kind)
                name = f"{dt}__{kind}.jpg"
                params: dict = {}
                fn = _identity
                if kind == "rot":
                    angle = float(r.uniform(1.0, 2.0) * r.choice([-1, 1]))
                    M = cv2.getRotationMatrix2D((W / 2, H / 2), angle, 1.0)
                    im = Image.fromarray(cv2.warpAffine(arr, M, (W, H), flags=cv2.INTER_CUBIC,
                                                        borderValue=(244, 243, 238)))
                    params = {"angle_deg": round(angle, 3)}
                    fn = partial(rotate_box, M=M)
                    im.save(out / name, "JPEG", quality=85)
                elif kind == "blur":
                    sigma = 1.4
                    Image.fromarray(cv2.GaussianBlur(arr, (0, 0), sigma)).save(out / name, "JPEG",
                                                                               quality=90)
                    params = {"sigma": sigma}
                else:
                    base.save(out / name, "JPEG", quality=35)
                    params = {"quality": 35}
                entry = {k: v for k, v in src_doc.items() if k not in {"tables", "filename", "format"}}
                entry = map_boxes(entry, fn)
                entry.update(filename=name, format="jpg", variant=kind, params=params,
                             source_filename=src_doc["filename"], pages=1)
                entries.append(entry)
                for m in gt["manipulations"]:
                    if m["filename"] == src_doc["filename"]:
                        tm = map_boxes({k: v for k, v in m.items() if k != "source_bbox"
                                        or m.get("source_filename") is None}, fn)
                        tm.update(id=f"{m['id']}__{dt}__{kind}", filename=name, source_id=m["id"])
                        if m.get("source_filename"):
                            tm["source_bbox"] = m["source_bbox"]  # lives in the unrotated source
                        mans.append(tm)
        (out / "ground_truth.json").write_text(json.dumps(
            {"case": case, "synthetic": True, "variant_set": True,
             "applicant": gt["applicant"], "documents": entries, "manipulations": mans,
             "discrepancies": [], "note": "Bboxes are transformed to each variant's pixels."},
            indent=2) + "\n")


# ----------------------------------------------------------------------------------------------
# Unsupported and corrupt inputs, for safe failure handling
# ----------------------------------------------------------------------------------------------
def gen_unsupported():
    out = OUT / "unsupported"
    out.mkdir(parents=True, exist_ok=True)
    info = zipfile.ZipInfo("[Content_Types].xml", date_time=(2026, 11, 1, 0, 0, 0))
    with zipfile.ZipFile(out / "sample.docx", "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(info, '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/'
                         'package/2006/content-types"/>')
        doc = zipfile.ZipInfo("word/document.xml", date_time=(2026, 11, 1, 0, 0, 0))
        z.writestr(doc, '<?xml version="1.0"?><document>SYNTHETIC word-processor sample</document>')
    good = (OUT / "case_a_clean" / "salary_slip.pdf").read_bytes()
    (out / "truncated.pdf").write_bytes(good[: len(good) * 2 // 5])
    (out / "empty.png").write_bytes(b"")
    (out / "not_an_image.png").write_text("SYNTHETIC: this is plain text renamed to .png\n")
    (out / "expected.json").write_text(json.dumps({
        "sample.docx": {"status": "unsupported", "why": "Word documents are not an accepted format."},
        "truncated.pdf": {"status": "failed", "why": "The PDF is cut off and cannot be parsed."},
        "empty.png": {"status": "failed", "why": "The file has no content."},
        "not_an_image.png": {"status": "unsupported", "why": "Content is text despite the extension."},
    }, indent=2) + "\n")


def write_manifest():
    data = []
    for key, name, desc in MANIFEST:
        docs = [f"{d}.{EXT[FORMATS[key][d]]}" for d in ORDER]
        data.append({"key": key, "name": name, "description": desc, "dir": key, "documents": docs})
    (OUT / "manifest.json").write_text(json.dumps(data, indent=2) + "\n")


def generate():
    """Build in a sibling directory, then swap it in, so readers never see a partial tree."""
    global OUT
    final = OUT
    OUT = final.with_name(final.name + ".building")
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    gts = {}
    for gen in (gen_case_a, gen_case_b, gen_case_c, gen_case_d):
        gt, _ = gen()
        gts[gt["case"]] = gt
    gen_noise_variants(gts)
    gen_unsupported()
    write_manifest()
    assert all(verhoeff_valid(p.aadhaar) for p in (PA, PB, PC, PD))
    if final.exists():
        shutil.rmtree(final)
    OUT.rename(final)
    OUT = final


# ----------------------------------------------------------------------------------------------
# Verification: ground truth boxes must really contain the stated values
# ----------------------------------------------------------------------------------------------
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def verify(threshold=80.0) -> int:
    from rapidfuzz import fuzz
    from rapidocr_onnxruntime import RapidOCR

    engine = RapidOCR()
    failures = 0
    for key, *_ in MANIFEST:
        gt = json.loads((OUT / key / "ground_truth.json").read_text())
        total, scores, full = 0, [], {}
        for d in gt["documents"]:
            path = OUT / key / d["filename"]
            pages = {}
            for name, f in d["fields"].items():
                pg = f["page"]
                if pg not in pages:
                    pages[pg] = np.asarray(render_page(path, pg))
                    assert pages[pg].shape[:2] == (H, W), (path, pages[pg].shape)
                x0, y0, x1, y1 = [int(v) for v in f["bbox"]]
                crop = pages[pg][max(0, y0 - 14):y1 + 14, max(0, x0 - 14):x1 + 14]
                crop = cv2.copyMakeBorder(crop, 20, 20, 20, 20, cv2.BORDER_REPLICATE)
                res, _ = engine(crop)
                got = " ".join(r[1] for r in res) if res else ""
                score = fuzz.partial_ratio(_norm(str(f["raw"])), _norm(got))
                if score < threshold:
                    if (d["filename"], pg) not in full:
                        full[(d["filename"], pg)] = engine(pages[pg])[0] or []
                    near = [r[1] for r in full[(d["filename"], pg)]
                            if x0 - 14 <= np.mean([q[0] for q in r[0]]) <= x1 + 14
                            and y0 - 14 <= np.mean([q[1] for q in r[0]]) <= y1 + 14]
                    got = " ".join(near)
                    score = fuzz.partial_ratio(_norm(str(f["raw"])), _norm(got))
                total += 1
                scores.append(score)
                if score < threshold:
                    failures += 1
                    print(f"  LOW {key}/{d['filename']}:{name} want={f['raw']!r} got={got!r} {score:.0f}")
        print(f"{key}: {total} fields, mean OCR match {np.mean(scores):.1f}, min {min(scores):.0f}")
    return failures


def overlays(dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    for key, *_ in MANIFEST:
        gt = json.loads((OUT / key / "ground_truth.json").read_text())
        for d in gt["documents"]:
            im = render_page(OUT / key / d["filename"])
            draw = ImageDraw.Draw(im)
            for f in d["fields"].values():
                if f["page"] == 0:
                    draw.rectangle(f["bbox"], outline=(0, 120, 255), width=2)
            for r in d["regions"].values():
                draw.rectangle(r["bbox"], outline=(0, 170, 60), width=3)
            for m in gt["manipulations"]:
                if m["filename"] == d["filename"]:
                    draw.rectangle(m["bbox"], outline=(230, 30, 30), width=4)
                    if "source_bbox" in m and not m.get("source_filename"):
                        draw.rectangle(m["source_bbox"], outline=(240, 140, 20), width=4)
            im.resize((W // 2, H // 2), Image.LANCZOS).save(dest / f"{key}__{d['doc_type']}.png")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--no-generate", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--overlays", type=Path)
    ap.add_argument("--seed", type=int, help="Other randomness, for held-out evaluation sets")
    ap.add_argument("--out", type=Path, help="Write here instead of data/synthetic_cases")
    args = ap.parse_args()
    global SEED, OUT
    if args.seed is not None:
        SEED = args.seed
    if args.out is not None:
        OUT = args.out.resolve()
    if not args.no_generate:
        generate()
        total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
        print(f"Generated {sum(1 for f in OUT.rglob('*') if f.is_file())} files, "
              f"{total / 1e6:.1f} MB")
    if args.overlays:
        overlays(args.overlays)
    if args.verify:
        failures = verify()
        print(f"verification failures: {failures}")
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
