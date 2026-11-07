"""Totals across all cases. Counts only: no scores or rates are presented as accuracy.

The false-alarm tracker counts, per check, how often reviewers confirmed or dismissed what it flagged.
It's the reviewers' own record on this system, which says where a check needs care. With few
decisions it says little, so the rate is only given from MIN_DECISIONS decisions up.
"""
from __future__ import annotations

from collections import Counter

from backend import db

MIN_DECISIONS = 3


def report() -> dict:
    cases = db.list_cases()
    by_status: Counter = Counter()
    by_check: Counter = Counter()
    by_discrepancy: Counter = Counter()
    by_review: Counter = Counter()
    dismissed_by_check: Counter = Counter()
    decisions_by_check: dict[str, Counter] = {}
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
            if f.status.value != "OBSERVATION":
                decisions_by_check.setdefault(f.detector, Counter())[f.review.decision.value] += 1
        rows.append({
            "id": case.id, "name": case.name, "status": case.status.value, "risk_level": case.risk_level.value,
            "created_at": case.created_at.isoformat(), "documents": len(docs),
            "to_review": sum(f.status.value != "OBSERVATION" and f.review.decision.value == "pending" for f in findings),
            "findings": sum(f.status.value != "OBSERVATION" for f in findings),
            "conflicts": sum(bool(f.discrepancy_type) and f.status.value != "OBSERVATION" for f in findings),
        })
    return {
        "cases": len(cases), "documents": documents, "by_risk": dict(by_risk), "by_status": dict(by_status),
        "by_review": dict(by_review), "by_discrepancy": by_discrepancy.most_common(),
        "by_check": [
            {"check": check, "count": n, "dismissed": dismissed_by_check[check]} for check, n in by_check.most_common()
        ],
        "recent": rows[:25],
        "track_record": track_record(decisions_by_check),
        "min_decisions": MIN_DECISIONS,
    }


def track_record(decisions_by_check: dict[str, Counter] | None = None) -> list[dict]:
    """Per check: how many flags reached a reviewer, and what they decided. Flags only, not observations."""
    if decisions_by_check is None:
        decisions_by_check = {}
        for case in db.list_cases():
            for f in db.list_findings(case.id):
                if f.status.value != "OBSERVATION":
                    decisions_by_check.setdefault(f.detector, Counter())[f.review.decision.value] += 1
    out = []
    for check, c in decisions_by_check.items():
        decided = c["confirmed"] + c["dismissed"] + c["escalated"]
        out.append({
            "check": check, "flagged": sum(c.values()), "decided": decided, "confirmed": c["confirmed"],
            "dismissed": c["dismissed"], "escalated": c["escalated"],
            "dismissal_rate": round(c["dismissed"] / decided, 3) if decided >= MIN_DECISIONS else None,
        })
    return sorted(out, key=lambda r: (-(r["dismissal_rate"] or -1), -r["decided"], -r["flagged"]))
