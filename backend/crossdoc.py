"""Cross-document correlation: entity resolution, conflicts, reconciliation, evidence graph.

Discrepancies here only become visible with several documents together. Each finding links the
fields and bboxes from BOTH sides so the reviewer can trace it to every source location.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from backend.contextual import _column, _txn_table, field_ref
from backend.normalize import (
    MONEY_TOLERANCE, Comparison, clean_address, compare_addresses, compare_employers, compare_ids, compare_names,
    date_of, fmt_money, money_of, norm_address, norm_employer, norm_id, ocr_adjustment, parse_date,
    parse_money, parse_period,
)
from models.schemas import (
    BBox, Document, DocType, Entity, EntityMention, EntityType, EvidenceGraph, EvidenceItem,
    EvidenceKind, Field, Finding, FindingCategory, FindingStatus, GraphEdge, GraphNode,
    ProcessingStatus, Severity, TableCell,
)

# Which document to trust as the reference side: only used to pick the highlighted primary, and
# never to decide which value is true.
_AUTHORITY = {
    DocType.id_proof: 6, DocType.bank_statement: 5, DocType.address_proof: 4, DocType.salary_slip: 3,
    DocType.declaration: 2, DocType.application_form: 1, DocType.unknown: 0,
}
INCOME_TOLERANCE_PCT = Decimal("0.05")
_SALARY_WORDS = re.compile(r"\b(sal|salary|payroll|wages|pay\s*credit)\b", re.I)


def _compare_dates(a: str, b: str) -> Comparison:
    da, db = parse_date(a), parse_date(b)
    if da and db:
        return Comparison(da == db, 100.0 if da == db else 0.0,
                          "same date" if da == db else "dates differ")
    return Comparison(a.strip() == b.strip(), 0.0, "could not parse as dates")


@dataclass(frozen=True)
class EntitySpec:
    fields: tuple[str, ...]
    type: EntityType
    compare: Callable[[str, str], Comparison]
    key: str


SPECS = [
    EntitySpec(("person_name",), EntityType.person, compare_names, "person"),
    EntitySpec(("date_of_birth",), EntityType.date_of_birth, _compare_dates, "dob"),
    EntitySpec(("address",), EntityType.address, compare_addresses, "address"),
    EntitySpec(("employer_name",), EntityType.employer, compare_employers, "employer"),
    EntitySpec(("id_number",), EntityType.id_number, compare_ids, "id"),
    EntitySpec(("pan_number",), EntityType.id_number, compare_ids, "pan"),
    EntitySpec(("bank_account_number",), EntityType.account_number, compare_ids, "account"),
]


def _usable(docs: list[Document]) -> list[Document]:
    return [d for d in docs if d.status not in (ProcessingStatus.unsupported, ProcessingStatus.failed)]


def _value(f: Field) -> str:
    return f.value_norm or f.value_raw


def _cluster(spec: EntitySpec, docs: list[Document]) -> list[list[Field]]:
    clusters: list[list[Field]] = []
    for doc in docs:
        for f in doc.fields:
            if f.name not in spec.fields or not f.value_raw.strip():
                continue
            for cluster in clusters:
                if spec.compare(_value(cluster[0]), _value(f)).same or spec.compare(f.value_raw, cluster[0].value_raw).same:
                    cluster.append(f)
                    break
            else:
                clusters.append([f])
    return clusters


def _canonical(spec: EntitySpec, cluster: list[Field]) -> str:
    best = max(cluster, key=lambda f: (f.confidence, len(f.value_raw)))
    return clean_address(best.value_raw) if spec.key == "address" else best.value_raw.strip()


def _entity(case_id: str, spec: EntitySpec, cluster: list[Field], conflict: bool) -> Entity:
    return Entity(
        case_id=case_id, type=spec.type, canonical_value=_canonical(spec, cluster), conflict=conflict,
        mentions=[EntityMention(doc_id=f.doc_id, field_id=f.id, value_raw=f.value_raw, page=f.page,
                                bbox=f.bbox, confidence=f.confidence) for f in cluster],
    )


def build_entities(docs: list[Document], case_id: str) -> list[Entity]:
    entities: list[Entity] = []
    usable = _usable(docs)
    for spec in SPECS:
        clusters = _cluster(spec, usable)
        for cluster in clusters:
            entities.append(_entity(case_id, spec, cluster, conflict=len(clusters) > 1))
    return entities


# ---- finding construction
def _doc_index(docs: list[Document]) -> dict[str, Document]:
    return {d.id: d for d in docs}


def _doc_label(doc: Document | None) -> str:
    if doc is None:
        return "a document"
    return f"{doc.doc_type.value.replace('_', ' ')} ({doc.filename})"


def _conflict(case_id: str, dtype: str, title: str, explanation: str, side_a: list[Field],
              side_b: list[Field], docs_by_id: dict[str, Document], severity: Severity,
              confidence: float, primary: Field | None = None,
              extra: list[EvidenceItem] | None = None,
              status: FindingStatus = FindingStatus.INCONSISTENCY) -> Finding:
    involved = side_a + side_b
    if primary is None:
        # The highlighted side is the smaller group, then the less authoritative document.
        candidates = side_a if len(side_a) < len(side_b) else side_b if len(side_b) < len(side_a) else involved
        primary = min(candidates, key=lambda f: _AUTHORITY.get(
            docs_by_id[f.doc_id].doc_type if f.doc_id in docs_by_id else DocType.unknown, 0))
    doc_ids = list(dict.fromkeys(f.doc_id for f in involved))
    return Finding(
        case_id=case_id, status=status, category=FindingCategory.cross_document, severity=severity,
        confidence=round(max(0.05, min(confidence, 0.99)), 3), title=title, doc_id=primary.doc_id,
        page=primary.page, bbox=primary.bbox, related_doc_ids=doc_ids,
        related_field_ids=[f.id for f in involved],
        evidence=[field_ref(f, f"{f.name} on {_doc_label(docs_by_id.get(f.doc_id))}") for f in involved]
        + (extra or []),
        explanation=explanation, detector=f"cross.{dtype}", discrepancy_type=dtype,
    )


def _sides_text(clusters: list[list[Field]], docs_by_id: dict[str, Document],
                display: Callable[[str], str] = str.strip) -> str:
    parts = []
    for cluster in clusters:
        where = ", ".join(dict.fromkeys(_doc_label(docs_by_id.get(f.doc_id)) for f in cluster))
        parts.append(f"'{display(cluster[0].value_raw)}' on {where}")
    return "; ".join(parts)


# ---- identity conflicts
def _dob_findings(case_id, docs, by_id) -> list[Finding]:
    spec = next(s for s in SPECS if s.key == "dob")
    clusters = _cluster(spec, docs)
    out = []
    for i, a in enumerate(clusters):
        for b in clusters[i + 1:]:
            va, vb = _value(a[0]), _value(b[0])
            da, db = parse_date(va) or parse_date(a[0].value_raw), parse_date(vb) or parse_date(b[0].value_raw)
            factor, note = ocr_adjustment(a + b, a[0].value_raw, b[0].value_raw, docs=by_id)
            extra = ""
            if da and db and da.day == db.month and da.month == db.day:
                extra = " The day and month are swapped, which can come from a date-format mix-up."
                factor = min(factor, 0.7)
            out.append(_conflict(
                case_id, "dob_mismatch", "Date of birth differs across documents",
                f"Date of birth conflict: {_sides_text([a, b], by_id)}.{extra}" + (f" {note}" if note else ""),
                a, b, by_id, Severity.high if factor > 0.6 else Severity.medium, 0.95 * factor,
            ))
    return out


def _name_findings(case_id, docs, by_id) -> list[Finding]:
    spec = next(s for s in SPECS if s.key == "person")
    clusters = _cluster(spec, docs)
    out = []
    for i, a in enumerate(clusters):
        for b in clusters[i + 1:]:
            cmp = compare_names(a[0].value_raw, b[0].value_raw)
            factor, note = ocr_adjustment(a + b, a[0].value_raw, b[0].value_raw, docs=by_id)
            close = cmp.score >= 80
            title = "Name spelling varies across documents" if close else "Different names across documents"
            detail = "The names are close, but differ beyond an initial or a dropped middle name." if close \
                else "These look like different people, or a document belonging to someone else."
            out.append(_conflict(
                case_id, "name_variant", title,
                f"Applicant name conflict: {_sides_text([a, b], by_id)} (similarity {cmp.score:.0f}/100). {detail}"
                + (f" {note}" if note else ""),
                a, b, by_id, (Severity.medium if close else Severity.high) if factor > 0.6 else Severity.low,
                (0.8 if close else 0.92) * factor,
            ))
    return out


def _address_findings(case_id, docs, by_id) -> list[Finding]:
    spec = next(s for s in SPECS if s.key == "address")
    clusters = _cluster(spec, docs)
    out = []
    for i, a in enumerate(clusters):
        for b in clusters[i + 1:]:
            cmp = compare_addresses(a[0].value_raw, b[0].value_raw)
            factor, note = ocr_adjustment(a + b, norm_address(a[0].value_raw), norm_address(b[0].value_raw))
            subtle = cmp.score >= 80
            title = "Subtle address variant across documents" if subtle else "Different addresses across documents"
            out.append(_conflict(
                case_id, "address_variant", title,
                f"Address conflict: {_sides_text([a, b], by_id, clean_address)}. {cmp.reason.capitalize()}. "
                f"Abbreviations and formatting were normalized first, so this isn't just 'Rd.' vs 'Road'."
                + (f" {note}" if note else ""),
                a, b, by_id, Severity.medium if factor > 0.6 else Severity.low, 0.85 * factor,
            ))
    return out


def _employer_findings(case_id, docs, by_id) -> list[Finding]:
    spec = next(s for s in SPECS if s.key == "employer")
    clusters = _cluster(spec, docs)
    out = []
    for i, a in enumerate(clusters):
        for b in clusters[i + 1:]:
            cmp = compare_employers(a[0].value_raw, b[0].value_raw)
            factor, note = ocr_adjustment(a + b, norm_employer(a[0].value_raw), norm_employer(b[0].value_raw))
            out.append(_conflict(
                case_id, "employer_mismatch", "Employer name differs across documents",
                f"Employer conflict: {_sides_text([a, b], by_id)} (similarity {cmp.score:.0f}/100 after removing "
                "legal suffixes such as Pvt Ltd)." + (f" {note}" if note else ""),
                a, b, by_id, Severity.high if factor > 0.6 else Severity.low, 0.88 * factor,
            ))
    return out


def _id_findings(case_id, docs, by_id) -> list[Finding]:
    out = []
    for key, dtype, label in (
        ("id", "id_number_mismatch", "ID number"), ("pan", "id_number_mismatch", "PAN"),
        ("account", "account_number_mismatch", "Bank account number"),
    ):
        spec = next(s for s in SPECS if s.key == key)
        clusters = _cluster(spec, docs)
        for i, a in enumerate(clusters):
            for b in clusters[i + 1:]:
                factor, note = ocr_adjustment(a + b, norm_id(a[0].value_raw), norm_id(b[0].value_raw), docs=by_id)
                out.append(_conflict(
                    case_id, dtype, f"{label} differs across documents",
                    f"{label} conflict: {_sides_text([a, b], by_id)}." + (f" {note}" if note else ""),
                    a, b, by_id, Severity.high if factor > 0.6 else Severity.low, 0.93 * factor,
                ))
    return out


# ---- reconciliation
@dataclass
class _Credit:
    doc: Document
    row: int
    when: date | None
    amount: Decimal
    description: str
    cell: TableCell
    page: int
    labelled_salary: bool


def _credits(doc: Document) -> list[_Credit]:
    table = _txn_table(doc)
    if table is None:
        return []
    col_credit, col_desc, col_date = _column(table, "credit"), _column(table, "desc"), _column(table, "date")
    if col_credit is None:
        return []
    out = []
    for i, row in enumerate(table.rows):
        if col_credit >= len(row) or not row[col_credit].text.strip():
            continue
        amount = parse_money(row[col_credit].text)
        if amount is None or amount == 0:
            continue
        desc = row[col_desc].text if col_desc is not None and col_desc < len(row) else ""
        when = parse_date(row[col_date].text) if col_date is not None and col_date < len(row) else None
        out.append(_Credit(doc, i + 1, when, amount, desc, row[col_credit], table.page, bool(_SALARY_WORDS.search(desc))))
    return out


def _credit_evidence(credit: _Credit, label: str) -> EvidenceItem:
    return EvidenceItem(
        kind=EvidenceKind.raw_value, label=label, doc_id=credit.doc.id, page=credit.page, bbox=credit.cell.bbox,
        data={"amount": str(credit.amount), "description": credit.description,
              "date": credit.when.isoformat() if credit.when else None, "row": credit.row,
              "ocr_confidence": round(credit.cell.confidence, 3)},
    )


def _lone_matching_credit(case_id, net_f, net, match, salary_credits, by_id) -> Finding | None:
    """Net pay reconciles with one credit, while every other month agrees on a different amount."""
    same = [c for c in salary_credits if abs(c.amount - net) <= MONEY_TOLERANCE]
    others = [c for c in salary_credits if abs(c.amount - net) > MONEY_TOLERANCE]
    if len(same) != 1 or len(others) < 2:
        return None
    usual = others[0].amount
    if any(abs(c.amount - usual) > MONEY_TOLERANCE for c in others) or abs(usual - net) / usual < Decimal("0.05"):
        return None
    finding = _conflict(
        case_id, "salary_vs_bank_credit", "Net pay matches only one of the monthly salary credits",
        f"Net pay {fmt_money(net)} matches only the credit in row {match.row}. The other {len(others)} salary "
        f"credits on the statement are all {fmt_money(usual)}, so this one month stands apart.",
        [net_f], [], by_id, Severity.medium, 0.75, primary=net_f,
        extra=[_credit_evidence(match, "The one matching credit")]
        + [_credit_evidence(c, f"Usual salary credit, row {c.row}") for c in others[:3]],
    )
    finding.related_doc_ids = list(dict.fromkeys(finding.related_doc_ids + [match.doc.id]))
    return finding


def _salary_vs_bank(case_id, docs, by_id) -> list[Finding]:
    slips = [d for d in docs if d.doc_type == DocType.salary_slip]
    statements = [d for d in docs if d.doc_type == DocType.bank_statement]
    if not slips or not statements:
        return []
    out = []
    credits_all = [c for s in statements for c in _credits(s)]
    for slip in slips:
        net_f = next((f for f in slip.fields if f.name == "net_pay"), None)
        net = money_of(net_f)
        if net_f is None or net is None:
            continue
        employer_f = next((f for f in slip.fields if f.name == "employer_name"), None)
        employer = norm_employer(employer_f.value_raw) if employer_f else ""

        def looks_like_salary(c: _Credit) -> bool:
            if c.labelled_salary:
                return True
            return bool(employer) and all(tok in c.description.upper() for tok in employer.split()[:1])

        period_f = next((f for f in slip.fields if f.name == "pay_period"), None)
        period = (parse_period(period_f.value_raw) or parse_period(_value(period_f))) if period_f else None
        salary_credits = [c for c in credits_all if looks_like_salary(c)]
        in_window = salary_credits
        if period and salary_credits:
            start = period[0]
            # Salary for a month normally arrives in that month or early in the next one.
            end = date.fromordinal(period[1].toordinal() + 12)
            dated = [c for c in salary_credits if c.when and start <= c.when <= end]
            in_window = dated or salary_credits

        if not in_window:
            if credits_all and any(abs(c.amount - net) <= MONEY_TOLERANCE for c in credits_all):
                continue  # an unlabelled credit reconciles exactly
            if not credits_all:
                continue  # no extractable transactions: nothing can be concluded
            out.append(_conflict(
                case_id, "salary_vs_bank_credit", "No bank credit matches the stated net pay",
                f"Net pay on the slip is {fmt_money(net)}, but no credit on the statement equals it and none is "
                f"labelled as salary or names the employer. {len(credits_all)} credit(s) were checked.",
                [net_f], [], by_id, Severity.medium, 0.7, primary=net_f,
                extra=[_credit_evidence(c, f"Bank credit, row {c.row}") for c in credits_all[:5]],
            ))
            continue

        closest = min(in_window, key=lambda c: abs(c.amount - net))
        diff = abs(closest.amount - net)
        if diff <= MONEY_TOLERANCE:
            outlier = _lone_matching_credit(case_id, net_f, net, closest, salary_credits, by_id)
            if outlier:
                out.append(outlier)
            continue
        factor, note = ocr_adjustment([net_f], str(net), str(closest.amount))
        if closest.cell.confidence < 0.55:
            factor, note = min(factor, 0.5), note or "OCR confidence on the bank credit is low; check the image."
        pct = (diff / net * 100) if net else Decimal(0)
        out.append(_conflict(
            case_id, "salary_vs_bank_credit", "Net pay on the salary slip does not match the bank credit",
            f"The salary slip states net pay {fmt_money(net)}, but the closest salary credit on the bank statement "
            f"is {fmt_money(closest.amount)} ('{closest.description.strip()}', row {closest.row}), a difference of "
            f"{fmt_money(diff)} ({pct:.1f}%)." + (f" {note}" if note else ""),
            [net_f], [], by_id, Severity.high if factor > 0.6 and pct >= 2 else Severity.medium, 0.92 * factor,
            primary=net_f,
            extra=[_credit_evidence(closest, f"Salary credit on {_doc_label(closest.doc)}")]
            + [_credit_evidence(c, f"Other salary credit, row {c.row}") for c in in_window if c is not closest][:3],
        ))
        out[-1].related_doc_ids = list(dict.fromkeys(out[-1].related_doc_ids + [closest.doc.id]))
    return out


def _declared_vs_actual(case_id, docs, by_id) -> list[Finding]:
    declared = [f for d in docs for f in d.fields if f.name == "declared_monthly_income"]
    if not declared:
        return []
    out = []
    # Declared income conflicting between two documents.
    amounts = [(f, money_of(f)) for f in declared if money_of(f) is not None]
    for i, (fa, va) in enumerate(amounts):
        for fb, vb in amounts[i + 1:]:
            if abs(va - vb) > MONEY_TOLERANCE:
                factor, note = ocr_adjustment([fa, fb], str(va), str(vb))
                out.append(_conflict(
                    case_id, "declared_vs_actual_income", "Declared income differs between documents",
                    f"Declared monthly income is {fmt_money(va)} on {_doc_label(by_id.get(fa.doc_id))} and "
                    f"{fmt_money(vb)} on {_doc_label(by_id.get(fb.doc_id))}." + (f" {note}" if note else ""),
                    [fa], [fb], by_id, Severity.medium if factor > 0.6 else Severity.low, 0.9 * factor,
                ))

    slips = [d for d in docs if d.doc_type == DocType.salary_slip]
    gross_f = next((f for d in slips for f in d.fields if f.name == "gross_pay"), None)
    net_f = next((f for d in slips for f in d.fields if f.name == "net_pay"), None)
    gross, net = money_of(gross_f), money_of(net_f)
    upper = gross if gross is not None else net
    if upper is None:
        return out
    lower = net if net is not None else gross
    slip_fields = [f for f in (gross_f, net_f) if f is not None]
    seen: set[str] = set()
    for f, value in amounts:
        limit_hi = upper * (1 + INCOME_TOLERANCE_PCT)
        limit_lo = lower * (1 - INCOME_TOLERANCE_PCT)
        if limit_lo <= value <= limit_hi or str(value) in seen:
            continue
        seen.add(str(value))
        factor, note = ocr_adjustment([f] + slip_fields, str(value), str(upper))
        direction = "above" if value > limit_hi else "below"
        out.append(_conflict(
            case_id, "declared_vs_actual_income", f"Declared income is {direction} what the salary slip shows",
            f"Declared monthly income {fmt_money(value)} on {_doc_label(by_id.get(f.doc_id))} is {direction} the "
            f"slip's range of net {fmt_money(lower)} to gross {fmt_money(upper)} by more than "
            f"{int(INCOME_TOLERANCE_PCT * 100)}%." + (f" {note}" if note else ""),
            [f], slip_fields, by_id, Severity.high if factor > 0.6 and value > limit_hi else Severity.medium,
            0.88 * factor, primary=f,
        ))
    return out


def _employment_dates(case_id, docs, by_id) -> list[Finding]:
    doj_fields = [f for d in docs for f in d.fields if f.name == "date_of_joining"]
    dob_fields = [f for d in docs for f in d.fields if f.name == "date_of_birth"]
    out = []
    parsed = [(f, date_of(f)) for f in doj_fields if date_of(f)]
    for i, (fa, da) in enumerate(parsed):
        for fb, db in parsed[i + 1:]:
            if da != db:
                factor, note = ocr_adjustment([fa, fb], fa.value_raw, fb.value_raw, docs=by_id)
                out.append(_conflict(
                    case_id, "employment_date_conflict", "Joining date differs across documents",
                    f"Date of joining is {da.isoformat()} on {_doc_label(by_id.get(fa.doc_id))} and "
                    f"{db.isoformat()} on {_doc_label(by_id.get(fb.doc_id))}." + (f" {note}" if note else ""),
                    [fa], [fb], by_id, Severity.medium if factor > 0.6 else Severity.low, 0.88 * factor,
                ))
    for fj, dj in parsed:
        for fb in dob_fields:
            if fb.doc_id == fj.doc_id:
                continue  # the within-document check already covers this
            dob = date_of(fb)
            if dob and (dj.year - dob.year) < 14:
                factor, note = ocr_adjustment([fj, fb])
                out.append(_conflict(
                    case_id, "employment_date_conflict", "Joining date implies an implausibly young employee",
                    f"Date of joining {dj.isoformat()} is under 14 years after the date of birth {dob.isoformat()} "
                    f"on {_doc_label(by_id.get(fb.doc_id))}." + (f" {note}" if note else ""),
                    [fj], [fb], by_id, Severity.medium, 0.85 * factor, primary=fj,
                ))
                break
    # A statement credit from this employer before the stated joining date.
    statements = [d for d in docs if d.doc_type == DocType.bank_statement]
    for fj, dj in parsed:
        early = [c for s in statements for c in _credits(s) if c.labelled_salary and c.when and c.when < dj]
        if early:
            first = min(early, key=lambda c: c.when)
            out.append(_conflict(
                case_id, "employment_date_conflict", "Salary credit predates the stated joining date",
                f"A salary-labelled credit dated {first.when.isoformat()} appears before the stated date of joining "
                f"{dj.isoformat()}.", [fj], [], by_id, Severity.medium, 0.8, primary=fj,
                extra=[_credit_evidence(first, "Earlier salary credit")],
            ))
    return out


def correlate(docs: list[Document], entities: list[Entity], case_id: str) -> list[Finding]:
    """All cross-document discrepancy types. Each is isolated from the others' failures."""
    usable = _usable(docs)
    if len(usable) < 2:
        return []
    by_id = _doc_index(usable)
    findings: list[Finding] = []
    for check in (_name_findings, _dob_findings, _address_findings, _employer_findings, _id_findings,
                  _salary_vs_bank, _declared_vs_actual, _employment_dates):
        try:
            findings.extend(check(case_id, usable, by_id))
        except Exception as exc:  # noqa: BLE001 - isolation; recorded, not silent
            findings.append(Finding(
                case_id=case_id, status=FindingStatus.OBSERVATION, category=FindingCategory.cross_document,
                severity=Severity.info, confidence=1.0, title="A cross-document check could not complete",
                detector="cross.check_error",
                explanation=f"{check.__name__.strip('_')} stopped with {type(exc).__name__}; its result is "
                            "absent, not negative.",
            ))
    return findings


# ---- evidence graph
def _conflict_doc_pair(finding: Finding, linked: list[str], entity_docs: dict[str, list[str]],
                       by_doc: dict[str, Document]) -> tuple[str, str] | None:
    """The one document pair that shows a finding: its highlighted side and the best opposite side.

    One red edge per finding. If one document disagrees with five others, that's one discrepancy
    and not five. The entity nodes still show every document on each side.
    """
    primary = finding.doc_id

    def authority(doc_id: str) -> int:
        doc = by_doc.get(doc_id)
        return _AUTHORITY.get(doc.doc_type, 0) if doc else -1

    opposite: list[str] = []
    if len(linked) >= 2:
        side_of_primary = [e for e in linked if primary in entity_docs.get(e, [])]
        for ent in linked:
            if ent not in side_of_primary:
                opposite += entity_docs.get(ent, [])
    if not opposite:
        opposite = list(finding.related_doc_ids)
    opposite = [d for d in dict.fromkeys(opposite) if d != primary]
    if primary is None or not opposite:
        return None
    return primary, max(opposite, key=authority)


def build_graph(case_id: str, docs: list[Document], entities: list[Entity],
                findings: list[Finding]) -> EvidenceGraph:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []
    node_ids: set[str] = set()

    def edge(source, target, kind, conflict=False, label=None, finding_id=None):
        edges.append(GraphEdge(id=f"e{len(edges) + 1}", source=source, target=target, kind=kind,
                               conflict=conflict, label=label, finding_id=finding_id))

    for doc in docs:
        nodes.append(GraphNode(id=doc.id, kind="document", label=doc.filename, ref_id=doc.id,
                               meta={"doc_type": doc.doc_type.value, "status": doc.status.value}))
        node_ids.add(doc.id)

    field_to_entity: dict[str, str] = {}
    agreements: dict[tuple[str, str], list[str]] = {}
    for ent in entities:
        nodes.append(GraphNode(id=ent.id, kind="entity", label=ent.canonical_value, ref_id=ent.id,
                               meta={"type": ent.type.value, "conflict": ent.conflict,
                                     "mention_count": len(ent.mentions)}))
        node_ids.add(ent.id)
        for doc_id in dict.fromkeys(m.doc_id for m in ent.mentions):
            if doc_id in node_ids:
                edge(doc_id, ent.id, "mentions", conflict=False, label=ent.type.value)
        for m in ent.mentions:
            field_to_entity[m.field_id] = ent.id
        docs_of_entity = list(dict.fromkeys(m.doc_id for m in ent.mentions))
        for i, a in enumerate(docs_of_entity):
            for b in docs_of_entity[i + 1:]:
                agreements.setdefault(tuple(sorted((a, b))), []).append(ent.type.value)

    for (a, b), kinds in agreements.items():
        if a in node_ids and b in node_ids:
            edge(a, b, "agrees", conflict=False, label=", ".join(sorted(set(kinds))))
    entity_docs = {e.id: list(dict.fromkeys(m.doc_id for m in e.mentions)) for e in entities}
    by_doc = {d.id: d for d in docs}

    for finding in findings:
        if finding.category != FindingCategory.cross_document and not finding.related_field_ids and finding.doc_id is None:
            continue
        fid = f"f_{finding.id}"
        nodes.append(GraphNode(id=fid, kind="finding", label=finding.title, ref_id=finding.id,
                               meta={"status": finding.status.value, "severity": finding.severity.value,
                                     "category": finding.category.value, "confidence": finding.confidence}))
        node_ids.add(fid)
        if finding.doc_id in node_ids:
            edge(fid, finding.doc_id, "supports", label="anchored on", finding_id=finding.id)
        linked = list(dict.fromkeys(field_to_entity[f] for f in finding.related_field_ids if f in field_to_entity))
        for ent_id in linked:
            edge(fid, ent_id, "supports", label="concerns", finding_id=finding.id)
        if finding.category == FindingCategory.cross_document:
            # Red edges: the entity clusters or documents that disagree.
            if len(linked) >= 2:
                for i, a in enumerate(linked):
                    for b in linked[i + 1:]:
                        edge(a, b, "conflicts", conflict=True, label=finding.discrepancy_type, finding_id=finding.id)
            pair = _conflict_doc_pair(finding, linked, entity_docs, by_doc)
            if pair and pair[0] in node_ids and pair[1] in node_ids:
                edge(pair[0], pair[1], "conflicts", conflict=True, label=finding.discrepancy_type, finding_id=finding.id)
        for other in finding.related_finding_ids:
            if finding.id < other:  # one edge per pair
                edges.append(GraphEdge(id=f"e{len(edges) + 1}", source=fid, target=f"f_{other}", kind="supports",
                                       label="corroborates", finding_id=finding.id))
    # Drop corroboration edges whose other end wasn't added as a node.
    edges = [e for e in edges if e.source in node_ids and e.target in node_ids]
    return EvidenceGraph(case_id=case_id, nodes=nodes, edges=edges)


__all__ = ["build_entities", "correlate", "build_graph", "BBox"]
