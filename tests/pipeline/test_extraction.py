import json

import numpy as np
import pytest
from PIL import Image

from models.schemas import BBox, DocType, ProcessingStatus, TextSource, ValueType, Word
from pipeline.classify import classify
from pipeline.extract import _check_amounts, extract_fields, repair_pan
from pipeline.ingest import ingest_file
from pipeline.layout import group_lines
from pipeline.normalize import norm_address, norm_date, norm_money, norm_period
from pipeline.ocr import (
    OcrLine,
    _line_to_words,
    estimate_skew_deg,
    extract_words,
    merge_fragments,
    repair_text,
)
from tests.pipeline.fixtures import salary_slip, write_pdf_text


def _word(text, x0, y0, x1, y1):
    return Word(text=text, confidence=0.95, bbox=BBox(x0=x0, y0=y0, x1=x1, y1=y1), page=0, source=TextSource.ocr_rapid)


def test_normalizers():
    assert norm_money("Rs. 85,400.00") == "85400.00"
    assert norm_money("₹1,23,456") == "123456.00"
    assert norm_money("no amount") is None
    assert norm_date("14/03/1991") == "1991-03-14"
    assert norm_date("02-Aug-2021") == "2021-08-02"
    assert norm_date("99/99/2021") is None
    assert norm_period("October 2026") == "2026-10"
    assert norm_period("01-May-2026 to 31-Oct-2026") == "2026-05-01/2026-10-31"
    assert norm_address("12th Main Rd., Pune") == "12TH MAIN ROAD, PUNE"


def test_ocr_text_repairs():
    assert repair_text("12-0ct-2026") == "12-Oct-2026"
    assert repair_text("Society，") == "Society,"
    assert repair_pan("ZZCP15520R") == "ZZCPI5520R"
    assert repair_pan("not a pan") is None


def test_lost_spaces_recovered_from_tesseract_words():
    chars = []
    text = "DateofBirth:14/03/1991"
    for i, ch in enumerate(text):
        chars.append((ch, 0.99, BBox(x0=100 + 14 * i, y0=50, x1=114 + 14 * i, y1=80)))
    line = OcrLine(text=text, confidence=0.99, bbox=BBox(x0=100, y0=50, x1=420, y1=80), tilt_deg=0, chars=chars)
    tess = [
        ("Date", 0.9, BBox(x0=100, y0=52, x1=155, y1=78)),
        ("of", 0.9, BBox(x0=160, y0=52, x1=185, y1=78)),
        ("Birth:", 0.9, BBox(x0=190, y0=52, x1=270, y1=78)),
        ("14/03/1991", 0.9, BBox(x0=275, y0=52, x1=420, y1=78)),
    ]
    assert [w.text for w in _line_to_words(line, tess, 0)] == ["Date", "of", "Birth:", "14/03/1991"]


def test_fragmented_number_merged_from_tesseract():
    def frag(text, x0, x1):
        step = (x1 - x0) / len(text)
        chars = [(c, 0.9, BBox(x0=x0 + i * step, y0=10, x1=x0 + (i + 1) * step, y1=30)) for i, c in enumerate(text)]
        return OcrLine(text=text, confidence=0.9, bbox=BBox(x0=x0, y0=10, x1=x1, y1=30), tilt_deg=0, chars=chars)

    lines = [frag("12,", 680, 725), frag("000.00", 714, 800)]
    merged = merge_fragments(lines, [("12,000.00", 0.96, BBox(x0=682, y0=10, x1=809, y1=30))])
    assert [ln.text for ln in merged] == ["12,000.00"]


def test_skew_estimate_and_deskewed_grouping():
    words = []
    tan = np.tan(np.radians(2.0))
    for row in range(5):
        for col in range(4):
            x = 100 + col * 350
            y = 100 + row * 90 + x * tan
            words.append(_word(f"w{row}{col}", x, y, x + 200, y + 30))
    assert abs(estimate_skew_deg(words) - 2.0) < 0.4
    lines = group_lines(words, 2.0)
    assert len(lines) == 5 and all(len(ln.words) == 4 for ln in lines)


def test_fields_have_values_boxes_and_confidence(prepare):
    im, boxes = salary_slip()
    doc = prepare(im)
    assert doc.status == ProcessingStatus.ok
    assert doc.doc_type == DocType.salary_slip and doc.doc_type_confidence > 0.7
    by_name = {f.name: f for f in doc.fields}
    assert by_name["net_pay"].value_norm == "63600.00"
    assert by_name["person_name"].value_norm == "asha verma"
    assert by_name["pay_period"].value_norm == "2026-03"
    box = boxes["Net Pay"]
    truth = BBox(x0=box[0], y0=box[1], x1=box[2], y1=box[3])
    assert by_name["net_pay"].bbox.iou(truth) > 0.5
    assert all(0 < f.confidence <= 1 for f in doc.fields)
    assert not doc.missing_fields
    assert doc.metadata["relationships"]
    assert doc.sections


def test_missing_and_duplicated_fields_reported(prepare):
    rows = [("Employee Name", "Asha Verma"), ("Employee Name", "Usha Varma"), ("Basic Pay", "Rs. 45,000.00")]
    doc = prepare(salary_slip(rows=rows)[0])
    assert "net_pay" in doc.missing_fields
    assert "person_name" in doc.duplicated_fields


def test_incomplete_amount_is_reread_or_discounted(prepare):
    doc = prepare(salary_slip()[0])
    hra = next(f for f in doc.fields if f.name == "hra")
    # What OCR produced in a real run: the amount cut short.
    hra.value_raw, hra.value_norm = "18,", "18.00"
    hra.bbox = BBox(x0=hra.bbox.x0, y0=hra.bbox.y0, x1=hra.bbox.x0 + 40, y1=hra.bbox.y1)
    _check_amounts(doc)
    assert hra.value_norm == "18000.00" or hra.confidence <= 0.3
    assert doc.metadata["amount_rereads"][0]["name"] == "hra"


def test_unreadable_amount_loses_confidence_when_reread_fails(prepare, monkeypatch):
    from pipeline import extract as mod

    doc = prepare(salary_slip()[0])
    hra = next(f for f in doc.fields if f.name == "hra")
    hra.value_raw, hra.value_norm = "18,", "18.00"
    monkeypatch.setattr(mod, "_reread_money", lambda *_: None)
    _check_amounts(doc)
    assert hra.confidence <= 0.3


def test_digital_pdf_uses_text_layer(tmp_path):
    p = tmp_path / "d.pdf"
    lines = [(50, 60, "SALARY SLIP"), (50, 100, "Employee Name:"), (250, 100, "Asha Verma"), (50, 130, "Net Pay:"), (250, 130, "Rs. 63,600.00"), (50, 160, "Basic Pay:"), (250, 160, "Rs. 45,000.00"), (50, 190, "Earnings and Deductions")]
    write_pdf_text(p, lines)
    doc = ingest_file(p, "c", tmp_path)
    extract_words(doc, tmp_path)
    classify(doc)
    extract_fields(doc)
    assert doc.pages[0].text_source == TextSource.text_layer
    net = next(f for f in doc.fields if f.name == "net_pay")
    assert net.source == TextSource.text_layer and net.value_type == ValueType.money


def test_blank_page_degrades_with_message(prepare):
    doc = prepare(Image.new("RGB", (800, 1000), "white"))
    assert doc.status == ProcessingStatus.degraded
    assert "text" in doc.status_message
    assert doc.doc_type == DocType.unknown


def test_low_confidence_page_is_degraded(prepare, monkeypatch):
    from pipeline import ocr

    monkeypatch.setattr(ocr, "ocr_image", lambda img, page=0: ([_word("x1", 1, 1, 20, 20).model_copy(update={"confidence": 0.2})], TextSource.ocr_rapid))
    doc = prepare(salary_slip()[0])
    assert doc.status == ProcessingStatus.degraded
    assert "confidence" in doc.status_message


def test_ocr_engines_missing_is_reported_not_faked(prepare, monkeypatch):
    from pipeline import ocr

    monkeypatch.setattr(ocr, "ocr_image", lambda img, page=0: ([], None))
    monkeypatch.setattr(ocr, "_get_engine", lambda: None)
    doc = prepare(salary_slip()[0])
    assert doc.status == ProcessingStatus.degraded
    assert "OCR engine" in doc.status_message
    assert doc.fields == []


@pytest.mark.parametrize("case", ["case_a_clean", "case_b_visual", "case_c_crossdoc", "case_d_pdf"])
def test_dataset_field_accuracy(case, dataset, prepare):
    truth = json.loads((dataset / case / "ground_truth.json").read_text())
    total = correct = 0
    for spec in truth["documents"]:
        doc = prepare(dataset / case / spec["filename"])
        assert doc.doc_type.value == spec["doc_type"], spec["filename"]
        assert doc.format.value == spec["format"], spec["filename"]
        for name, want in spec["fields"].items():
            total += 1
            got = [f.value_norm or f.value_raw for f in doc.fields if f.name == name] + [f.value_raw for f in doc.fields if f.name == name]
            clean = lambda s: str(s).casefold().replace(" ", "").replace(",", "")
            correct += clean(want["value"]) in {clean(g) for g in got} or any(norm_money(str(g)) == norm_money(str(want["value"])) for g in got if norm_money(str(want["value"])))
    assert correct / total >= 0.95, f"{correct}/{total}"


__all__ = ["norm_address"]


def test_digit_misread_in_month_is_repaired():
    from pipeline.ocr import repair_text

    assert repair_text("03-Ju1-2026") == "03-Jul-2026"
    assert repair_text("12-0ct-2026") == "12-Oct-2026"
    assert repair_text("07 Au9 2026") == "07 Aug 2026"
    # Not a date, so left as read.
    assert repair_text("Ju1-2026") == "Ju1-2026"
    assert repair_text("A1B-99-X") == "A1B-99-X"


def test_amount_split_by_a_stray_space_is_rejoined():
    from models.schemas import BBox, TextSource, Word
    from pipeline.ocr import _join_split_amounts

    def word(text, x0, x1):
        return Word(text=text, confidence=0.9, bbox=BBox(x0=x0, y0=0, x1=x1, y1=20), page=0, source=TextSource.ocr_rapid)

    joined = _join_split_amounts([word("2,77", 0, 40), word("1.99", 44, 80)], 20)
    assert [w.text for w in joined] == ["2,771.99"]
    # Two separate amounts in neighbouring columns stay separate.
    apart = _join_split_amounts([word("1,310.21", 0, 80), word("5.00", 84, 120)], 20)
    assert [w.text for w in apart] == ["1,310.21", "5.00"]


def test_amount_with_dropped_digit_is_not_well_formed():
    from pipeline.extract import WELL_FORMED_MONEY

    for good in ("3,58,260.32", "85,400.00", "1,23,45,678.00", "999.50", "Rs. 45,000.00", "1200"):
        assert WELL_FORMED_MONEY.fullmatch(good), good
    for bad in ("3,58,20.32", "12,", "1,23,4.00"):
        assert not WELL_FORMED_MONEY.fullmatch(bad), bad
