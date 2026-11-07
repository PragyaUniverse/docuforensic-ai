"""Seen before: repeated details across applications are found, explained and never called a verdict."""
import numpy as np
import pytest

from backend import crosscase, db
from config.settings import settings
from models.schemas import BBox, Case, DocType, Document, Field, FindingStatus, Page, TextSource

BOX = BBox(x0=10, y0=10, x1=200, y1=40)


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def _doc(case_id: str, **fields: str) -> Document:
    doc = Document(case_id=case_id, filename="application_form.png", sha256="x", doc_type=DocType.application_form,
                   pages=[Page(index=0, width=1000, height=1000, image_path="none.png")])
    doc.fields = [Field(doc_id=doc.id, name=k, value_raw=v, confidence=0.95, page=0, bbox=BOX, source=TextSource.ocr_rapid)
                  for k, v in fields.items()]
    return doc


def _case(name: str, demo_key: str | None = None, **fields: str) -> tuple[Case, Document]:
    case = db.save_case(Case(name=name, is_demo=bool(demo_key), demo_key=demo_key))
    doc = db.save_document(_doc(case.id, **fields))
    crosscase.record(case, [doc])
    return case, doc


def test_text_details_are_normalised_before_comparing():
    assert crosscase._norm_text("phone", "+91 90000 01234") == crosscase._norm_text("phone", "9000001234")
    assert crosscase._norm_text("bank_account_number", "5010 0234 5678 12") == "50100234567812"
    assert crosscase._norm_text("pan_number", "zzepr6247q") == "ZZEPR6247Q"
    assert crosscase._norm_text("email", "Kavya.Rao@Example.com") == "kavya.rao@example.com"
    assert crosscase._norm_text("phone", "12345") is None  # too short to identify anyone


def test_values_are_masked_when_shown():
    assert crosscase.mask("bank_account_number", "50100234567812") == "•••• 7812"
    assert crosscase.mask("email", "kavya.rao@example.com") == "k•••@example.com"


def test_a_shared_account_under_another_name_is_an_inconsistency(tmp_path):
    _case("Earlier", person_name="Meenakshi Iyer", bank_account_number="50100234567812")
    case, doc = _case("New", person_name="Kavya Rao", bank_account_number="50100234567812", phone="9000001234")
    result = crosscase.matches(case.id)
    assert result["checked_cases"] == 1
    (group,) = result["groups"]
    assert group["case_name"] == "Earlier" and not group["same_applicant"]
    assert [e["kind"] for e in group["elements"]] == ["bank_account_number"]
    assert group["elements"][0]["value"] == "•••• 7812"

    (finding,) = crosscase.findings_for(case, [doc], tmp_path)
    assert finding.status == FindingStatus.INCONSISTENCY
    assert finding.detector == crosscase.DETECTOR
    assert "fraud" not in (finding.title + finding.explanation).lower()
    assert finding.benign_alternatives and finding.recommended_verification
    assert finding.evidence[0].data["other_case_name"] == "Earlier"


def test_same_applicant_reapplying_is_only_an_observation(tmp_path):
    _case("First try", person_name="Kavya Anand Rao", phone="9000001234")
    case, doc = _case("Second try", person_name="Kavya A. Rao", phone="+91 90000 01234")
    (finding,) = crosscase.findings_for(case, [doc], tmp_path)
    assert finding.status == FindingStatus.OBSERVATION


def test_the_same_demo_loaded_twice_is_not_a_repeat():
    _case("Case A", demo_key="case_a_clean", person_name="Priya", phone="9000001234")
    case, _ = _case("Case A again", demo_key="case_a_clean", person_name="Priya", phone="9000001234")
    assert crosscase.matches(case.id)["groups"] == []


def test_nothing_shared_means_nothing_reported(tmp_path):
    _case("Other", person_name="Someone Else", phone="9111111111")
    case, doc = _case("Mine", person_name="Kavya Rao", phone="9000001234")
    assert crosscase.matches(case.id)["groups"] == []
    assert crosscase.findings_for(case, [doc], tmp_path) == []


def _photo(seed: int, tint: tuple[int, int, int]) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((120, 100, 3), 255, dtype=np.uint8)
    img[20:110, 10:90] = np.clip(np.array(tint) + rng.normal(0, 20, (90, 80, 3)), 0, 255).astype(np.uint8)
    return img


def test_photos_match_only_when_the_image_is_the_same():
    box = BBox(x0=0, y0=0, x1=100, y1=120)
    a = crosscase._image_print("photo", _photo(1, (150, 120, 200)), box)
    rescan = _photo(1, (150, 120, 200)).astype(int) + np.random.default_rng(9).normal(0, 3, (120, 100, 3)).astype(int)
    b = crosscase._image_print("photo", np.clip(rescan, 0, 255).astype(np.uint8), box)
    c = crosscase._image_print("photo", _photo(2, (90, 160, 110)), box)
    pa, pb, pc = ({"kind": "photo", "value": p["phash"], "thumb": p["thumb"]} for p in (a, b, c))
    assert crosscase._same(pa, pb) is not None
    assert crosscase._same(pa, pc) is None


def test_cases_analysed_before_this_check_are_fingerprinted_on_demand():
    from models.schemas import CaseStatus

    old = db.save_case(Case(name="Older", status=CaseStatus.complete))
    db.save_document(_doc(old.id, person_name="Someone Else", phone="9000001234"))
    case, _ = _case("New", person_name="Kavya Rao", phone="9000001234")
    (group,) = crosscase.matches(case.id)["groups"]
    assert group["case_name"] == "Older"


def test_copies_of_one_demo_count_as_one_application():
    _case("Case C", demo_key="case_c_crossdoc", person_name="Meenakshi", bank_account_number="50100234567812")
    _case("Case C", demo_key="case_c_crossdoc", person_name="Meenakshi", bank_account_number="50100234567812")
    case, _ = _case("Case E", demo_key="case_e_repeat", person_name="Kavya", bank_account_number="50100234567812")
    result = crosscase.matches(case.id)
    assert result["checked_cases"] == 1
    (group,) = result["groups"]
    assert group["copies"] == 2
