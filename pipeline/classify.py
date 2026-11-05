"""Document classification from printed keywords and layout signals.

Keywords are matched on space-free text, because OCR can drop spaces. The confidence reflects both
the evidence strength and the margin over the runner-up, so an ambiguous page scores low.
"""
from __future__ import annotations

import re

from models.schemas import BBox, DocType, Document
from pipeline.common import is_processable, log
from pipeline.layout import doc_lines, squish

# (phrase, weight). Title-like phrases are strong, supporting vocabulary is weaker.
KEYWORDS: dict[DocType, list[tuple[str, float]]] = {
    DocType.application_form: [
        ("application form", 5), ("loan application", 5), ("applicant", 2), ("application id", 3),
        ("application number", 3), ("application no", 3), ("loan amount", 3), ("application date", 2),
        ("personal details", 1.5), ("employment details", 1.5), ("signature of applicant", 2),
    ],
    DocType.id_proof: [
        ("government of india", 3), ("aadhaar", 5), ("unique identification", 4),
        ("permanent account number", 5), ("income tax department", 5), ("identity card", 5),
        ("national id", 5), ("id proof", 5), ("identity proof", 5), ("uidai", 4), ("vid", 0.5),
    ],
    DocType.salary_slip: [
        ("salary slip", 6), ("pay slip", 6), ("payslip", 6), ("salary statement", 5), ("net pay", 3),
        ("gross pay", 2.5), ("basic pay", 2.5), ("earnings", 2), ("deductions", 2), ("hra", 1.5),
        ("employee id", 2), ("provident fund", 1.5), ("pay period", 2.5), ("professional tax", 1.5),
    ],
    DocType.bank_statement: [
        ("account statement", 6), ("bank statement", 6), ("statement of account", 6),
        ("opening balance", 3), ("closing balance", 3), ("ifsc", 2.5), ("statement period", 3),
        ("withdrawal", 1), ("deposit", 1), ("debit", 1), ("credit", 1), ("balance", 0.5),
    ],
    DocType.address_proof: [
        ("electricity bill", 6), ("utility bill", 6), ("water bill", 6), ("gas bill", 6),
        ("telephone bill", 6), ("address proof", 6), ("proof of address", 6), ("consumer number", 4),
        ("consumer no", 4), ("amount due", 3), ("bill date", 3), ("units consumed", 3),
        ("due date", 1.5), ("meter", 1.5), ("tariff", 1.5), ("service address", 3), ("billing period", 2),
    ],
    DocType.declaration: [
        ("declaration", 5), ("self declaration", 6), ("i hereby declare", 6), ("hereby declare", 5),
        ("solemnly", 3), ("to the best of my knowledge", 4), ("true and correct", 3), ("declarant", 4),
        ("undertaking", 2.5), ("affidavit", 3),
    ],
}

MIN_SCORE = 3.0


def _layout_bonus(doc: Document, text: str) -> dict[DocType, float]:
    bonus: dict[DocType, float] = {}
    if all(k in text for k in ("date", "description", "balance")) and ("debit" in text or "withdrawal" in text):
        bonus[DocType.bank_statement] = 4.0
    if "earnings" in text and "deductions" in text:
        bonus[DocType.salary_slip] = 3.0
    # A tall narrative page with few numbers reads like a declaration, only if the word is present.
    page = doc.pages[0]
    if page.words:
        heights = [w.bbox.y1 - w.bbox.y0 for w in page.words]
        narrow = len(page.words) < 45
        if narrow and re.search(r"\d{4}\s?\d{4}\s?\d{4}", text) and max(heights) > 0:
            bonus[DocType.id_proof] = 2.0
    return bonus


def classify(doc: Document) -> Document:
    if not is_processable(doc):
        return doc
    try:
        words = [w for p in doc.pages for w in p.words]
        if not words:
            doc.doc_type = DocType.unknown
            doc.doc_type_confidence = 0.0
            doc.classification_method = "none: no text available"
            return doc

        # Title region counts double: the top quarter of the first page.
        first = doc.pages[0]
        title_limit = first.height * 0.25
        full = squish(" ".join(ln.text for p in doc.pages for ln in doc_lines(doc, p.index)))
        title = squish(" ".join(w.text for w in first.words if w.bbox.y1 <= title_limit))
        scores: dict[DocType, float] = {}
        matched: dict[str, list[str]] = {}
        for dtype, kws in KEYWORDS.items():
            s = 0.0
            for phrase, weight in kws:
                key = squish(phrase)
                if key in full:
                    s += weight
                    matched.setdefault(dtype.value, []).append(phrase)
                    if key in title and weight >= 3:
                        s += weight
            scores[dtype] = s
        spaced = " ".join(w.text for p in doc.pages for w in p.words).casefold()
        for dtype, extra in _layout_bonus(doc, spaced).items():
            scores[dtype] = scores.get(dtype, 0.0) + extra

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        best, best_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else 0.0
        doc.metadata["classification_scores"] = {k.value: round(v, 2) for k, v in ranked if v > 0}
        doc.metadata["classification_keywords"] = matched.get(best.value, [])
        if best_score < MIN_SCORE:
            doc.doc_type = DocType.unknown
            doc.doc_type_confidence = round(min(best_score / MIN_SCORE, 1.0) * 0.3, 3)
            doc.classification_method = "keywords+layout: insufficient evidence"
            return doc
        margin = (best_score - second) / best_score
        strength = min(best_score / 12.0, 1.0)
        mean_conf = sum(w.confidence for w in words) / len(words)
        doc.doc_type = best
        doc.doc_type_confidence = round(max(0.05, (0.45 + 0.35 * margin + 0.2 * strength) * mean_conf), 3)
        doc.classification_method = "keywords+layout"
    except Exception as exc:
        log.warning("classification failed: %s", type(exc).__name__)
        doc.doc_type = DocType.unknown
        doc.classification_method = "failed"
    return doc


__all__ = ["BBox", "classify"]
