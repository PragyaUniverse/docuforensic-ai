"""Doc in Hindi: every fixed sentence has a Hindi form, values pass through unchanged, Hindi questions are understood."""
import re

import pytest

from backend import chat, hindi
from models.schemas import FindingStatus
from tests.backend.test_chat import _no_ai, world  # noqa: F401  (fixture)

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
QUESTIONS = [
    "What did you find?", "What should I look at first?", "Show me the strongest evidence", "Which document looks suspicious?",
    "Do the documents conflict?", "Why is the risk high?", "What's the net pay?", "What's the date of birth?", "explain #1",
    "explain #2", "Could #2 be innocent?", "How do I check #2?", "explain #99", "Is this fake?", "What do the labels mean?",
    "How do I download the report?", "What can you do?", "How do I start?", "Draft a verification letter", "What's on the bank statement?",
]


def _hi(question, world):  # noqa: F811
    case, docs, findings = world
    return chat.respond(question, case, docs, findings, client=_no_ai(), lang="hi")


def _en(question, world):  # noqa: F811
    case, docs, findings = world
    return chat.respond(question, case, docs, findings, client=_no_ai())


@pytest.mark.parametrize("question", QUESTIONS)
def test_every_answer_is_in_hindi_and_keeps_every_number(question, world):  # noqa: F811
    en, hi = _en(question, world), _hi(question, world)
    assert DEVANAGARI.search(hi.answer), hi.answer
    assert sorted(re.findall(r"\d+(?:[.,]\d+)*", en.answer)) == sorted(
        re.findall(r"\d+(?:[.,]\d+)*", hi.answer.replace(hindi.ENGLISH_NOTE, ""))), (en.answer, hi.answer)
    assert len(hi.links) == len(en.links) and [x["to"] for x in hi.links] == [x["to"] for x in en.links]


@pytest.mark.parametrize("question", QUESTIONS)
def test_lines_with_a_fixed_pattern_are_fully_translated(question, world):  # noqa: F811
    en = _en(question, world)
    for line in en.answer.split("\n"):
        translated = hindi.translate_line(line)
        if translated is not None and line.strip():
            assert DEVANAGARI.search(translated), line


def test_free_text_from_the_checks_stays_english_with_a_note(world):  # noqa: F811
    hi = _hi("explain #1", world)
    assert "measured" in hi.answer  # the explanation lead, as written by the check
    assert hindi.ENGLISH_NOTE in hi.answer


def test_verdict_questions_in_hindi_get_the_honest_answer(world):  # noqa: F811
    for q in ("क्या यह नकली है?", "क्या मुझे इसे स्वीकार करना चाहिए?", "क्या यह असली है?"):
        hi = _hi(q, world)
        assert "नहीं बता सकता" in hi.answer, (q, hi.answer)


@pytest.mark.parametrize("hindi_q,english", [
    ("आपको क्या मिला?", "What did you find?"), ("मुझे पहले क्या देखना चाहिए?", "What should I look at first?"),
    ("#2 समझाइए", "explain #2"), ("शुद्ध वेतन क्या है?", "what's the net pay"), ("रिपोर्ट कैसे डाउनलोड करूँ?", "How do I download the report?"),
    ("सत्यापन पत्र का मसौदा बनाइए", "Draft a verification letter"), ("क्या ये विवरण पहले देखे गए हैं?", "Has this been seen before?"),
])
def test_hindi_questions_map_to_the_english_question(hindi_q, english):
    assert hindi.to_english(hindi_q).casefold() == english.casefold()


def test_suggestions_round_trip(world):  # noqa: F811
    hi = _hi("What did you find?", world)
    assert hi.suggestions and all(DEVANAGARI.search(s) for s in hi.suggestions)
    assert all(hindi.to_english(s) in hindi.SUGGESTIONS for s in hi.suggestions)


def test_titles_and_statuses_are_named_in_hindi():
    assert hindi._title("Date of birth differs across documents") == "दस्तावेज़ों में जन्म तिथि अलग है"
    assert hindi._title("Typography differs from other text on the page (3 signals agree)").endswith("(3 संकेत सहमत)")
    assert hindi._title("2 details from this application appear in another one").startswith("इस आवेदन के 2")
    assert set(hindi.STATUS) == {"Potential manipulation", "Inconsistency", "Observation"}
    assert {s.value for s in FindingStatus}  # statuses stay the same values; only their names are translated
