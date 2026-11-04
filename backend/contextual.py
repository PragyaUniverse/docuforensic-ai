"""Within-document verification: relationships between fields on a single document.

Every check uses extracted values with their confidence. A mismatch that OCR could explain gets a
lower confidence and says so; nothing here treats OCR output as ground truth.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.normalize import (
    IFSC_RE, MONEY_TOLERANCE, PAN_RE, date_of, fmt_money, money_of, norm_id, ocr_adjustment,
    parse_money, parse_period, verhoeff_valid,
)
from config.settings import settings
from models.schemas import (
    BBox, Document, DocType, EvidenceItem, EvidenceKind, Field, Finding, FindingCategory,
    FindingStatus, Severity, Table, TableCell, TextSource,
)

MIN_WORKING_AGE_YEARS = 14
_DOC_DATE_FIELDS = ("application_date", "bill_date", "declaration_date", "document_date")


def field_map(doc: Document) -> dict[str, Field]:
    """Highest-confidence field per name."""
    out: dict[str, Field] = {}
    for f in doc.fields:
        if f.name not in out or f.confidence > out[f.name].confidence:
            out[f.name] = f
    return out


def field_ref(f: Field, label: str | None = None) -> EvidenceItem:
    return EvidenceItem(
        kind=EvidenceKind.field_ref, label=label or f.name, doc_id=f.doc_id, page=f.page, bbox=f.bbox,
        field_id=f.id,
        data={"field": f.name, "value": f.value_raw, "normalized": f.value_norm,
              "confidence": round(f.confidence, 3), "source": f.source.value},
    )


def _finding(doc: Document, detector: str, title: str, explanation: str, anchor: Field | None,
             involved: list[Field], status: FindingStatus = FindingStatus.INCONSISTENCY,
             severity: Severity = Severity.medium, confidence: float = 0.9,
             bbox: BBox | None = None, page: int | None = None,
             extra: list[EvidenceItem] | None = None) -> Finding:
    return Finding(
        case_id=doc.case_id, status=status, category=FindingCategory.contextual, severity=severity,
        confidence=round(max(0.05, min(confidence, 0.99)), 3), title=title, doc_id=doc.id,
        page=anchor.page if anchor else page, bbox=anchor.bbox if anchor else bbox,
        related_doc_ids=[doc.id], related_field_ids=[f.id for f in involved],
        evidence=[field_ref(f) for f in involved] + (extra or []), explanation=explanation,
        detector=detector,
    )


def _downgrade(sev: Severity, factor: float) -> Severity:
    if factor > 0.6:
        return sev
    order = [Severity.info, Severity.low, Severity.medium, Severity.high]
    return order[max(0, order.index(sev) - 1)]


# ---- salary arithmetic
def _check_salary(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    out: list[Finding] = []
    net, gross, ded = fm.get("net_pay"), fm.get("gross_pay"), fm.get("total_deductions")
    v_net, v_gross, v_ded = money_of(net), money_of(gross), money_of(ded)

    if v_net is not None and v_gross is not None and v_ded is not None:
        expected = v_gross - v_ded
        if abs(expected - v_net) > MONEY_TOLERANCE:
            involved = [gross, ded, net]  # type: ignore[list-item]
            factor, note = ocr_adjustment(involved, str(expected), str(v_net))
            out.append(_finding(
                doc, "context.arithmetic_salary", "Net pay does not equal gross pay minus deductions",
                f"Gross pay {fmt_money(v_gross)} minus total deductions {fmt_money(v_ded)} gives "
                f"{fmt_money(expected)}, but the document states net pay {fmt_money(v_net)} (difference "
                f"{fmt_money(abs(expected - v_net))})." + (f" {note}" if note else ""),
                net, involved, severity=_downgrade(Severity.high, factor), confidence=0.95 * factor,
                extra=[EvidenceItem(kind=EvidenceKind.raw_value, label="Recomputed net pay", doc_id=doc.id,
                                    data={"expected": str(expected), "stated": str(v_net),
                                          "difference": str(abs(expected - v_net))})],
            ))

    components = [fm[n] for n in ("basic_pay", "hra", "other_allowances") if n in fm]
    values = [money_of(f) for f in components]
    if gross is not None and v_gross is not None and len(components) >= 2 and all(v is not None for v in values):
        total = sum(values, Decimal(0))  # type: ignore[arg-type]
        if "other_allowances" in fm and abs(total - v_gross) > MONEY_TOLERANCE:
            involved = components + [gross]
            factor, note = ocr_adjustment(involved, str(total), str(v_gross))
            out.append(_finding(
                doc, "context.arithmetic_salary", "Gross pay does not equal the sum of its components",
                f"Listed earnings sum to {fmt_money(total)}, but gross pay is stated as "
                f"{fmt_money(v_gross)}." + (f" {note}" if note else ""),
                gross, involved, severity=_downgrade(Severity.medium, factor), confidence=0.9 * factor,
            ))
    return out


# ---- bank statement arithmetic
def _cell_money(cell: TableCell | None) -> Decimal | None:
    return parse_money(cell.text) if cell and cell.text.strip() else None


def _column(table: Table, name: str) -> int | None:
    for i, header in enumerate(table.headers):
        if name in header.strip().lower():
            return i
    return None


def _txn_table(doc: Document) -> Table | None:
    return next((t for t in doc.tables if t.name == "transactions" and t.rows), None)


def _check_balance(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    table = _txn_table(doc)
    if table is None:
        return []
    deb, cre, bal = _column(table, "debit"), _column(table, "credit"), _column(table, "balance")
    if bal is None or (deb is None and cre is None):
        return []
    opening = money_of(fm.get("opening_balance"))
    previous = opening
    breaks: list[dict] = []
    for idx, row in enumerate(table.rows):
        if bal >= len(row):
            previous = None
            continue
        balance = _cell_money(row[bal])
        if balance is None:
            previous = None
            continue
        debit = _cell_money(row[deb]) if deb is not None and deb < len(row) else None
        credit = _cell_money(row[cre]) if cre is not None and cre < len(row) else None
        if previous is not None:
            expected = previous - (debit or Decimal(0)) + (credit or Decimal(0))
            if abs(expected - balance) > MONEY_TOLERANCE:
                breaks.append({"row": idx + 1, "expected": expected, "stated": balance, "cell": row[bal],
                               "credit": row[cre] if credit is not None and cre is not None else None,
                               "debit": row[deb] if debit is not None and deb is not None else None})
        previous = balance

    out: list[Finding] = []
    if breaks:
        first = breaks[0]
        confs = [b["cell"].confidence for b in breaks]
        low = min(confs)
        ocr_based = any(w.source != TextSource.text_layer for p in doc.pages for w in p.words[:1])
        factor = (0.5 if low < settings.low_ocr_confidence else 0.8 + 0.2 * low) if ocr_based else 1.0
        note = (" A low-confidence OCR reading of a balance cell could explain this; check the image."
                if factor <= 0.5 else "")
        rows_text = "; ".join(
            f"row {b['row']}: expected {fmt_money(b['expected'])}, stated {fmt_money(b['stated'])}"
            for b in breaks[:5]
        )
        evidence = [
            EvidenceItem(kind=EvidenceKind.raw_value, label=f"Transaction row {b['row']}", doc_id=doc.id,
                         page=table.page, bbox=b["cell"].bbox,
                         data={"expected": str(b["expected"]), "stated": str(b["stated"]),
                               "ocr_confidence": round(b["cell"].confidence, 3)})
            for b in breaks[:8]
        ]
        out.append(_finding(
            doc, "context.arithmetic_balance", "Running balance breaks in the transaction table",
            f"Applying each debit and credit to the previous balance doesn't reproduce the stated balance "
            f"in {len(breaks)} row(s): {rows_text}.{note}",
            None, [], severity=_downgrade(Severity.high, factor), confidence=0.93 * factor,
            bbox=first["cell"].bbox or table.bbox, page=table.page, extra=evidence,
        ))

    closing = fm.get("closing_balance")
    v_closing = money_of(closing)
    if v_closing is not None and table.rows and bal < len(table.rows[-1]):
        last = _cell_money(table.rows[-1][bal])
        if last is not None and abs(last - v_closing) > MONEY_TOLERANCE:
            factor, note = ocr_adjustment([closing], str(last), str(v_closing))  # type: ignore[list-item]
            out.append(_finding(
                doc, "context.arithmetic_balance", "Closing balance disagrees with the last transaction",
                f"The last transaction leaves a balance of {fmt_money(last)}, but the stated closing balance "
                f"is {fmt_money(v_closing)}." + (f" {note}" if note else ""),
                closing, [closing], severity=_downgrade(Severity.medium, factor),  # type: ignore[list-item]
                confidence=0.9 * factor,
            ))
    return out


# ---- date logic
def _check_dates(doc: Document, fm: dict[str, Field], today: date) -> list[Finding]:
    out: list[Finding] = []
    dob_f, doj_f = fm.get("date_of_birth"), fm.get("date_of_joining")
    dob, doj = date_of(dob_f), date_of(doj_f)

    def add(title: str, explanation: str, anchor: Field, involved: list[Field],
            severity: Severity = Severity.medium, base: float = 0.85) -> None:
        factor, note = ocr_adjustment(involved)
        out.append(_finding(doc, "context.date_order", title,
                            explanation + (f" {note}" if note else ""), anchor, involved,
                            severity=_downgrade(severity, factor), confidence=base * factor))

    if dob and dob > today:
        add("Date of birth is in the future", f"The date of birth reads {dob.isoformat()}, later than today.",
            dob_f, [dob_f], Severity.high)  # type: ignore[list-item,arg-type]
    if dob and doj and doj < dob.replace(year=dob.year + MIN_WORKING_AGE_YEARS, day=min(dob.day, 28)):
        add("Joining date implies an implausibly young employee",
            f"Date of joining {doj.isoformat()} is less than {MIN_WORKING_AGE_YEARS} years after date of birth "
            f"{dob.isoformat()}.", doj_f, [dob_f, doj_f])  # type: ignore[list-item,arg-type]

    period_f = fm.get("pay_period")
    period = parse_period(period_f.value_norm or period_f.value_raw) if period_f else None
    if period and doj and doj > period[1]:
        add("Joining date is after the pay period",
            f"The slip covers a pay period ending {period[1].isoformat()}, but the date of joining is "
            f"{doj.isoformat()}.", doj_f, [doj_f, period_f])  # type: ignore[list-item,arg-type]

    for name in _DOC_DATE_FIELDS:
        f = fm.get(name)
        value = date_of(f)
        if f is None or value is None:
            continue
        if value > today + timedelta(days=1):
            add(f"{name.replace('_', ' ').capitalize()} is in the future",
                f"The document states {value.isoformat()}, later than the processing date {today.isoformat()}.",
                f, [f])
        if dob and value < dob:
            add(f"{name.replace('_', ' ').capitalize()} precedes the date of birth",
                f"The document date {value.isoformat()} is earlier than the date of birth {dob.isoformat()}.",
                f, [f, dob_f])  # type: ignore[list-item]

    st_f = fm.get("statement_period")
    statement = parse_period(st_f.value_norm or st_f.value_raw) if st_f else None
    if st_f and statement and statement[0] > statement[1]:
        add("Statement period ends before it starts",
            f"The period runs from {statement[0].isoformat()} to {statement[1].isoformat()}.", st_f, [st_f])

    table = _txn_table(doc)
    if table is not None:
        col = _column(table, "date")
        if col is not None:
            _check_txn_dates(doc, table, col, statement, st_f, out)
    return out


def _check_txn_dates(doc, table, col, statement, st_f, out) -> None:
    from backend.normalize import parse_date

    previous = None
    outside, unordered = [], []
    for idx, row in enumerate(table.rows):
        if col >= len(row):
            continue
        value = parse_date(row[col].text)
        if value is None:
            continue
        if statement and not (statement[0] <= value <= statement[1]):
            outside.append((idx + 1, value, row[col]))
        if previous and value < previous:
            unordered.append((idx + 1, value, row[col]))
        previous = value
    for items, title, text in (
        (outside, "Transactions dated outside the statement period",
         "fall outside the stated statement period"),
        (unordered, "Transactions out of date order", "are earlier than the preceding row"),
    ):
        if items:
            first = items[0]
            rows = ", ".join(f"row {i} ({d.isoformat()})" for i, d, _ in items[:5])
            out.append(_finding(
                doc, "context.date_order", title, f"Transaction dates {text}: {rows}.", None,
                [st_f] if st_f and items is outside else [], severity=Severity.medium, confidence=0.8,
                bbox=first[2].bbox or table.bbox, page=table.page,
            ))


# ---- identifiers
def _check_ids(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    out: list[Finding] = []
    aadhaar_like = fm.get("id_number")
    if aadhaar_like is not None:
        value = norm_id(aadhaar_like.value_norm or aadhaar_like.value_raw)
        if len(value) == 12 and value.isdigit() and not verhoeff_valid(value):
            factor, note = ocr_adjustment([aadhaar_like])
            if aadhaar_like.source != TextSource.text_layer:
                factor = min(factor, 0.7)
                note = note or "One misread digit by OCR would also fail this check; check the image."
            out.append(_finding(
                doc, "context.id_checksum", "12-digit ID number fails its Verhoeff check digit",
                "The number has the 12-digit Aadhaar-style format, but its check digit doesn't validate. "
                "A correctly issued number passes this check." + (f" {note}" if note else ""),
                aadhaar_like, [aadhaar_like], severity=_downgrade(Severity.medium, factor),
                confidence=0.9 * factor,
            ))
    pan = fm.get("pan_number")
    if pan is not None:
        value = norm_id(pan.value_norm or pan.value_raw)
        if not PAN_RE.match(value):
            factor, note = ocr_adjustment([pan])
            out.append(_finding(
                doc, "context.id_checksum", "PAN does not match the expected format",
                f"'{pan.value_raw}' doesn't follow the five letters, four digits, one letter PAN format."
                + (f" {note}" if note else ""),
                pan, [pan], severity=_downgrade(Severity.medium, factor), confidence=0.85 * factor,
            ))
    ifsc = fm.get("ifsc")
    if ifsc is not None:
        value = norm_id(ifsc.value_norm or ifsc.value_raw)
        if not IFSC_RE.match(value):
            factor, note = ocr_adjustment([ifsc])
            out.append(_finding(
                doc, "context.id_checksum", "IFSC does not match the expected format",
                f"'{ifsc.value_raw}' doesn't follow the four letters, zero, six characters IFSC format."
                + (f" {note}" if note else ""),
                ifsc, [ifsc], severity=_downgrade(Severity.low, factor), confidence=0.8 * factor,
            ))
    return out


# ---- completeness
def _check_missing(doc: Document) -> list[Finding]:
    if not doc.missing_fields:
        return []
    labels = ", ".join(n.replace("_", " ") for n in doc.missing_fields)
    low_ocr = any((p.mean_ocr_confidence or 1.0) < settings.low_ocr_confidence for p in doc.pages)
    note = " Page OCR confidence is low, so these may be present but unread." if low_ocr else ""
    return [Finding(
        case_id=doc.case_id, status=FindingStatus.OBSERVATION, category=FindingCategory.contextual,
        severity=Severity.low, confidence=0.6 if low_ocr else 0.8,
        title=f"Expected fields not found on this {doc.doc_type.value.replace('_', ' ')}",
        doc_id=doc.id, page=0 if doc.pages else None, related_doc_ids=[doc.id],
        explanation=f"Fields usually present on this document type weren't extracted: {labels}.{note}",
        evidence=[EvidenceItem(kind=EvidenceKind.raw_value, label="Missing fields", doc_id=doc.id,
                               data={"missing": list(doc.missing_fields)})],
        detector="context.missing_field",
    )]


def _check_duplicates(doc: Document) -> list[Finding]:
    groups: dict[str, list[Field]] = {}
    for f in doc.fields:
        groups.setdefault(f.name, []).append(f)
    out: list[Finding] = []
    for name, items in groups.items():
        if len(items) < 2:
            continue
        values = {(f.value_norm or f.value_raw).strip().casefold() for f in items}
        label = name.replace("_", " ")
        if len(values) > 1:
            factor, note = ocr_adjustment(items, items[0].value_raw, items[1].value_raw)
            shown = " / ".join(f"'{f.value_raw}'" for f in items[:4])
            out.append(_finding(
                doc, "context.duplicate_field", f"Conflicting values for {label} on one document",
                f"The document states {label} more than once with different values: {shown}."
                + (f" {note}" if note else ""),
                items[1], items, severity=_downgrade(Severity.medium, factor), confidence=0.85 * factor,
            ))
        elif name in doc.duplicated_fields:
            out.append(_finding(
                doc, "context.duplicate_field", f"{label.capitalize()} appears more than once",
                f"{label.capitalize()} is printed {len(items)} times with the same value.", items[1], items,
                status=FindingStatus.OBSERVATION, severity=Severity.info, confidence=0.8,
            ))
    return out


def verify_within_document(doc: Document, today: date | None = None) -> list[Finding]:
    """All context.* detectors. Each is isolated, so one failure can't lose the others."""
    today = today or date.today()
    fm = field_map(doc)
    findings: list[Finding] = []
    checks = [
        lambda: _check_salary(doc, fm) if doc.doc_type in (DocType.salary_slip, DocType.unknown) else [],
        lambda: _check_balance(doc, fm),
        lambda: _check_dates(doc, fm, today),
        lambda: _check_ids(doc, fm),
        lambda: _check_missing(doc),
        lambda: _check_duplicates(doc),
    ]
    for check in checks:
        try:
            findings.extend(check())
        except Exception as exc:  # noqa: BLE001 - a detector failure must not lose other results
            findings.append(Finding(
                case_id=doc.case_id, status=FindingStatus.OBSERVATION, category=FindingCategory.contextual,
                severity=Severity.info, confidence=1.0, title="A contextual check could not complete",
                doc_id=doc.id, related_doc_ids=[doc.id], detector="context.check_error",
                explanation=f"One within-document check stopped with {type(exc).__name__}; its result "
                            "is absent, not negative.",
            ))
    return findings
