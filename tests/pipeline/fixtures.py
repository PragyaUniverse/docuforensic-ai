"""Small synthetic pages built for pipeline tests. All people and numbers are made up."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import reportlab
from PIL import Image, ImageDraw, ImageFilter, ImageFont

_FONT_DIR = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
SANS = os.path.join(_FONT_DIR, "Vera.ttf")
SANS_BOLD = os.path.join(_FONT_DIR, "VeraBd.ttf")
ITALIC = os.path.join(_FONT_DIR, "VeraIt.ttf")

A4 = (1654, 2339)


def font(path: str = SANS, size: int = 34) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


SALARY_ROWS = [
    ("Employee Name", "Asha Verma"),
    ("Employee ID", "EMP-20417"),
    ("Employer", "Northwind Tools Pvt Ltd"),
    ("Designation", "Senior Analyst"),
    ("Pay Period", "March 2026"),
    ("PAN", "ABCPV1234F"),
    ("Bank Account Number", "501002233445"),
    ("Basic Pay", "Rs. 45,000.00"),
    ("HRA", "Rs. 18,000.00"),
    ("Other Allowances", "Rs. 7,000.00"),
    ("Gross Pay", "Rs. 70,000.00"),
    ("Total Deductions", "Rs. 6,400.00"),
    ("Net Pay", "Rs. 63,600.00"),
]


def paper(noise: float = 2.0, seed: int = 7, size: tuple[int, int] = A4) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = size
    base = np.full((h, w, 3), 246.0) + rng.normal(0, noise, (h, w, 1))
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")


def salary_slip(rows=SALARY_ROWS, noise: float = 2.0, title: str = "SALARY SLIP") -> tuple[Image.Image, dict]:
    """Returns the page and a {label: value bbox} map in canonical pixels."""
    im = paper(noise)
    d = ImageDraw.Draw(im)
    d.text((120, 90), "Northwind Tools Pvt Ltd", font=font(SANS_BOLD, 48), fill=(20, 20, 20))
    d.text((120, 170), title, font=font(SANS_BOLD, 40), fill=(20, 20, 20))
    y = 300
    boxes: dict[str, tuple[int, int, int, int]] = {}
    f = font()
    for label, value in rows:
        d.text((120, y), f"{label}:", font=f, fill=(25, 25, 25))
        d.text((800, y), value, font=f, fill=(25, 25, 25))
        boxes[label] = d.textbbox((800, y), value, font=f)
        y += 90
    d.text((120, 2150), "SYNTHETIC SAMPLE", font=font(size=26), fill=(120, 120, 120))
    return im, boxes


def overwrite_value(im: Image.Image, bbox: tuple[int, int, int, int], text: str, noise_free: bool = True) -> tuple[Image.Image, tuple[int, int, int, int]]:
    """Paint a flat patch over a value and write a new one in a different font."""
    out = im.copy()
    d = ImageDraw.Draw(out)
    patch = (bbox[0] - 10, bbox[1] - 10, bbox[2] + 40, bbox[3] + 12)
    d.rectangle(patch, fill=(252, 252, 252))
    d.text((bbox[0], bbox[1] - 8), text, font=font(ITALIC, 40), fill=(60, 60, 90))
    return out, patch


def draw_signature(seed: int = 3, size: tuple[int, int] = (360, 120)) -> Image.Image:
    rng = np.random.default_rng(seed)
    w, h = size
    im = Image.new("L", size, 255)
    d = ImageDraw.Draw(im)
    x = np.linspace(10, w - 10, 80)
    y = h / 2 + np.cumsum(rng.normal(0, 7, 80))
    y = np.clip(y - y.mean() + h / 2 + 22 * np.sin(x / 16), 8, h - 8)
    d.line(list(zip(x.tolist(), y.tolist())), fill=20, width=3)
    return im.filter(ImageFilter.GaussianBlur(0.6))


def add_signature(im: Image.Image, sig: Image.Image, xy: tuple[int, int]) -> tuple[int, int, int, int]:
    arr = np.asarray(im).copy()
    s = np.asarray(sig).astype(float) / 255.0
    x, y = xy
    h, w = s.shape
    region = arr[y : y + h, x : x + w].astype(float)
    arr[y : y + h, x : x + w] = (region * s[..., None]).astype(np.uint8)
    im.paste(Image.fromarray(arr))
    return (x, y, x + w, y + h)


def write_pdf_text(path: Path, lines: list[tuple[float, float, str]], fontsize: float = 11) -> None:
    import pymupdf

    pdf = pymupdf.open()
    page = pdf.new_page(width=595, height=842)
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=fontsize)
    pdf.set_metadata({"producer": "UnitTest", "creator": "UnitTest"})
    pdf.save(path)
    pdf.close()
