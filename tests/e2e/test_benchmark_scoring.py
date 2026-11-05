"""The benchmark must be unable to flatter results. These tests attack the scoring itself."""
from __future__ import annotations

import json

import pytest

from models.schemas import (
    BBox,
    DocType,
    Document,
    EvidenceItem,
    EvidenceKind,
    Field,
    Finding,
    FindingCategory,
    FindingStatus,
    Severity,
    TextSource,
)
from scripts import run_benchmark as rb

FILES = {"d1": "salary_slip.png", "d2": "bank_statement.png", "d3": "id_proof.png"}
GT_BOX = [100, 100, 300, 150]
PAGE_BOX = BBox(x0=0, y0=0, x1=1654, y1=2339)
NEAR_BOX = BBox(x0=110, y0=105, x1=290, y1=145)
FIELD_BOX = BBox(x0=100, y0=100, x1=300, y1=150)


def finding(status=FindingStatus.POTENTIAL_MANIPULATION, doc_id="d1", page=0,
            bbox=NEAR_BOX, detector="visual.overwrite", **kw) -> Finding:
    return Finding(case_id="c", status=status, category=kw.pop("category", FindingCategory.visual),
                   severity=Severity.medium, confidence=0.8, title="t", explanation="e",
                   doc_id=doc_id, page=page, bbox=bbox, detector=detector, **kw)


def run(findings, docs=()) -> rb.CaseRun:
    return rb.CaseRun("case", list(docs), list(findings), FILES)


def truth(manips=None, discs=None, docs=None) -> dict:
    return {"manipulations": manips or [], "discrepancies": discs or [], "documents": docs or []}


def manip(**kw) -> dict:
    base = {"id": "m1", "type": "overwrite", "filename": "salary_slip.png", "page": 0,
            "bbox": GT_BOX, "expected_detectors": ["visual.overwrite"]}
    return {**base, **kw}


def test_exact_box_is_true_positive():
    s = rb.score_detection(run([finding()]), truth([manip()]))
    assert s["manipulations"][0]["localized_potential_manipulation"] is True
    assert s["potential_manipulation_matched"] == 1
    assert s["unmatched_findings"] == []


def test_whole_page_box_gets_no_credit():
    s = rb.score_detection(run([finding(bbox=PAGE_BOX)]), truth([manip()]))
    assert s["manipulations"][0]["localized_potential_manipulation"] is False
    assert s["potential_manipulation_matched"] == 0
    assert len(s["unmatched_findings"]) == 1


def test_wrong_page_wrong_document_and_distant_box_get_no_credit():
    for f in (finding(page=1), finding(doc_id="d2"),
              finding(bbox=BBox(x0=900, y0=900, x1=1100, y1=950))):
        s = rb.score_detection(run([f]), truth([manip()]))
        assert s["manipulations"][0]["localized_potential_manipulation"] is False, f


def test_tiny_box_inside_large_target_rejected_by_area_ratio():
    assert rb.boxes_overlap(BBox(x0=100, y0=100, x1=103, y1=103), rb._bbox(GT_BOX)) is False


def test_observation_does_not_count_for_strict_recall():
    s = rb.score_detection(run([finding(status=FindingStatus.OBSERVATION)]), truth([manip()]))
    row = s["manipulations"][0]
    assert row["localized_potential_manipulation"] is False
    assert row["any_status_flagged"] is True


def test_document_level_finding_needs_expected_detector():
    no_box_ok = finding(bbox=None, detector="visual.overwrite")
    no_box_wrong = finding(bbox=None, detector="metadata.exif")
    ok = rb.score_detection(run([no_box_ok]), truth([manip()]))["manipulations"][0]
    assert ok["doc_level_potential_manipulation"] and not ok["localized_potential_manipulation"]
    bad = rb.score_detection(run([no_box_wrong]), truth([manip()]))
    assert not bad["manipulations"][0]["doc_level_potential_manipulation"]
    assert len(bad["unmatched_findings"]) == 1


def test_located_evidence_can_localize_a_regionless_finding():
    ev = EvidenceItem(kind=EvidenceKind.crop, label="x", doc_id="d1", page=0,
                      bbox=BBox(x0=110, y0=105, x1=290, y1=145))
    s = rb.score_detection(run([finding(bbox=None, detector="x", evidence=[ev])]), truth([manip()]))
    assert s["manipulations"][0]["localized_potential_manipulation"] is True


def test_duplicate_detections_do_not_inflate_recall():
    s = rb.score_detection(run([finding(), finding(detector="visual.ela")]),
                           truth([manip(), manip(id="m2", bbox=[800, 800, 900, 850])]))
    a = rb.aggregate([s], [], [])
    assert a["manipulation"]["recall_localized"] == 0.5
    assert a["manipulation"]["precision"] == 1.0


def test_every_finding_on_a_clean_case_is_inventoried():
    fs = [finding(), finding(status=FindingStatus.OBSERVATION)]
    s = rb.score_detection(run(fs), truth())
    assert s["clean"] is True
    assert len(s["unmatched_findings"]) == 2
    a = rb.aggregate([s], [], [])
    assert a["clean_cases"]["potential_manipulation_findings"] == 1
    assert a["clean_cases"]["all_findings"] == 2
    assert a["manipulation"]["precision"] == 0.0


def test_observation_is_not_a_false_positive_on_a_tampered_case():
    s = rb.score_detection(run([finding(status=FindingStatus.OBSERVATION, bbox=None, detector="q")]),
                           truth([manip()]))
    assert s["unmatched_findings"] == []


def test_zero_denominators_are_na_not_perfect():
    a = rb.aggregate([rb.score_detection(run([]), truth())], [], [])
    assert a["manipulation"]["precision"] is None
    assert a["manipulation"]["recall_localized"] is None
    assert a["discrepancy"]["recall"] is None
    assert a["classification"]["accuracy"] is None
    assert a["fields"]["value_accuracy"] is None
    assert "n/a" == rb._pct(None)


DISC = {"id": "d1", "discrepancy_type": "dob_mismatch",
        "documents": ["salary_slip.png", "id_proof.png"]}


def cross(**kw) -> Finding:
    return finding(status=FindingStatus.INCONSISTENCY, category=FindingCategory.cross_document,
                   detector="cross.x", **kw)


def test_discrepancy_needs_type_and_both_documents():
    good = cross(discrepancy_type="dob_mismatch", related_doc_ids=["d3"])
    one_doc = cross(discrepancy_type="dob_mismatch")
    wrong_docs = cross(discrepancy_type="dob_mismatch", related_doc_ids=["d2"])
    wrong_type = cross(discrepancy_type="address_variant", related_doc_ids=["d3"])
    assert rb.score_detection(run([good]), truth(discs=[DISC]))["discrepancies"][0]["found"]
    for bad in (one_doc, wrong_docs, wrong_type):
        s = rb.score_detection(run([bad]), truth(discs=[DISC]))
        assert not s["discrepancies"][0]["found"], bad
        assert len(s["unmatched_findings"]) == 1


def test_discrepancy_recall_by_type():
    s = rb.score_detection(
        run([cross(discrepancy_type="dob_mismatch", related_doc_ids=["d3"])]),
        truth(discs=[DISC, {**DISC, "id": "d2", "discrepancy_type": "name_variant"}]),
    )
    d = rb.aggregate([s], [], [])["discrepancy"]
    assert d["recall"] == 0.5
    assert d["distinct_types_found"] == ["dob_mismatch"]
    assert d["by_type"]["name_variant"]["recall"] == 0.0


def test_inconsistency_explained_by_a_manipulation_is_not_a_false_positive():
    f = finding(status=FindingStatus.INCONSISTENCY, category=FindingCategory.contextual,
                detector="context.arithmetic_salary")
    s = rb.score_detection(run([f]), truth([manip()]))
    assert s["unmatched_findings"] == []
    assert s["inconsistency_matched"] == 1


def _doc(fields=(), doc_id="d1", doc_type=DocType.salary_slip) -> Document:
    return Document(id=doc_id, case_id="c", filename="doc_abc.png", sha256="0", doc_type=doc_type,
                    fields=list(fields))


def _field(name, raw, norm=None, bbox=FIELD_BOX, page=0) -> Field:
    return Field(doc_id="d1", name=name, value_raw=raw, value_norm=norm, confidence=0.9,
                 page=page, bbox=bbox, source=TextSource.ocr_rapid)


GT_DOCS = [{"filename": "salary_slip.png", "doc_type": "salary_slip", "format": "png",
            "fields": {"net_pay": {"value": "85400.00", "page": 0, "bbox": GT_BOX},
                       "person_name": {"value": "Asha Rao", "page": 0, "bbox": [0, 0, 50, 20]}}}]


def test_field_accuracy_counts_missing_fields_as_wrong():
    rows = rb.score_fields(run([], [_doc([_field("net_pay", "Rs. 85,400.00")])]),
                           truth(docs=GT_DOCS))
    summary = rb._field_summary(rows)
    assert summary["total"] == 2
    assert summary["value_correct"] == 1
    assert summary["value_accuracy"] == 0.5
    assert summary["by_doc_type"]["salary_slip"]["total"] == 2
    assert summary["by_format"]["png"]["accuracy"] == 0.5


def test_field_value_must_really_match():
    rows = rb.score_fields(run([], [_doc([_field("net_pay", "85,400.01")])]), truth(docs=GT_DOCS))
    assert next(r for r in rows if r["field"] == "net_pay")["value_correct"] is False


def test_field_of_a_document_that_never_ran_is_wrong():
    rows = rb.score_fields(run([], []), truth(docs=GT_DOCS))
    assert all(r["value_correct"] is False and r["present"] is False for r in rows)


def test_field_location_checked_against_truth_box():
    far = _field("net_pay", "85400.00", bbox=BBox(x0=900, y0=900, x1=1000, y1=950))
    rows = rb.score_fields(run([], [_doc([far])]), truth(docs=GT_DOCS))
    row = next(r for r in rows if r["field"] == "net_pay")
    assert row["value_correct"] is True
    assert row["location_correct"] is False


@pytest.mark.parametrize("raw,expected", [
    ("Rs. 85,400.00", "85400.00"), ("₹85400", "85400.00"), ("  Asha   RAO ", "asha rao"),
    ("85,400/-", "85400.00"),
])
def test_normalize_is_only_about_formatting(raw, expected):
    assert rb.normalize_value(raw) == expected


def test_classification_counts_unprocessed_documents_as_wrong():
    gt = [{"filename": "salary_slip.png", "doc_type": "salary_slip"},
          {"filename": "id_proof.png", "doc_type": "id_proof"}]
    rows = rb.score_classification(run([], [_doc()]), truth(docs=gt))
    assert {r["filename"]: r["correct"] for r in rows} == {"salary_slip.png": True,
                                                           "id_proof.png": False}


def test_anonymized_name_leaks_nothing():
    name = rb.anonymize("tampered_salary_slip_case_b.PNG")
    assert name.startswith("doc_") and name.endswith(".png")
    for word in ("tamper", "salary", "case"):
        assert word not in name


def test_ground_truth_cannot_be_passed_to_detection(tmp_path):
    gt = tmp_path / "ground_truth.json"
    gt.write_text("{}")
    with pytest.raises(ValueError):
        rb.stage_copy([gt], tmp_path / "out")


def test_noise_truth_is_limited_to_the_group(tmp_path):
    gt = tmp_path / "ground_truth.json"
    gt.write_text(json.dumps({
        "documents": [{"filename": "a__rot.png"}, {"filename": "a__blur.png"}],
        "manipulations": [{"filename": "a__rot.png"}, {"filename": "a__blur.png"}],
        "discrepancies": [{"documents": ["a__rot.png", "b__rot.png"]},
                          {"documents": ["a__blur.png", "b__blur.png"]}],
    }))
    case = rb.BenchCase("x", [tmp_path / "a__rot.png", tmp_path / "b__rot.png"], gt, "rot")
    t = rb.load_truth(case)
    assert [d["filename"] for d in t["documents"]] == ["a__rot.png"]
    assert len(t["manipulations"]) == 1 and len(t["discrepancies"]) == 1


def test_report_carries_disclosure_commit_and_inventory():
    s = rb.score_detection(run([finding()]), truth())
    result = {
        "generated_at": "2026-11-05T00:00:00+00:00",
        "git": {"commit": "abcdef1234567", "dirty": True},
        "summary_clean_scans": rb.aggregate([s], [], []),
        "cases": [s],
    }
    md = rb.render_markdown(result)
    assert "not generalization estimates" in md
    assert "synthetic" in md
    assert "abcdef1234" in md and "uncommitted" in md
    assert "Unmatched findings (1)" in md


def test_main_writes_nothing_without_a_dataset(tmp_path):
    out = tmp_path / "out"
    assert rb.main(["--dataset", str(tmp_path), "--out", str(out)]) == 2
    assert not out.exists()


def test_separators_are_forgiven_but_characters_are_not():
    same = "Flat 304, Lakeview Residency, 12th Main Road, Bengaluru 560038"
    assert rb.normalize_value("Flat 304, Lakeview Residency,, 12th Main Road,, Bengaluru - 560038") == rb.normalize_value(same)
    assert rb.normalize_value("+91 90000 01234") == rb.normalize_value("+919000001234")
    assert rb.normalize_value("Flat 305, Lakeview Residency, 12th Main Road, Bengaluru 560038") != rb.normalize_value(same)
