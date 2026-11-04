from dataclasses import dataclass, field

import pytest

from llm.client import LLMResult
from llm.investigator import (
    PLAYBOOK, InvestigationAnswer, correlate_findings, investigate, summarize_case, validate_answer,
)
from models.schemas import (
    BBox, Finding, FindingCategory, FindingStatus, Severity,
)


def finding(detector="cross.salary_vs_bank_credit", status=FindingStatus.INCONSISTENCY, severity=Severity.high, **kw):
    base = dict(case_id="c", status=status, category=FindingCategory.cross_document, severity=severity,
                confidence=0.9, title="Net pay differs", explanation="Net pay 86,400.00 vs credit 62,400.00.",
                detector=detector, discrepancy_type="salary_vs_bank_credit", doc_id="d1", page=0,
                bbox=BBox(x0=10, y0=10, x1=100, y1=30))
    base.update(kw)
    return Finding(**base)


@dataclass
class FakeClient:
    answer: object = None
    calls: list = field(default_factory=list)

    def complete_json(self, task, prompt, schema, strength="fast", system="", pii_values=None):
        self.calls.append((task, prompt, strength))
        if self.answer is None:
            return LLMResult(False, "deterministic", error="none")
        return LLMResult(True, "live_llm", self.answer, "ollama", "m:1", prompt_hash="h")

    def any_live_provider(self):
        return self.answer is not None


GOOD = InvestigationAnswer(
    reasoning="The gap of 86,400.00 vs 62,400.00 may reflect a changed figure, or a bonus.",
    benign_alternatives=["A bonus was paid separately."],
    what_would_confirm=["Payroll register shows 62,400.00."], what_would_refute=["Employer confirms the higher figure."])


@pytest.mark.parametrize("detector", [
    "visual.ela", "visual.noise", "visual.copy_move", "visual.font_consistency", "visual.overwrite", "visual.photo_insert",
    "visual.alignment", "visual.signature_reuse", "visual.signature_placement", "pdf.text_vs_pixels",
    "pdf.incremental_update", "pdf.producer_mismatch", "pdf.overlay_object", "metadata.exif", "metadata.pdf_dates",
    "context.arithmetic_salary", "context.arithmetic_balance", "context.date_order", "context.id_checksum",
    "context.missing_field", "context.duplicate_field", "dob_mismatch", "name_variant", "address_variant",
    "employer_mismatch", "salary_vs_bank_credit", "declared_vs_actual_income", "id_number_mismatch",
    "account_number_mismatch", "employment_date_conflict",
])
def test_every_detector_has_a_deterministic_playbook(detector):
    why, benign, verify = PLAYBOOK[detector]
    assert why and benign and verify


def test_without_an_llm_every_finding_still_gets_full_reasoning():
    f = finding()
    stats = {}
    investigate([f], [], client=FakeClient(), stats=stats)
    assert f.reasoning.mode == "deterministic"
    assert f.benign_alternatives and f.recommended_verification and "Why it matters" in f.explanation
    assert stats["deterministic"] == 1


def test_llm_adds_reasoning_but_changes_nothing_else():
    f = finding()
    before = (f.status, f.severity, f.confidence, f.bbox, f.detector, f.doc_id, f.page, f.id)
    investigate([f], [], client=FakeClient(GOOD))
    assert (f.status, f.severity, f.confidence, f.bbox, f.detector, f.doc_id, f.page, f.id) == before
    assert f.reasoning.mode == "live_llm" and f.reasoning.provider == "ollama"
    assert "AI reasoning (ollama/m:1)" in f.explanation
    assert "A bonus was paid separately." in f.benign_alternatives
    assert any(v.startswith("To refute:") for v in f.recommended_verification)


def test_llm_cannot_add_findings():
    items = [finding()]
    assert len(investigate(items, [], client=FakeClient(GOOD))) == 1


@pytest.mark.parametrize("word", ["This is clearly fraud.", "The document was forged.", "This proves tampering.",
                                  "It is manipulated.", "The applicant is guilty.", "fraudulent payslip"])
def test_verdict_language_is_rejected(word):
    answer = InvestigationAnswer(reasoning=word, benign_alternatives=[], what_would_confirm=[], what_would_refute=[])
    f = finding()
    stats = {}
    investigate([f], [], client=FakeClient(answer), stats=stats)
    assert stats["llm_rejected"] == 1 and f.reasoning.mode == "deterministic" and word not in f.explanation


def test_invented_numbers_are_rejected():
    answer = InvestigationAnswer(reasoning="The real salary is 99,999.00.", benign_alternatives=[],
                                 what_would_confirm=[], what_would_refute=[])
    assert validate_answer(answer, "Net pay 86,400.00") == "cites numbers absent from the evidence"
    assert validate_answer(GOOD, "Net pay 86,400.00 vs credit 62,400.00.") is None


def test_prompts_have_no_generated_ids_so_the_cache_can_replay():
    a, b = finding(), finding()
    assert a.id != b.id
    ca, cb = FakeClient(), FakeClient()
    investigate([a], [], client=ca)
    investigate([b], [], client=cb)
    assert ca.calls[0][1] == cb.calls[0][1] and a.id not in ca.calls[0][1]


def test_high_severity_uses_the_strong_model_and_low_the_fast_one():
    client = FakeClient()
    investigate([finding(), finding(severity=Severity.medium, title="other")], [], client=client)
    assert {c[2] for c in client.calls} <= {"strong", "fast"}
    assert client.calls[0][2] == "strong"


def test_shared_region_links_findings_across_categories():
    visual = finding(detector="visual.overwrite", status=FindingStatus.POTENTIAL_MANIPULATION,
                     category=FindingCategory.visual, discrepancy_type=None, title="Patch behind value")
    context = finding(detector="context.arithmetic_salary", category=FindingCategory.contextual,
                      discrepancy_type=None, title="Sum broken", bbox=BBox(x0=15, y0=12, x1=90, y1=28))
    apart = finding(detector="visual.noise", category=FindingCategory.visual, discrepancy_type=None,
                    title="Far away", bbox=BBox(x0=500, y0=500, x1=600, y1=600))
    correlate_findings([visual, context, apart], [])
    assert context.id in visual.related_finding_ids and visual.id in context.related_finding_ids
    assert apart.related_finding_ids == []
    assert "Corroboration" in visual.explanation


def test_summary_falls_back_when_the_llm_output_has_a_verdict():
    from llm.investigator import CaseSummaryAnswer

    text, prov = summarize_case([finding()], [], "high", client=FakeClient(CaseSummaryAnswer(summary="This is fraud.")))
    assert prov.mode == "deterministic" and "fraud" not in text.lower() and "human review" in text
