"""Draft verification requests ask the right issuer about exactly the doubtful values, without accusing anyone."""
import pytest
from fastapi.testclient import TestClient

from audit import chain
from backend import db, verification_letter
from backend.app import app
from config.settings import settings
from models.schemas import (
    BBox,
    Case,
    DocType,
    Document,
    EvidenceItem,
    EvidenceKind,
    Field,
    Finding,
    FindingCategory,
    FindingStatus,
    Page,
    Severity,
    TextSource,
)

BOX = BBox(x0=10, y0=10, x1=200, y1=40)


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def _doc(case_id: str, doc_type: DocType, **fields: str) -> Document:
    doc = Document(case_id=case_id, filename=f"{doc_type.value}.pdf", sha256="x", doc_type=doc_type,
                   pages=[Page(index=0, width=1000, height=1000, image_path="none.png")])
    doc.fields = [Field(doc_id=doc.id, name=k, value_raw=v, confidence=0.95, page=0, bbox=BOX, source=TextSource.text_layer)
                  for k, v in fields.items()]
    return doc


def _ref(doc: Document, name: str, value: str, normalized: str | None = None) -> EvidenceItem:
    return EvidenceItem(kind=EvidenceKind.field_ref, label=name, doc_id=doc.id, page=0, bbox=BOX,
                        data={"field": name, "value": value, "normalized": normalized or value})


def _finding(case_id: str, doc: Document, evidence, category=FindingCategory.cross_document, detector="cross.dob_mismatch",
             related=()) -> Finding:
    return Finding(case_id=case_id, status=FindingStatus.INCONSISTENCY, category=category, severity=Severity.high,
                   confidence=0.9, title="t", doc_id=doc.id, page=0, bbox=BOX, related_doc_ids=list(related),
                   evidence=evidence, explanation="e", detector=detector)


def test_conflicting_values_are_asked_about_once_each_and_formats_are_merged():
    case = Case(name="C")
    app_form = _doc(case.id, DocType.application_form, person_name="Meenakshi Iyer")
    decl = _doc(case.id, DocType.declaration)
    idp = _doc(case.id, DocType.id_proof)
    f = _finding(case.id, app_form, [
        _ref(app_form, "date_of_birth", "19/07/1988", "1988-07-19"),
        _ref(decl, "date_of_birth", "19-07-1988", "1988-07-19"),
        _ref(idp, "date_of_birth", "19/07/1986", "1986-07-19"),
    ], related=[decl.id, idp.id])
    letter = verification_letter.draft(case, [app_form, decl, idp], f)
    assert letter["available"] and letter["questions"] == 1
    body = letter["body"]
    assert "19/07/1988 on the application form and declaration" in body
    assert "19/07/1986 on the ID document" in body
    assert "19-07-1988" not in body  # the same date, so it isn't asked twice
    assert "Meenakshi Iyer" in body and "DF-" in body


def test_a_salary_question_goes_to_the_employer_named_on_the_slip():
    case = Case(name="B")
    slip = _doc(case.id, DocType.salary_slip, employer_name="Kestrel Logistics Pvt. Ltd.", net_pay="84,320.00")
    f = _finding(case.id, slip, [
        _ref(slip, "net_pay", "84,320.00"),
        EvidenceItem(kind=EvidenceKind.raw_value, label="words", doc_id=slip.id, page=0,
                     data={"text": "Net Pay in words: Rupees Forty Eight Thousand", "value_in_words": 48000, "value_in_figures": 84320}),
    ], category=FindingCategory.contextual, detector="context.amount_in_words")
    letter = verification_letter.draft(case, [slip], f)
    assert letter["to"] == "HR / Payroll, Kestrel Logistics Pvt. Ltd."
    assert '"Rupees Forty Eight Thousand" in words' in letter["body"]
    assert "Ltd.." not in letter["body"]


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_letters_never_accuse_and_say_nothing_is_sent(lang):
    case = Case(name="B")
    slip = _doc(case.id, DocType.salary_slip, employer_name="Kestrel", net_pay="84,320.00")
    f = _finding(case.id, slip, [_ref(slip, "net_pay", "84,320.00")], category=FindingCategory.visual, detector="visual.overwrite")
    letter = verification_letter.draft(case, [slip], f, lang)
    text = (letter["body"] + letter["note"]).lower()
    for word in ("fraud", "forged", "fake", "manipulat", "tamper", "धोखा", "जाली", "नकली"):
        assert word not in text
    assert letter["lang"] == lang
    assert ("never sends" in text) if lang == "en" else ("नहीं भेजता" in text)


def test_endpoint_drafts_and_records_it_in_the_history():
    case = db.save_case(Case(name="B"))
    slip = db.save_document(_doc(case.id, DocType.salary_slip, employer_name="Kestrel", net_pay="84,320.00"))
    f = db.save_finding(_finding(case.id, slip, [_ref(slip, "net_pay", "84,320.00")]))
    client = TestClient(app)
    res = client.get(f"/api/findings/{f.id}/verification-request?lang=hi")
    assert res.status_code == 200, res.text
    assert res.json()["lang"] == "hi" and "महोदय" in res.json()["body"]
    assert any(e.action == "verification_request.drafted" for e in chain.entries(case.id))
    assert client.get("/api/findings/fnd_missing/verification-request").status_code == 404
    assert client.get(f"/api/findings/{f.id}/verification-request?lang=fr").status_code == 422
