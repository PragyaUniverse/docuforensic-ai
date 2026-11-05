"""Totals across all cases. Counts only: no scores or rates are presented as accuracy."""
from __future__ import annotations

from collections import Counter

from backend import db


def report() -> dict:
    cases = db.list_cases()
    by_status: Counter = Counter()
    by_check: Counter = Counter()
    by_discrepancy: Counter = Counter()
    by_review: Counter = Counter()
    dismissed_by_check: Counter = Counter()
    by_risk: Counter = Counter()
    rows = []
    documents = 0
    for case in cases:
        findings = db.list_findings(case.id)
        docs = db.list_documents(case.id)
        documents += len(docs)
        if case.status.value == "complete":
            by_risk[case.risk_level.value] += 1
        for f in findings:
            by_status[f.status.value] += 1
            by_check[f.detector] += 1
            by_review[f.review.decision.value] += 1
            if f.discrepancy_type:
                by_discrepancy[f.discrepancy_type] += 1
            if f.review.decision.value == "dismissed":
                dismissed_by_check[f.detector] += 1
        rows.append({
            "id": case.id, "name": case.name, "status": case.status.value, "risk_level": case.risk_level.value,
            "created_at": case.created_at.isoformat(), "documents": len(docs),
            "to_review": sum(f.status.value != "OBSERVATION" and f.review.decision.value == "pending" for f in findings),
        })
    return {
        "cases": len(cases), "documents": documents, "by_risk": dict(by_risk), "by_status": dict(by_status),
        "by_review": dict(by_review), "by_discrepancy": by_discrepancy.most_common(),
        "by_check": [
            {"check": check, "count": n, "dismissed": dismissed_by_check[check]} for check, n in by_check.most_common()
        ],
        "recent": rows[:25],
    }
