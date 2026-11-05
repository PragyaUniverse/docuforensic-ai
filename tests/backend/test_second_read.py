"""Confusable characters are settled by a second OCR engine where possible."""
from unittest.mock import patch

from backend.normalize import ocr_adjustment
from models.schemas import BBox, Field, TextSource


def _field(value, source=TextSource.ocr_rapid):
    return Field(doc_id="d", name="date_of_birth", value_raw=value, confidence=0.99, page=0,
                 bbox=BBox(x0=0, y0=0, x1=10, y1=10), source=source)


def _adjust(reads):
    docs = {"d": object()}
    with patch("pipeline.ocr.reread_region", side_effect=reads):
        return ocr_adjustment([_field("19/07/1986"), _field("19/07/1988")], "19/07/1986", "19/07/1988", docs=docs)


def test_agreeing_second_engine_raises_confidence():
    factor, note = _adjust(["19/07/1986", "19/07/1988"])
    assert factor == 0.9 and "second" in note


def test_disagreeing_second_engine_lowers_confidence():
    factor, note = _adjust(["19/07/1988", "19/07/1988"])
    assert factor == 0.5 and "reading error" in note


def test_unreadable_region_keeps_the_caution():
    factor, _ = _adjust([None, None])
    assert factor == 0.6


def test_without_documents_nothing_is_reread():
    with patch("pipeline.ocr.reread_region") as reread:
        factor, _ = ocr_adjustment([_field("19/07/1986")], "19/07/1986", "19/07/1988")
    assert factor == 0.6 and not reread.called
