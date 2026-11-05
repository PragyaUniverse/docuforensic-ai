"""Walks every finding on the real demo cases back to its source. This is problem statement 5.7."""
import json
from pathlib import Path

import pytest

from models.schemas import FindingStatus
from scripts.run_benchmark import run_pipeline

DATA = Path(__file__).resolve().parents[2] / "data" / "synthetic_cases"
CASES = ["case_a_clean", "case_b_visual", "case_c_crossdoc", "case_d_pdf"]


@pytest.fixture(scope="module", params=CASES)
def run(request, tmp_path_factory):
    folder = DATA / request.param
    if not folder.exists():
        pytest.skip("demo dataset not generated")
    names = [d["filename"] for d in json.loads((folder / "ground_truth.json").read_text())["documents"]]
    return run_pipeline(request.param, [folder / n for n in names], tmp_path_factory.mktemp("trace"))


def _inside(bbox, page) -> bool:
    return -2 <= bbox.x0 < bbox.x1 <= page.width + 2 and -2 <= bbox.y0 < bbox.y1 <= page.height + 2


def test_every_finding_resolves_to_a_document_page_and_region(run):
    docs = {d.id: d for d in run.documents}
    for f in run.findings:
        if f.bbox is None:  # document-level facts, such as PDF metadata, name a document but no region
            assert f.doc_id in docs and f.status == FindingStatus.OBSERVATION, f.title
            continue
        assert f.doc_id in docs, f.title
        assert 0 <= f.page < len(docs[f.doc_id].pages), f.title
        assert _inside(f.bbox, docs[f.doc_id].pages[f.page]), f"{f.title}: {f.bbox}"


def test_every_referenced_field_exists_and_locates_its_value(run):
    fields = {x.id: (d, x) for d in run.documents for x in d.fields}
    for f in run.findings:
        for field_id in f.related_field_ids:
            assert field_id in fields, f"{f.title}: {field_id}"
            doc, field = fields[field_id]
            assert _inside(field.bbox, doc.pages[field.page])


def test_cross_document_findings_show_both_sides(run):
    for f in run.findings:
        if f.discrepancy_type:
            located = {e.doc_id for e in f.evidence if e.bbox is not None and e.doc_id}
            assert len(located) >= 2, f"{f.discrepancy_type} is located on {len(located)} document(s)"


def test_flags_are_evidenced_and_never_claim_a_verdict(run):
    for f in run.findings:
        assert "fraud" not in f"{f.title} {f.explanation}".lower()
        if f.status != FindingStatus.OBSERVATION:
            assert f.evidence, f.title
