"""Within-document verification: relationships between fields on a single document.

Every check uses extracted values with their confidence. A mismatch that OCR could explain gets a
lower confidence and says so; nothing here treats OCR output as ground truth.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal

from backend.normalize import (
    IFSC_RE,
    MONEY_TOLERANCE,
    PAN_RE,
    date_of,
    fmt_money,
    money_of,
    money_well_formed,
    norm_id,
    ocr_adjustment,
    parse_money,
    parse_period,
    verhoeff_valid,
)
from config.settings import settings
from models.schemas import (
    BBox,
    DocType,
    Document,
    EvidenceItem,
    EvidenceKind,
    Field,
    Finding,
    FindingCategory,
    FindingStatus,
    Severity,
    Table,
    TableCell,
    TextSource,
)
from pipeline.layout import doc_lines

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


# ---- handwriting read two different ways
def _check_handwriting(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    by_id = {f.id: f for f in doc.fields}
    out = []
    for item in (doc.metadata.get("handwriting") or {}).get("disagreements", []):
        field = by_id.get(item["field_id"])
        if field is not None:
            out.append(_finding(
                doc, "ocr.handwriting_disagreement", f"Handwritten {field.name.replace('_', ' ')} was read two ways",
                f"The text reader saw '{item['ocr_read']}' and an AI vision model saw '{item['ai_read']}'. "
                "The first is used for now. Please read it from the document.",
                field, [field], status=FindingStatus.OBSERVATION, severity=Severity.low, confidence=0.5,
            ))
    return out


# ---- figures against the same amount written in words
_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "lakhs": 100000, "lakh": 100000, "lacs": 100000, "lac": 100000,
           "crores": 10000000, "crore": 10000000}
_FILLER = ("rupees", "rupee", "rs", "and", "only", "inr")
_TOKENS = sorted([*_NUMBER_WORDS, *_SCALES, *_FILLER], key=len, reverse=True)


def parse_amount_words(text: str) -> int | None:
    """'Rupees Forty Eight Thousand Three Hundred Twenty Only' -> 48320. Spaces may be missing, as OCR
    often drops them. None unless every part of the text is understood, so a misread can't produce
    a wrong number."""
    rest = re.sub(r"[^a-z]", "", text.casefold())
    total, current, seen = 0, 0, False
    while rest:
        token = next((t for t in _TOKENS if rest.startswith(t)), None)
        if token is None:
            return None
        rest = rest[len(token):]
        if token in _NUMBER_WORDS:
            current += _NUMBER_WORDS[token]
            seen = True
        elif token == "hundred":
            current = max(current, 1) * 100
            seen = True
        elif token in _SCALES:
            total += max(current, 1) * _SCALES[token]
            current, seen = 0, True
    return total + current if seen else None


def _check_amount_in_words(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    net = fm.get("net_pay")
    figure = money_of(net)
    if net is None or figure is None:
        return []
    for page in doc.pages:
        for line in doc_lines(doc, page.index):
            match = re.search(r"inwords:?(.*)$", line.squished)
            if not match:
                continue
            stated = parse_amount_words(match.group(1))
            if stated is None or abs(Decimal(stated) - figure) <= 1:
                return []
            factor, note = ocr_adjustment([net], str(figure), str(stated))
            gross, ded = money_of(fm.get("gross_pay")), money_of(fm.get("total_deductions"))
            agrees = gross is not None and ded is not None and abs(gross - ded - stated) <= 1
            detail = (f" The words agree with gross pay minus deductions ({fmt_money(gross - ded)}), so it is the "
                      "figure that stands apart." if agrees else "")
            return [_finding(
                doc, "context.amount_in_words", "Net pay in figures differs from net pay in words",
                f"Net pay is printed as {fmt_money(figure)} in figures, but as {fmt_money(Decimal(stated))} in words "
                f"on the same document.{detail}" + (f" {note}" if note else ""),
                net, [net], severity=_downgrade(Severity.high, factor), confidence=0.95 * factor,
                extra=[EvidenceItem(
                    kind=EvidenceKind.raw_value, label="Net pay written in words", doc_id=doc.id, page=page.index,
                    bbox=line.bbox, data={"text": line.text, "value_in_words": stated, "value_in_figures": str(figure)},
                )],
            )]
    return []


# ---- salary arithmetic
SUSPECT_OCR_CONFIDENCE = 0.85
LABELS = {"basic_pay": "basic pay", "hra": "HRA", "other_allowances": "other allowances", "gross_pay": "gross pay",
          "total_deductions": "total deductions", "net_pay": "net pay"}


def _label(f: Field) -> str:
    return LABELS.get(f.name, f.name.replace("_", " "))


def _unreadable(fields: list[Field]) -> list[Field]:
    return [f for f in fields if not money_well_formed(f.value_raw)]


def _suspect_operands(fields: list[Field]) -> list[Field]:
    """Complete-looking amounts that could still be misread.

    An OCR reading with low confidence, an amount missing the decimals its neighbours print, or one
    far smaller than the others (under 1% of the largest), which suggests lost digits.
    """
    values = [(f, money_of(f)) for f in fields]
    largest = max((v for _, v in values if v is not None), default=Decimal(0))
    decimal_style = sum("." in f.value_raw for f in fields) >= max(2, len(fields) - 1)
    suspects = []
    for f, value in values:
        from_ocr = f.source not in (TextSource.text_layer, TextSource.llm)
        tiny = value is not None and value > 0 and largest > 0 and value < largest / 100
        style_break = decimal_style and "." not in f.value_raw
        if (from_ocr and f.confidence < SUSPECT_OCR_CONFIDENCE) or tiny or (from_ocr and style_break):
            suspects.append(f)
    return suspects


def _cannot_verify(doc: Document, what: str, involved: list[Field], unreadable: list[Field]) -> Finding:
    shown = ", ".join(f"{_label(f)} read as '{f.value_raw}'" for f in unreadable)
    return _finding(
        doc, "context.arithmetic_salary", f"{what} could not be checked: an amount looks misread",
        f"This check needs complete amounts, but {shown}. That looks like an OCR misread or a reading cut short, "
        "so no conflict is claimed. Read the value from the image.",
        unreadable[0], involved, status=FindingStatus.OBSERVATION, severity=Severity.low, confidence=0.7,
    )


def _sum_conflict(doc: Document, title: str, facts: str, anchor: Field, involved: list[Field], expected: Decimal,
                  stated: Decimal, base: float, severity: Severity,
                  extra: list[EvidenceItem] | None = None) -> Finding:
    factor, note = ocr_adjustment(involved, str(expected), str(stated))
    suspects = _suspect_operands(involved)
    if suspects:
        factor = min(factor, 0.5)
        names = ", ".join(f"{_label(f)} ('{f.value_raw}', confidence {f.confidence:.2f})" for f in suspects)
        note = f"An OCR misread is a possible cause: check {names} against the image first."
    return _finding(
        doc, "context.arithmetic_salary", title, facts + (f" {note}" if note else ""), anchor, involved,
        severity=_downgrade(severity, factor), confidence=base * factor, extra=extra,
    )


def _check_salary(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    out: list[Finding] = []
    net, gross, ded = fm.get("net_pay"), fm.get("gross_pay"), fm.get("total_deductions")
    if net is not None and gross is not None and ded is not None:
        involved = [gross, ded, net]
        unreadable = _unreadable(involved)
        if unreadable:
            out.append(_cannot_verify(doc, "Net pay", involved, unreadable))
        else:
            v_net, v_gross, v_ded = money_of(net), money_of(gross), money_of(ded)
            if v_net is not None and v_gross is not None and v_ded is not None:
                expected = v_gross - v_ded
                if abs(expected - v_net) > MONEY_TOLERANCE:
                    out.append(_sum_conflict(
                        doc, "Net pay does not equal gross pay minus deductions",
                        f"Gross pay {fmt_money(v_gross)} minus total deductions {fmt_money(v_ded)} gives "
                        f"{fmt_money(expected)}, but the document states net pay {fmt_money(v_net)} (difference "
                        f"{fmt_money(abs(expected - v_net))}).",
                        net, involved, expected, v_net, 0.95, Severity.high,
                        extra=[EvidenceItem(kind=EvidenceKind.raw_value, label="Recomputed net pay", doc_id=doc.id,
                                            data={"expected": str(expected), "stated": str(v_net),
                                                  "difference": str(abs(expected - v_net))})],
                    ))

    components = [fm[n] for n in ("basic_pay", "hra", "other_allowances") if n in fm]
    if gross is not None and len(components) >= 2 and "other_allowances" in fm:
        involved = components + [gross]
        unreadable = _unreadable(involved)
        if unreadable:
            out.append(_cannot_verify(doc, "Gross pay", involved, unreadable))
        else:
            values = [money_of(f) for f in components]
            v_gross = money_of(gross)
            if v_gross is not None and all(v is not None for v in values):
                total = sum(values, Decimal(0))  # type: ignore[arg-type]
                if abs(total - v_gross) > MONEY_TOLERANCE:
                    out.append(_sum_conflict(
                        doc, "Gross pay does not equal the sum of its components",
                        f"Listed earnings sum to {fmt_money(total)}, but gross pay is stated as {fmt_money(v_gross)}.",
                        gross, involved, total, v_gross, 0.9, Severity.medium,
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


def repair_transaction_row(row: list[TableCell], desc_col: int | None, bal_col: int | None) -> None:
    """Moves a balance that OCR word-splitting left at the end of the description cell.

    '...HOUSE OWNER 1,23,380.' + '25' is one printed balance read across a column edge. Only the
    assignment changes; no digit is added or altered.
    """
    if desc_col is None or bal_col is None or max(desc_col, bal_col) >= len(row):
        return
    desc, bal = row[desc_col], row[bal_col]
    split = re.match(r"^(.*\S)\s+(\d[\d,]*\.)$", desc.text.strip())
    if split and re.fullmatch(r"\d{1,2}", bal.text.strip()):
        bal.text, desc.text = split.group(2) + bal.text.strip(), split.group(1)
        return
    whole = re.match(r"^(.*\S)\s+(\d[\d,]*\.\d{2})$", desc.text.strip())
    if whole and not bal.text.strip():
        bal.text, desc.text = whole.group(2), whole.group(1)


def _txn_table(doc: Document) -> Table | None:
    table = next((t for t in doc.tables if t.name == "transactions" and t.rows), None)
    if table is not None:
        desc_col, bal_col = _column(table, "desc"), _column(table, "balance")
        for row in table.rows:
            repair_transaction_row(row, desc_col, bal_col)
    return table


_DATE_TOKEN = re.compile(r"^\d{1,2}[-/][A-Za-z0-9]{3}[-/]\d{2,4}$|^\d{1,2}[-/]\d{1,2}[-/]\d{2,4}$")


def rows_not_extracted(doc: Document, table: Table) -> int:
    """Date-shaped words at or below the table's first row, minus the rows extracted.

    If rows are missing, a broken running balance may be our extraction rather than the document.
    """
    if not table.rows or table.page >= len(doc.pages):
        return 0
    first = next((c.bbox for c in table.rows[0] if c.bbox), None)
    if first is None:
        return 0
    words = doc.pages[table.page].words
    dates = [w for w in words if _DATE_TOKEN.match(w.text.strip()) and w.bbox.y1 >= first.y0]
    return max(0, len(dates) - len(table.rows))


def _check_balance(doc: Document, fm: dict[str, Field]) -> list[Finding]:
    table = _txn_table(doc)
    if table is None:
        return []
    missing_rows = rows_not_extracted(doc, table)
    coverage_note = (
        f" {missing_rows} row(s) visible on the page were not extracted, so the break may come from "
        "the extraction and not the document. Check the image." if missing_rows else "")
    coverage_factor = 0.5 if missing_rows else 1.0
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
                if factor <= 0.5 else "") + coverage_note
        factor *= coverage_factor
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
            None, [], severity=Severity.low if missing_rows else _downgrade(Severity.high, factor),
            confidence=0.93 * factor,
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
                f"is {fmt_money(v_closing)}." + (f" {note}" if note else "") + coverage_note,
                closing, [closing],  # type: ignore[list-item]
                severity=Severity.low if missing_rows else _downgrade(Severity.medium, factor),
                confidence=0.9 * factor * coverage_factor,
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
    period = (parse_period(period_f.value_raw) or parse_period(period_f.value_norm)) if period_f else None
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
    statement = (parse_period(st_f.value_raw) or parse_period(st_f.value_norm)) if st_f else None
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


def _comparable(f: Field) -> str:
    money = money_of(f) if f.value_type.value in ("money", "number") else None
    return str(money) if money is not None else (f.value_norm or f.value_raw).strip().casefold()


def _check_duplicates(doc: Document) -> list[Finding]:
    groups: dict[str, list[Field]] = {}
    for f in doc.fields:
        groups.setdefault(f.name, []).append(f)
    out: list[Finding] = []
    for name, items in groups.items():
        if len(items) < 2:
            continue
        values = {_comparable(f) for f in items}
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
    return out


def verify_within_document(doc: Document, today: date | None = None) -> list[Finding]:
    """All context.* detectors. Each is isolated, so one failure can't lose the others."""
    today = today or date.today()
    fm = field_map(doc)
    findings: list[Finding] = []
    checks = [
        lambda: _check_salary(doc, fm) if doc.doc_type in (DocType.salary_slip, DocType.unknown) else [],
        lambda: _check_amount_in_words(doc, fm),
        lambda: _check_handwriting(doc, fm),
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
