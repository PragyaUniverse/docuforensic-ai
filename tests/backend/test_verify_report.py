"""Verify this report: an issued dossier is recognised byte for byte, and any change is caught."""
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from audit import chain
from backend import db, verify_report
from backend.app import app
from config.settings import settings
from models.schemas import Case


@pytest.fixture(autouse=True)
def tmp_db(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def _pdf(path, case_id: str, text: str, subject: bool = True):
    c = canvas.Canvas(str(path))
    if subject:
        c.setSubject(f"DocuForensic case {case_id}")
    c.drawString(72, 720, text)
    c.save()
    return path


def test_an_issued_report_is_original_and_an_edited_one_is_not(tmp_path):
    case = db.save_case(Case(name="Case B"))
    issued = _pdf(tmp_path / "a.pdf", case.id, "Net pay 48,320")
    verify_report.record_issued(case.id, issued)

    ok = verify_report.verify(issued.read_bytes())
    assert ok["result"] == "original"
    assert ok["case_id"] == case.id and ok["case_name"] == "Case B"
    assert ok["chain"]["ok"] is True

    edited = _pdf(tmp_path / "b.pdf", case.id, "Net pay 84,320")
    changed = verify_report.verify(edited.read_bytes())
    assert changed["result"] == "modified"
    assert changed["case_id"] == case.id

    one_byte = bytearray(issued.read_bytes())
    one_byte[-20] ^= 1
    assert verify_report.verify(bytes(one_byte))["result"] in ("modified", "unknown")


def test_a_case_named_only_in_the_text_is_still_found(tmp_path):
    case = db.save_case(Case(name="Case C"))
    pdf = _pdf(tmp_path / "c.pdf", case.id, f"DocuForensic AI | {case.id} | For human review only", subject=False)
    assert verify_report.verify(pdf.read_bytes())["result"] == "modified"


def test_unrelated_files_are_unknown_or_not_pdf(tmp_path):
    other = _pdf(tmp_path / "d.pdf", "case_000000000000", "hello", subject=False)
    assert verify_report.verify(other.read_bytes())["result"] == "unknown"
    assert verify_report.verify(b"not a pdf at all")["result"] == "not_pdf"


def test_a_broken_history_is_reported_alongside_a_match(tmp_path):
    case = db.save_case(Case(name="Case D"))
    issued = _pdf(tmp_path / "e.pdf", case.id, "x")
    verify_report.record_issued(case.id, issued)
    chain.append("note", "system", case.id, {"a": 1})
    assert chain.tamper_demo(case.id) is not None
    result = verify_report.verify(issued.read_bytes())
    assert result["result"] == "original"
    assert result["chain"]["ok"] is False


def test_endpoint_checks_an_upload_and_records_it(tmp_path):
    case = db.save_case(Case(name="Case A"))
    issued = _pdf(tmp_path / "f.pdf", case.id, "x")
    verify_report.record_issued(case.id, issued)
    client = TestClient(app)
    res = client.post("/api/verify-report", files={"file": ("report.pdf", issued.read_bytes(), "application/pdf")})
    assert res.status_code == 200, res.text
    assert res.json()["result"] == "original"
    assert any(e.action == "report.verified" for e in chain.entries(case.id))
    assert client.post("/api/verify-report").status_code == 400
