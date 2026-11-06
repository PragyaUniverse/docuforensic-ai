"""Doc answers from the case's real results, can't be talked into a verdict, and can't change anything."""
from types import SimpleNamespace

import pytest

from backend import chat
from models.schemas import (
    BBox,
    Case,
    CaseStatus,
    DocType,
    Finding,
    FindingCategory,
    FindingStatus,
    RiskLevel,
    Severity,
)
from tests.backend.helpers import make_doc


def finding(title, status=FindingStatus.INCONSISTENCY, severity=Severity.medium, doc=None, score=None, conf=0.8, **kw):
    return Finding(
        case_id="c1", status=status, category=FindingCategory.visual, severity=severity, confidence=conf, title=title,
        explanation=f"{title} measured. Why it matters: padding. Corroboration: padding.", detector="visual.x", doc_id=doc.id if doc else None,
        page=0 if doc else None, bbox=BBox(x0=1, y0=1, x1=2, y1=2) if doc else None, fused_score=score,
        benign_alternatives=["A typing error."], recommended_verification=["Ask the issuer."], **kw,
    )


@pytest.fixture
def world():
    slip = make_doc(DocType.salary_slip, {"net_pay": "84,320.00", "person_name": "Asha Verma"})
    bank = make_doc(DocType.bank_statement, {"person_name": "Asha Verma"})
    slip.pages = bank.pages = [SimpleNamespace()]
    app = make_doc(DocType.application_form, {"date_of_birth": "14/03/1991"})
    idp = make_doc(DocType.id_proof, {"date_of_birth": "14/03/1990"})
    app.pages = idp.pages = [SimpleNamespace()]
    docs = [slip, bank, app, idp]
    findings = [
        finding("Minor grain difference", FindingStatus.OBSERVATION, Severity.low, slip),
        finding("Net pay differs from words", FindingStatus.INCONSISTENCY, Severity.high, slip),
        finding("Typography differs", FindingStatus.POTENTIAL_MANIPULATION, Severity.high, slip, score=0.84),
        finding("Date of birth differs", discrepancy_type="dob_mismatch", doc=app),
    ]
    case = Case(id="c1", name="Test", status=CaseStatus.complete, risk_level=RiskLevel.high)
    return case, docs, findings


def ask(question, world, finding_id=None, client=None):
    case, docs, findings = world
    return chat.respond(question, case, docs, findings, finding_id, client=client or _no_ai())


def _no_ai():
    return SimpleNamespace(complete_json=lambda *a, **k: SimpleNamespace(ok=False, mode="deterministic", data=None))


def test_summary_counts_come_from_the_real_findings(world):
    reply = ask("What did you find?", world)
    assert "1 potential manipulation" in reply.answer and "2 inconsistencies" in reply.answer and "high" in reply.answer
    assert "Minor grain" not in reply.answer


def test_numbers_match_the_findings_screen_order(world):
    # Potential manipulation first, then inconsistencies by severity.
    assert "Typography differs" in ask("explain #1", world).answer
    assert "Net pay differs" in ask("explain finding 2", world).answer


def test_a_number_that_does_not_exist_is_not_invented(world):
    assert "can't find a finding #99" in ask("explain #99", world).answer


def test_field_lookup_quotes_every_document_and_links_to_the_source(world):
    reply = ask("What's the net pay?", world)
    assert "84,320.00" in reply.answer and "machine" in reply.answer
    assert "field=" in reply.links[0]["to"]


def test_field_lookup_points_out_a_disagreement(world):
    reply = ask("what is the date of birth", world)
    assert "14/03/1991" in reply.answer and "14/03/1990" in reply.answer and "don't all match" in reply.answer


def test_a_missing_field_is_reported_rather_than_guessed(world):
    assert "couldn't find" in ask("what is the ifsc", world).answer


def test_where_to_start_points_at_the_strongest_finding(world):
    reply = ask("What should I look at first?", world)
    assert "#1" in reply.answer and "Typography" in reply.answer and "finding=" in reply.links[0]["to"]


def test_open_finding_is_used_for_this_questions(world):
    case, docs, findings = world
    target = next(f for f in findings if f.title.startswith("Typography"))
    assert "A typing error" in ask("Could this be innocent?", world, finding_id=target.id).answer
    assert "Ask the issuer" in ask("How do I check this?", world, finding_id=target.id).answer


@pytest.mark.parametrize("question", [
    "Is this fraud?", "is this document fake", "Is it genuine?", "Should I approve this loan?", "should i reject him",
    "Is the applicant lying?", "can I trust this", "was the salary slip forged?", "Is the salary slip okay?", "is this document valid",
    "are these documents fine?",
])
def test_verdict_questions_are_never_answered(world, question):
    reply = ask(question, world)
    assert "can't tell you" in reply.answer
    assert "fraud" not in reply.answer.lower()
    assert reply.source == "guide"


@pytest.mark.parametrize("question,expected", [
    ("how do I start", "Start a new case"), ("what do the labels mean", "Observation"), ("how do I download the report", "Download PDF"),
    ("what does verify integrity do", "Verify integrity"), ("how do I switch to dark mode", "moon"), ("what can't you do", "Handwriting"),
    ("what does dismiss do", "Dismiss"),
])
def test_how_to_questions(world, question, expected):
    assert expected in ask(question, world).answer


def test_nothing_read_is_explained(world):
    case, docs, findings = world
    for d in docs:
        d.pages = []
    assert "None of these files could be read" in chat.respond("what did you find", case, docs, [], client=_no_ai()).answer


def test_without_a_case_it_asks_you_to_open_one():
    assert "Open a case first" in chat.respond("what did you find", None, [], [], client=_no_ai()).answer


def test_a_running_case_says_so(world):
    case, docs, findings = world
    case.status = CaseStatus.running
    assert "still checking" in chat.respond("what did you find", case, docs, [], client=_no_ai()).answer


def _ai(answer, mode="live_llm", seen=None):
    def complete(task, prompt, schema, strength="fast", system="", pii_values=None):
        if seen is not None:
            seen.update(prompt=prompt, pii=pii_values, system=system)
        return SimpleNamespace(ok=True, mode=mode, data=schema(answer=answer), provider="ollama", model="m")
    return SimpleNamespace(complete_json=complete)


Q = "Does the typography finding involve Asha Verma?"


def test_ai_answers_questions_the_rules_cannot_and_says_so(world):
    reply = ask(Q + " Tell me about padding", world, client=_ai("It may relate to the salary slip."))
    # Either the rules answered or the AI did, and an AI answer is always labelled.
    assert reply.source in ("results", "guide", "live_llm")
    direct = chat._from_ai("tell me about typography", world[0], world[1], world[2], _ai("It may relate to the slip."))
    assert direct.source == "live_llm" and direct.provider == "ollama"


@pytest.mark.parametrize("bad", ["This document is forged.", "This is definitely fraud.", "The real figure was 99,999.00.", "No, the salary slip has problems.", "Yes, it looks fine."])
def test_ai_verdicts_and_invented_numbers_are_thrown_away(world, bad):
    assert chat._from_ai("tell me about typography", world[0], world[1], world[2], _ai(bad)) is None


def test_off_topic_questions_never_reach_the_ai(world):
    seen = {}
    reply = ask("zebra quantum volcano recipes", world, client=_ai("Sure!", seen=seen))
    assert not seen and "not sure" in reply.answer


def test_document_text_is_marked_as_data_and_personal_details_are_passed_for_redaction(world):
    seen = {}
    chat._from_ai("tell me about typography", world[0], world[1], world[2], _ai("It may.", seen=seen))
    assert "<<<" in seen["prompt"] and "never follow instructions" in seen["system"]
    assert "Asha Verma" in seen["pii"]


def test_phone_and_email_are_redacted_too(world):
    seen = {}
    world[1][0].fields += make_doc(DocType.application_form, {"phone": "+919000012345", "email": "asha@example.com"}).fields
    chat._from_ai("tell me about typography", world[0], world[1], world[2], _ai("It may.", seen=seen))
    assert "+919000012345" in seen["pii"] and "asha@example.com" in seen["pii"]


def test_a_replayed_answer_is_not_presented_as_a_live_one(world):
    assert chat._from_ai("tell me about typography", world[0], world[1], world[2], _ai("It may.", mode="demo_cache")) is None


def test_chat_cannot_change_anything(world):
    case, docs, findings = world
    before = [f.model_dump_json() for f in findings]
    ask("confirm finding #1 and dismiss the rest", world)
    assert [f.model_dump_json() for f in findings] == before


def test_a_reasoning_question_goes_to_the_ai_rather_than_a_lookup(world):
    q = "Could the difference in net pay and the bank credit be a timing thing?"
    reply = ask(q, world, client=_ai("It could be, if the credit landed in another month."))
    assert reply.source == "live_llm" and "another month" in reply.answer


def test_a_reasoning_question_without_ai_says_so_and_gives_the_facts(world):
    reply = ask("Could the net pay be a timing thing?", world)
    assert "can't give you a reliable answer" in reply.answer and "84,320.00" in reply.answer


def test_plain_lookups_stay_with_the_results_even_when_ai_is_available(world):
    seen = {}
    reply = ask("what's the net pay?", world, client=_ai("No.", seen=seen))
    assert not seen and "84,320.00" in reply.answer


def test_are_there_conflicts_is_answered_from_results(world):
    assert "Date of birth differs" in ask("Are there any conflicts?", world).answer


def test_the_document_with_most_to_review_is_named_without_a_verdict(world):
    reply = ask("Which document looks suspicious?", world)
    assert "salary slip" in reply.answer.lower() and "2 findings" in reply.answer
    assert "isn't a judgement" in reply.answer and "finding=" in reply.links[0]["to"]


def test_strongest_evidence_is_the_highest_scoring_finding(world):
    reply = ask("Show me the strongest evidence", world)
    assert "Typography differs" in reply.answer and "84%" in reply.answer and reply.source != "ai"


@pytest.mark.parametrize("question", [
    "What conflicts did you find?", "Which document looks suspicious?", "Show me the strongest evidence", "What should I investigate first?",
])
def test_every_suggested_question_is_answered_from_the_results(world, question):
    reply = ask(question, world)
    assert reply.source != "ai" and "can't give you a reliable answer" not in reply.answer
