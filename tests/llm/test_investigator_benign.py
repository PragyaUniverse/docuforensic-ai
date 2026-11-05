"""An AI answer can add innocent explanations, but can't pass off tampering as one."""
from types import SimpleNamespace

from llm.investigator import InvestigationAnswer, _apply_answer
from models.schemas import Finding, FindingCategory, FindingStatus, Severity


def _finding():
    return Finding(
        case_id="c", status=FindingStatus.POTENTIAL_MANIPULATION, category=FindingCategory.visual,
        severity=Severity.high, confidence=0.8, title="t", explanation="e", detector="visual.overwrite",
        benign_alternatives=["Scanner artefact."],
    )


def _result(benign):
    answer = InvestigationAnswer(reasoning="r", benign_alternatives=benign, what_would_confirm=[], what_would_refute=[])
    return SimpleNamespace(data=answer, mode="live_llm", provider="ollama", model="m", prompt_hash="h")


def test_tampering_is_not_accepted_as_a_benign_alternative():
    f = _finding()
    _apply_answer(f, _result(["A patch applied over an original value", "A deliberate change to the amount", "A data entry typo"]))
    assert f.benign_alternatives == ["Scanner artefact.", "A data entry typo"]


def test_status_and_confidence_are_untouched_by_the_answer():
    f = _finding()
    _apply_answer(f, _result(["A data entry typo"]))
    assert f.status == FindingStatus.POTENTIAL_MANIPULATION and f.confidence == 0.8
    assert f.reasoning.mode == "live_llm"
