"""The system reports hypotheses, not verdicts. The word must not reach any output or UI source."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from models.schemas import FindingStatus, ReviewDecision

BANNED = re.compile(r"fraud", re.IGNORECASE)
# The ethics statement may say what the system refuses to do. Nothing else may use the word.
ALLOWED_LINE = re.compile(r"ethic|never|not (a |an )?(confirm|label|classif|verdict)|no verdict",
                          re.IGNORECASE)
UI_SUFFIXES = {".ts", ".tsx", ".js", ".jsx", ".html", ".css", ".json", ".md"}
UI_SKIP_DIRS = {"node_modules", "dist", ".vite", "coverage"}
UI_SKIP_FILES = {"package-lock.json"}


def violations(root: Path) -> list[str]:
    out = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in UI_SUFFIXES or path.name in UI_SKIP_FILES:
            continue
        rel = path.relative_to(root)
        if UI_SKIP_DIRS & set(rel.parts) or "test" in path.name.lower():
            continue
        for number, line in enumerate(path.read_text(errors="ignore").splitlines(), 1):
            if BANNED.search(line) and not ALLOWED_LINE.search(line):
                out.append(f"{rel}:{number}: {line.strip()[:100]}")
    return out


def test_schema_has_no_verdict_values():
    assert not BANNED.search(" ".join(s.value for s in FindingStatus))
    assert not BANNED.search(" ".join(s.value for s in ReviewDecision))


def test_scan_itself_finds_a_planted_word(tmp_path):
    (tmp_path / "App.tsx").write_text('const label = "Fraud detected";\n')
    (tmp_path / "Ethics.tsx").write_text("<p>We never label anything as fraud.</p>\n")
    (tmp_path / "App.test.tsx").write_text('expect("fraud")\n')
    found = violations(tmp_path)
    assert len(found) == 1 and found[0].startswith("App.tsx:1")


def test_frontend_source_has_no_verdict_language(repo_root):
    root = repo_root / "frontend"
    if not (root / "src").exists():
        pytest.skip("frontend source not landed yet")
    assert violations(root) == []


@pytest.mark.parametrize("demo", ["case_b", "case_c", "case_d"])
def test_findings_and_dossier_have_no_verdict_language(api, demo):
    case_id = api.load_demo(demo)
    if case_id is None:
        pytest.skip(f"demo {demo} not available yet")
    body = api.run(case_id)
    assert body["case"]["requires_human_review"] is True

    findings = api.findings(case_id)
    assert not BANNED.search(json.dumps(findings)), "finding text uses verdict language"
    for finding in findings:
        assert finding["status"] in {s.value for s in FindingStatus}
        if finding["status"] == "POTENTIAL_MANIPULATION":
            assert finding["benign_alternatives"], f"{finding['detector']} lists no alternatives"
            assert finding["recommended_verification"], finding["detector"]

    dossier = api.client.get(f"/api/cases/{case_id}/dossier")
    assert dossier.status_code == 200, dossier.text
    hits = [
        line for line in re.split(r"(?<=[.!?])\s+", dossier.text)
        if BANNED.search(line) and not ALLOWED_LINE.search(line)
    ]
    assert hits == [], "dossier uses verdict language outside the disclaimer"

    pdf = api.client.get(f"/api/cases/{case_id}/dossier.pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    import pymupdf

    with pymupdf.open(stream=pdf.content, filetype="pdf") as handle:
        pdf_text = "\n".join(page.get_text() for page in handle)
    pdf_hits = [
        line for line in pdf_text.splitlines()
        if BANNED.search(line) and not ALLOWED_LINE.search(line)
    ]
    assert pdf_hits == [], pdf_hits[:3]


def test_dossier_has_all_required_sections(api):
    case_id = api.load_demo("case_c")
    if case_id is None:
        pytest.skip("demo case C not available yet")
    api.run(case_id)
    dossier = api.client.get(f"/api/cases/{case_id}/dossier").json()
    for key in (
        "overview", "extracted", "structure", "contextual_findings", "cross_document_findings",
        "missing_or_duplicated", "visual_findings", "traceability", "summary",
        "potential_explanations", "areas_for_verification", "limitations", "reasoning_modes",
        "disclaimer",
    ):
        assert key in dossier, key
    assert dossier["requires_human_review"] is True
    assert dossier["limitations"]
    pdf = api.client.get(f"/api/cases/{case_id}/dossier.pdf")
    import pymupdf

    with pymupdf.open(stream=pdf.content, filetype="pdf") as handle:
        text = "\n".join(page.get_text() for page in handle).lower()
    for heading in ("overview", "extracted", "contextual", "visual", "traceability", "summary"):
        assert heading in text, f"dossier PDF has no {heading} section"
