from backend.orchestrator import apply_visible_readings, compute_risk
from models.schemas import (
    BBox, EvidenceItem, EvidenceKind, Finding, FindingCategory, FindingStatus, DocType, ProcessingStatus, Severity,
    TextSource,
)
from tests.backend.helpers import make_doc, txn_table


def mismatch(doc, bbox):
    return Finding(case_id="c1", status=FindingStatus.POTENTIAL_MANIPULATION, category=FindingCategory.structural,
                   severity=Severity.high, confidence=0.9, title="t", explanation="e", detector="pdf.text_vs_pixels",
                   doc_id=doc.id, page=0, bbox=bbox, evidence=[EvidenceItem(
                       kind=EvidenceKind.raw_value, label="cmp", page=0, bbox=bbox,
                       data={"text_layer": "62,400.00", "rendered_ocr": "86,400.00", "ocr_confidence": 0.98,
                             "digits_differ": True})])


def test_checks_use_the_value_a_person_sees_and_the_hidden_one_stays_recorded():
    doc = make_doc(DocType.salary_slip, {"net_pay": "62,400.00", "gross_pay": "68,000.00"})
    net = doc.fields[0]
    finding = mismatch(doc, net.bbox)
    assert apply_visible_readings([doc], [finding]) == 1
    assert net.value_raw == "86,400.00" and net.source == TextSource.ocr_rapid and net.confidence == 0.98
    assert doc.fields[1].value_raw == "68,000.00"
    assert doc.metadata["visible_readings"][0]["text_layer"] == "62,400.00"
    assert net.id in finding.related_field_ids


def test_table_cells_under_a_mismatch_also_use_the_visible_value():
    doc = make_doc(DocType.bank_statement, {}, tables=[txn_table([["30-Oct-2026", "SAL", "", "62,400.00 86,400.00", "1.00"]])])
    cell = doc.tables[0].rows[0][3]
    assert apply_visible_readings([doc], [mismatch(doc, BBox(x0=cell.bbox.x0, y0=cell.bbox.y0, x1=cell.bbox.x1, y1=cell.bbox.y1))]) == 1
    assert cell.text == "86,400.00"


def finding(status, severity, score=None, confidence=0.9):
    return Finding(case_id="c", status=status, category=FindingCategory.visual, severity=severity, confidence=confidence,
                   title="t", explanation="e", detector="d", fused_score=score)


def docs_ok():
    doc = make_doc(DocType.salary_slip, {})
    from models.schemas import Page

    doc.pages = [Page(index=0, width=10, height=10, image_path="x")]
    return [doc]


def test_risk_rules():
    docs = docs_ok()
    assert compute_risk([], docs).value == "low"
    assert compute_risk([finding(FindingStatus.OBSERVATION, Severity.low)], docs).value == "low"
    assert compute_risk([finding(FindingStatus.INCONSISTENCY, Severity.low)], docs).value == "low"
    assert compute_risk([finding(FindingStatus.INCONSISTENCY, Severity.medium)], docs).value == "medium"
    assert compute_risk([finding(FindingStatus.POTENTIAL_MANIPULATION, Severity.low, score=0.4)], docs).value == "medium"
    assert compute_risk([finding(FindingStatus.POTENTIAL_MANIPULATION, Severity.high, score=0.7)], docs).value == "high"
    assert compute_risk([finding(FindingStatus.INCONSISTENCY, Severity.medium)] * 3, docs).value == "high"


def test_risk_is_undetermined_when_nothing_could_be_read():
    doc = make_doc(DocType.unknown, {})
    doc.status = ProcessingStatus.failed
    assert compute_risk([], [doc]).value == "undetermined"
