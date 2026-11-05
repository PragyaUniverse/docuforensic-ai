"""Handwriting is detected from its shape, and an AI reading never overwrites what OCR read."""
import numpy as np
from PIL import Image, ImageDraw

from models.schemas import BBox, TextSource
from pipeline import handwriting
from pipeline.handwriting import handwriting_score, page_is_handwritten, read_handwriting
from tests.pipeline.fixtures import font, salary_slip


def _printed() -> np.ndarray:
    im = Image.new("L", (520, 70), 250)
    ImageDraw.Draw(im).text((14, 12), "Senior Data Analyst", font=font(size=34), fill=20)
    return np.asarray(im)


def _wobbly(seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    im = Image.new("L", (560, 110), 250)
    draw = ImageDraw.Draw(im)
    x = 14
    for ch in "Senior Data Analyst":
        f = font(size=int(rng.integers(24, 44)))
        draw.text((x, 26 + int(rng.integers(-11, 11))), ch, font=f, fill=30)
        x += int(draw.textlength(ch, font=f)) + 2
    return np.asarray(im)


def test_uneven_writing_scores_higher_than_print():
    assert handwriting_score(_wobbly()) > handwriting_score(_printed()) * 2


def test_stacked_printed_lines_do_not_look_handwritten():
    im = Image.new("L", (520, 170), 250)
    draw = ImageDraw.Draw(im)
    for i, line in enumerate(("Flat 304, Lakeview Residency", "12th Main Road, Indiranagar", "Bengaluru 560038")):
        draw.text((14, 12 + i * 50), line, font=font(size=30), fill=20)
    assert handwriting_score(np.asarray(im)) < handwriting.HANDWRITTEN_SCORE


def test_a_printed_page_is_not_treated_as_handwritten(prepare):
    doc = prepare(salary_slip()[0])
    gray = np.asarray(Image.open(handwriting.from_rel(doc.pages[0].image_path)).convert("L"))
    assert not page_is_handwritten(gray, doc.fields)[0]


def test_a_printed_page_never_reaches_the_ai_model(prepare, monkeypatch):
    calls = []
    monkeypatch.setattr(handwriting.vision, "available", lambda: True)
    monkeypatch.setattr(handwriting.vision, "read_image", lambda png: calls.append(1) or "anything")
    read_handwriting(prepare(salary_slip()[0]))
    assert not calls


def test_ai_reading_flags_a_disagreement_but_keeps_the_ocr_value(prepare, monkeypatch):
    doc = prepare(salary_slip()[0])
    before = {f.id: f.value_raw for f in doc.fields}
    monkeypatch.setattr(handwriting, "page_is_handwritten", lambda gray, fields: (True, 0.4))
    monkeypatch.setattr(handwriting.vision, "available", lambda: True)
    monkeypatch.setattr(handwriting.vision, "read_image", lambda png: "Something Else 123")
    read_handwriting(doc)
    for f in doc.fields:
        if f.id in before:
            assert f.value_raw == before[f.id] and f.confidence <= handwriting.AI_READING_CONFIDENCE
    assert doc.metadata["handwriting"]["disagreements"]


def test_without_a_model_nothing_is_invented(prepare, monkeypatch):
    doc = prepare(salary_slip()[0])
    count = len(doc.fields)
    monkeypatch.setattr(handwriting, "page_is_handwritten", lambda gray, fields: (True, 0.4))
    monkeypatch.setattr(handwriting.vision, "available", lambda: False)
    read_handwriting(doc)
    assert len(doc.fields) == count
    assert not doc.metadata["handwriting"]["disagreements"]
    assert all(f.source != TextSource.llm for f in doc.fields)


def test_implausible_readings_are_ignored():
    from models.schemas import ValueType

    assert not handwriting._plausible("not a date", ValueType.date)
    assert handwriting._plausible("14/03/1991", ValueType.date)
    assert isinstance(BBox(x0=0, y0=0, x1=1, y1=1), BBox)
