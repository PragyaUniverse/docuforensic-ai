from datetime import date

import pytest

from backend.contextual import repair_transaction_row, rows_not_extracted, verify_within_document
from models.schemas import DocType, FindingStatus, Severity, TextSource
from tests.backend.helpers import make_doc, txn_table


def detectors(findings):
    return [f.detector for f in findings]


def test_clean_salary_slip_has_no_arithmetic_findings():
    doc = make_doc(DocType.salary_slip, {"basic_pay": "36,000.00", "hra": "14,400.00", "other_allowances": "13,200.50",
                                         "gross_pay": "63,600.50", "total_deductions": "5,170.50", "net_pay": "58,430.00"})
    assert "context.arithmetic_salary" not in detectors(verify_within_document(doc))


def test_within_a_rupee_rounding_is_not_flagged():
    doc = make_doc(DocType.salary_slip, {"gross_pay": "63,600.50", "total_deductions": "5,170.00", "net_pay": "58,430.00"})
    assert "context.arithmetic_salary" not in detectors(verify_within_document(doc))


def test_altered_net_pay_is_an_inconsistency_with_all_fields_linked():
    doc = make_doc(DocType.salary_slip, {"gross_pay": "54,000.00", "total_deductions": "5,680.00", "net_pay": "84,320.00"})
    found = [f for f in verify_within_document(doc) if f.detector == "context.arithmetic_salary"]
    assert len(found) == 1
    f = found[0]
    assert f.status == FindingStatus.INCONSISTENCY and f.severity == Severity.high
    assert "48,320.00" in f.explanation and "84,320.00" in f.explanation
    assert len(f.related_field_ids) == 3 and f.bbox is not None


@pytest.mark.parametrize("value", ["26,4", "12,"])
def test_truncated_reading_is_an_observation_that_names_ocr_not_a_conflict(value):
    doc = make_doc(DocType.salary_slip, {"basic_pay": "44,000.00", "hra": "17,600.00", "other_allowances": value,
                                         "gross_pay": "88,000.00"}, source=TextSource.ocr_rapid)
    found = [f for f in verify_within_document(doc) if f.detector == "context.arithmetic_salary"]
    assert len(found) == 1
    assert found[0].status == FindingStatus.OBSERVATION and found[0].severity == Severity.low
    assert "OCR misread" in found[0].explanation and value in found[0].explanation


def test_implausibly_small_operand_is_discounted_and_named():
    doc = make_doc(DocType.salary_slip, {"basic_pay": "44,000.00", "hra": "12.00", "other_allowances": "26,400.00",
                                         "gross_pay": "88,000.00"}, source=TextSource.ocr_rapid, confidence=0.97)
    found = next(f for f in verify_within_document(doc) if f.detector == "context.arithmetic_salary")
    assert found.status == FindingStatus.INCONSISTENCY and found.confidence < 0.5 and found.severity == Severity.low
    assert "OCR misread is a possible cause" in found.explanation and "HRA" in found.explanation


def test_a_clean_text_layer_sum_conflict_keeps_full_weight():
    doc = make_doc(DocType.salary_slip, {"basic_pay": "44,000.00", "hra": "17,600.00", "other_allowances": "26,400.00",
                                         "gross_pay": "98,000.00"})
    found = next(f for f in verify_within_document(doc) if f.detector == "context.arithmetic_salary")
    assert found.confidence > 0.85 and "OCR" not in found.explanation


def test_low_ocr_confidence_lowers_confidence_and_says_so():
    high = make_doc(DocType.salary_slip, {"gross_pay": "54,000.00", "total_deductions": "5,680.00", "net_pay": "84,320.00"},
                    source=TextSource.ocr_rapid, confidence=0.98)
    low = make_doc(DocType.salary_slip, {"gross_pay": "54,000.00", "total_deductions": "5,680.00", "net_pay": "84,320.00"},
                   source=TextSource.ocr_rapid, confidence=0.3)
    fh = next(f for f in verify_within_document(high) if f.detector == "context.arithmetic_salary")
    fl = next(f for f in verify_within_document(low) if f.detector == "context.arithmetic_salary")
    assert fl.confidence < fh.confidence * 0.7
    assert "OCR" in fl.explanation and fl.severity != Severity.high


GOOD_ROWS = [
    ["03-May-2026", "UPI RENT", "19,000.00", "", "1,23,380.25"],
    ["07-May-2026", "POWER", "1,310.21", "", "1,22,070.04"],
    ["29-May-2026", "NEFT SALARY", "", "58,430.00", "1,80,500.04"],
]


def statement(rows, **extra):
    fields = {"opening_balance": "1,42,380.25", "closing_balance": "1,80,500.04",
              "statement_period": "01-May-2026 to 31-May-2026", **extra}
    return make_doc(DocType.bank_statement, fields, tables=[txn_table(rows)])


def test_reconciling_statement_is_clean():
    assert not {"context.arithmetic_balance", "context.date_order"} & set(detectors(verify_within_document(statement(GOOD_ROWS))))


def test_altered_balance_is_flagged_at_the_row():
    rows = [list(r) for r in GOOD_ROWS]
    rows[1][4] = "1,32,070.04"
    found = [f for f in verify_within_document(statement(rows)) if f.detector == "context.arithmetic_balance"]
    assert found and "row 2" in found[0].explanation
    assert found[0].bbox.y0 == 530


def test_split_balance_is_reassembled_without_changing_digits():
    table = txn_table([["03-May-2026", "UPI RENT 1,23,380.", "19,000.00", "", "25"]])
    repair_transaction_row(table.rows[0], 1, 4)
    assert table.rows[0][1].text == "UPI RENT" and table.rows[0][4].text == "1,23,380.25"


def test_unextracted_rows_soften_a_balance_break(monkeypatch):
    from models.schemas import BBox, Word

    rows = [list(r) for r in GOOD_ROWS]
    rows[1][4] = "1,32,070.04"
    doc = statement(rows)
    from models.schemas import Page

    doc.pages = [Page(index=0, width=1654, height=2339, image_path="x.png", words=[
        Word(text=t, confidence=0.9, bbox=BBox(x0=100, y0=y, x1=190, y1=y + 20), page=0, source=TextSource.ocr_rapid)
        for t, y in (("03-May-2026", 500), ("05-Ju1-2026", 515), ("07-May-2026", 530), ("29-May-2026", 560))])]
    assert rows_not_extracted(doc, doc.tables[0]) == 1
    found = next(f for f in verify_within_document(doc) if f.detector == "context.arithmetic_balance")
    assert "not extracted" in found.explanation and found.severity != Severity.high


def test_transactions_outside_period_flagged():
    rows = [list(r) for r in GOOD_ROWS]
    rows[2][0] = "29-Jun-2026"
    found = verify_within_document(statement(rows))
    assert any(f.detector == "context.date_order" and "outside" in f.title for f in found)


def test_ocr_zero_for_letter_o_in_period_does_not_flag_dates():
    rows = [list(r) for r in GOOD_ROWS]
    rows[2][0] = "29-Sep-2026"
    doc = statement(rows)
    next(f for f in doc.fields if f.name == "statement_period").value_raw = "01-May-2026 to 31-0ct-2026"
    assert not any(f.detector == "context.date_order" for f in verify_within_document(doc))


def test_date_logic():
    doc = make_doc(DocType.application_form, {"date_of_birth": "19/07/2015", "date_of_joining": "01/01/2020",
                                              "application_date": "01/01/2030"})
    titles = [f.title for f in verify_within_document(doc, today=date(2026, 11, 4)) if f.detector == "context.date_order"]
    assert any("young" in t for t in titles) and any("future" in t for t in titles)


def test_id_checks():
    doc = make_doc(DocType.id_proof, {"id_number": "1234 5678 9012", "pan_number": "ABC12"})
    found = [f for f in verify_within_document(doc) if f.detector == "context.id_checksum"]
    assert len(found) == 2


def test_missing_fields_are_observations():
    doc = make_doc(DocType.address_proof, {"person_name": "A B"})
    doc.missing_fields = ["bill_date"]
    found = next(f for f in verify_within_document(doc) if f.detector == "context.missing_field")
    assert found.status == FindingStatus.OBSERVATION and "bill date" in found.explanation


def test_agreeing_repeats_are_not_flagged_but_conflicting_repeats_are():
    doc = make_doc(DocType.id_proof, {"person_name": "A B"})
    doc.fields.append(doc.fields[0].model_copy(update={"id": "other"}))
    doc.duplicated_fields = ["person_name"]
    assert "context.duplicate_field" not in detectors(verify_within_document(doc))
    doc.fields[1].value_raw = "C D"
    assert "context.duplicate_field" in detectors(verify_within_document(doc))


def test_amount_words_parse_with_or_without_spaces():
    from backend.contextual import parse_amount_words as parse

    assert parse("Rupees Forty Eight Thousand Three Hundred Twenty Only") == 48320
    assert parse("RupeesFortyEightThousandThreeHundredTwentyOnly") == 48320
    assert parse("One Lakh Twenty Five Thousand") == 125000
    assert parse("Two Crore Five Lakh") == 20500000
    assert parse("Fourteen Thousand Sixty") == 14060


def test_amount_words_refuse_to_guess_on_a_misread():
    from backend.contextual import parse_amount_words as parse

    assert parse("Rupees Fo7ty Thousand Only") is None
    assert parse("Rupees Only") is None
    assert parse("") is None
