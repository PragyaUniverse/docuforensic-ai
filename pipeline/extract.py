"""Layout-based extraction: printed labels to values, with boxes taken from word geometry.

Handled layouts: "Label: value", label and value in columns, value below its label, several
label/value pairs on a row, multi-line addresses, narrative declarations, and tables.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from models.schemas import (
    BBox,
    Document,
    DocType,
    Field,
    Table,
    TableCell,
    TextSource,
    ValueType,
)
from pipeline.common import is_processable, log, union_bbox
from pipeline.layout import Line, doc_lines, squish
from pipeline.normalize import (
    looks_like_date,
    norm_address,
    norm_date,
    norm_id,
    norm_money,
    norm_name,
    norm_number,
    norm_period,
)

S = ValueType.string
N = ValueType.name
D = ValueType.date
M = ValueType.money
I = ValueType.id_number
A = ValueType.address
C = ValueType.account_number

COMMON_LABELS: dict[str, tuple[ValueType, list[str]]] = {
    "person_name": (N, [
        "name of the applicant", "name of applicant", "applicant's name", "applicant name",
        "full name", "name of employee", "employee name", "account holder name", "account holder",
        "name of consumer", "consumer name", "customer name", "name of declarant", "declarant name",
        "holder name", "billed to", "name",
    ]),
    "date_of_birth": (D, ["date of birth", "birth date", "d.o.b.", "d.o.b", "dob"]),
    "gender": (S, ["gender", "sex"]),
    "address": (A, [
        "residential address", "permanent address", "current address", "correspondence address",
        "service address", "billing address", "supply address", "registered address", "address",
    ]),
    "phone": (S, ["mobile number", "mobile no", "phone number", "phone no", "contact number", "contact no", "mobile", "phone"]),
    "email": (S, ["email address", "e-mail address", "email id", "e-mail", "email"]),
    "id_number": (I, ["aadhaar number", "aadhaar no", "aadhar number", "aadhar no", "national id number", "national id", "id number", "id no", "aadhaar", "uid"]),
    "pan_number": (I, ["pan number", "pan no", "permanent account number", "permanent account no", "pan"]),
    "employer_name": (S, ["name of employer", "employer name", "current employer", "company name", "organisation", "organization", "employer", "company"]),
    "designation": (S, ["designation", "job title"]),
    "declared_monthly_income": (M, ["declared monthly income", "gross monthly income", "net monthly income", "monthly income", "monthly salary"]),
    "loan_amount": (M, ["loan amount requested", "requested loan amount", "loan amount", "amount requested"]),
    "bank_account_number": (C, ["bank account number", "bank account no", "bank a/c number", "bank a/c no", "salary account number", "salary account no", "salary a/c number", "salary a/c no", "account number", "account no", "a/c number", "a/c no", "acct no"]),
    "application_id": (S, ["application id", "application number", "application no", "application ref", "reference number", "ref no"]),
    "application_date": (D, ["application date", "date of application"]),
    "employee_id": (S, ["employee id", "employee no", "employee code", "emp id", "emp code", "emp no"]),
    "pay_period": (S, ["pay period", "salary for the month of", "salary for the month", "for the month of", "salary month", "pay month"]),
    "basic_pay": (M, ["basic pay", "basic salary", "basic"]),
    "hra": (M, ["house rent allowance", "hra"]),
    "other_allowances": (M, ["other allowances", "other allowance", "special allowance", "allowances"]),
    "gross_pay": (M, ["gross pay", "gross salary", "gross earnings", "total earnings"]),
    "total_deductions": (M, ["total deductions", "total deduction", "deductions total"]),
    "net_pay": (M, ["net salary payable", "net amount payable", "net pay", "net salary", "take home pay", "take home", "net payable"]),
    "date_of_joining": (D, ["date of joining", "joining date", "doj"]),
    "bank_name": (S, ["name of bank", "bank name", "bank"]),
    "tenure": (S, ["tenure"]),
    "due_date": (D, ["due date"]),
    "billing_period": (S, ["billing period"]),
    "ifsc": (I, ["ifsc code", "ifsc"]),
    "statement_period": (S, ["statement period", "statement for the period", "period"]),
    "opening_balance": (M, ["opening balance", "balance brought forward"]),
    "closing_balance": (M, ["closing balance", "balance carried forward"]),
    "issuer_name": (S, ["issued by", "service provider", "utility provider", "issuer", "provider"]),
    "consumer_number": (S, ["consumer number", "consumer no", "service number", "customer id", "ca number"]),
    "bill_date": (D, ["date of bill", "bill date", "invoice date", "issue date"]),
    "amount_due": (M, ["total amount due", "amount due", "amount payable", "total payable", "bill amount"]),
    "declaration_date": (D, ["declaration date", "date of declaration"]),
    "place": (S, ["place"]),
    "document_date": (D, ["date of issue", "issue date", "document date"]),
    "id_type": (S, ["id type", "document type", "type of id"]),
    # Generic "Date:" resolves to a per-document field, set in DATE_FIELD.
    "_date": (D, ["date"]),
}

FIELDS_BY_TYPE: dict[DocType, list[str]] = {
    DocType.application_form: [
        "application_id", "person_name", "date_of_birth", "gender", "address", "phone", "email",
        "id_number", "pan_number", "employer_name", "designation", "declared_monthly_income",
        "loan_amount", "bank_account_number", "application_date", "date_of_joining", "ifsc", "place", "tenure", "_date",
    ],
    DocType.id_proof: ["id_type", "id_number", "pan_number", "person_name", "date_of_birth", "gender", "address", "document_date"],
    DocType.salary_slip: [
        "person_name", "employee_id", "employer_name", "designation", "pay_period", "pan_number",
        "bank_account_number", "basic_pay", "hra", "other_allowances", "gross_pay",
        "total_deductions", "net_pay", "date_of_joining", "date_of_birth", "document_date",
    ],
    DocType.bank_statement: [
        "person_name", "address", "bank_name", "bank_account_number", "ifsc", "statement_period",
        "opening_balance", "closing_balance", "date_of_birth", "document_date",
    ],
    DocType.address_proof: ["person_name", "address", "issuer_name", "consumer_number", "bill_date", "amount_due", "due_date", "billing_period", "document_date", "_date"],
    DocType.declaration: [
        "person_name", "date_of_birth", "address", "employer_name", "declared_monthly_income",
        "declaration_date", "place", "_date", "document_date",
    ],
    DocType.unknown: ["person_name", "date_of_birth", "address", "document_date", "_date"],
}

DATE_FIELD = {
    DocType.application_form: "application_date",
    DocType.address_proof: "bill_date",
    DocType.declaration: "declaration_date",
    DocType.unknown: "document_date",
}

# Weak labels are accepted only with a colon or a clear column gap.
PAN_RE = re.compile(r"[A-Z]{5}\d{4}[A-Z]")
AADHAAR_RE = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
IFSC_RE = re.compile(r"[A-Z]{4}0[A-Z0-9]{6}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
MONEY_RE = re.compile(r"(?:(?:rs\.?|inr|₹)\s*)?\d[\d,]*(?:\.\d{1,2})?(?:/-)?", re.I)
DATE_RE = re.compile(
    r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2,4}|\d{1,2}(?:st|nd|rd|th)?[\s\-]*[A-Za-z]{3,9}[\s\-,]*\d{2,4}"
)


@dataclass
class LabelHit:
    start: int
    end: int
    name: str
    vtype: ValueType
    synonym: str


def _label_table(doc_type: DocType) -> list[tuple[str, str, ValueType, str]]:
    names = FIELDS_BY_TYPE.get(doc_type, FIELDS_BY_TYPE[DocType.unknown])
    out = []
    for name in names:
        vtype, synonyms = COMMON_LABELS[name]
        for syn in synonyms:
            out.append((squish(syn), name, vtype, syn))
    # Foreign labels are matched too so they bound a neighbouring value, but never emit a field.
    for name, (vtype, synonyms) in COMMON_LABELS.items():
        if name not in names:
            for syn in synonyms:
                out.append((squish(syn), f"!{name}", vtype, syn))
    out.sort(key=lambda t: len(t[0]), reverse=True)
    return out


def _find_labels(line: Line, table) -> list[LabelHit]:
    s = line.squished
    taken = [False] * len(s)
    hits: list[LabelHit] = []
    for key, name, vtype, syn in table:
        start = 0
        while True:
            i = s.find(key, start)
            if i < 0:
                break
            start = i + 1
            end = i + len(key)
            if any(taken[i:end]):
                continue
            if not _boundary_ok(line, i, end):
                continue
            if not _accept_position(line, i, end):
                continue
            for k in range(i, end):
                taken[k] = True
            hits.append(LabelHit(i, end, name, vtype, syn))
    hits.sort(key=lambda h: h.start)
    return hits


def _boundary_ok(line: Line, i: int, end: int) -> bool:
    chars = line.chars
    # Must start at a word start or after punctuation.
    if i > 0 and chars[i].frac0 > 0 and chars[i - 1].ch.isalnum():
        # Mid-word start is fine only for long labels, where OCR lost the space.
        if end - i < 9:
            return False
    if end < len(chars):
        nxt = chars[end].ch
        same_word = chars[end].word_index == chars[end - 1].word_index
        if same_word and nxt.isalpha():
            return False
    return True


def _accept_position(line: Line, i: int, end: int) -> bool:
    """Reject label words used inside prose. A label closes with a colon or a column gap, or ends
    the row, and it opens a row or a column unless a colon makes its role unambiguous."""
    chars = line.chars
    closes_with_colon = _colon_follows(line, end)
    if i > 0 and not closes_with_colon:
        gap_before = line.span_bbox(i, i + 1).x0 - line.span_bbox(i - 1, i).x1
        if gap_before < 0.7 * line.height and chars[i - 1].ch not in ":;|":
            return False
    if end >= len(chars) or closes_with_colon:
        return True
    gap_after = line.span_bbox(end, end + 1).x0 - line.span_bbox(end - 1, end).x1
    return gap_after >= 0.7 * line.height


def _colon_follows(line: Line, end: int) -> bool:
    """A colon right after the label, allowing 'No.' and '(Rs.)' style tails."""
    tail = "".join(c.ch for c in line.chars[end : end + 9])
    return bool(re.match(r"\.?(\((rs|inr|₹)\.?\))?\.?[:：=]", tail, re.I))


def _value_span(line: Line, hit: LabelHit, next_start: int) -> tuple[int, int]:
    """Value characters to the right of a label, up to the next label or a wide gap."""
    i = hit.end
    tail = "".join(c.ch for c in line.chars[i : i + 9])
    m = re.match(r"\.?(\((rs|inr|₹)\.?\))?", tail, re.I)
    if m:
        i += len(m.group(0))
    while i < next_start and line.chars[i].ch in ":：-–=.|":
        i += 1
    j = i
    limit = 2.6 * line.height
    while j < next_start:
        if j > i:
            prev = line.span_bbox(j - 1, j)
            cur = line.span_bbox(j, j + 1)
            if cur.x0 - prev.x1 > limit:
                break
        j += 1
    return i, j


def _fit_value(raw: str, vtype: ValueType, name: str) -> tuple[int, int] | None:
    """Locate the actual value inside the raw span as non-space character offsets, or None."""
    squished = re.sub(r"\s+", "", raw)

    def spaced(m: re.Match) -> tuple[int, int]:
        return _map_raw_span(raw, (m.start(), m.end()))

    def whole() -> tuple[int, int]:
        return 0, len(squished)

    if vtype == M:
        m = MONEY_RE.search(raw)
        return spaced(m) if m and norm_money(m.group(0)) else None
    if vtype == D:
        m = DATE_RE.search(raw)
        return spaced(m) if m and norm_date(m.group(0)) else None
    if name in ("pan_number", "ifsc"):
        m = (PAN_RE if name == "pan_number" else IFSC_RE).search(squished.upper())
        if m:
            return m.start(), m.end()
        if name == "pan_number":
            for i in range(0, max(len(squished) - 9, 0)):
                if repair_pan(squished[i : i + 10]):
                    return i, i + 10
        return None
    if name == "email":
        m = EMAIL_RE.search(squished)
        return (m.start(), m.end()) if m else None
    if name == "id_number":
        return whole() if sum(c.isdigit() for c in raw) >= 8 else None
    if vtype == C:
        return whole() if sum(c.isdigit() for c in raw) >= 6 else None
    if vtype == N:
        return whole() if sum(c.isalpha() for c in raw) >= 2 else None
    if name == "phone":
        return whole() if sum(c.isdigit() for c in raw) >= 8 else None
    if name == "gender":
        return whole() if re.search(r"(?i)\b(male|female|other|m|f)\b", raw) else None
    return whole() if any(c.isalnum() for c in raw) else None


def _normalize(name: str, vtype: ValueType, raw: str) -> str | None:
    if vtype == M:
        return norm_money(raw)
    if vtype == D:
        return norm_date(raw)
    if name in ("pay_period", "statement_period"):
        return norm_period(raw)
    if vtype == N:
        return norm_name(raw)
    if vtype == A:
        return norm_address(raw)
    if vtype in (I, C):
        return norm_id(raw)
    if name in ("employer_name", "bank_name", "issuer_name", "designation", "place"):
        return norm_name(raw)
    if name == "phone":
        return re.sub(r"\D", "", raw)
    if name == "gender":
        m = re.search(r"(?i)\b(male|female|other|m|f)\b", raw)
        return {"m": "male", "f": "female"}.get(m.group(1).lower(), m.group(1).lower()) if m else None
    if name == "email":
        return raw.replace(" ", "").casefold()
    if vtype == ValueType.number:
        return norm_number(raw)
    return re.sub(r"\s+", " ", raw).strip()


def _map_raw_span(raw: str, fit: tuple[int, int]) -> tuple[int, int]:
    """Convert a range in the spaced raw string into counts of non-space characters."""
    a = sum(1 for c in raw[: fit[0]] if not c.isspace())
    b = sum(1 for c in raw[: fit[1]] if not c.isspace())
    return a, b


def repair_pan(token: str) -> str | None:
    """PAN format is five letters, four digits, one letter, so OCR's letter/digit mix-ups in a
    given position have a single valid reading. Returns None if the token can't be a PAN."""
    t = re.sub(r"\s+", "", token).upper()
    if len(t) != 10 or not t.isalnum():
        return None
    to_letter = str.maketrans({"0": "O", "1": "I", "5": "S", "8": "B", "2": "Z"})
    to_digit = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})
    fixed = t[:5].translate(to_letter) + t[5:9].translate(to_digit) + t[9].translate(to_letter)
    return fixed if PAN_RE.fullmatch(fixed) else None


def _repair_name(raw: str) -> str:
    """OCR often reads a capital I as lowercase l at the start of a name ('lyer' for 'Iyer')."""
    return re.sub(r"\bl(?=[a-z])", "I", raw)


class _Extractor:
    def __init__(self, doc: Document):
        self.doc = doc
        self.table = _label_table(doc.doc_type)
        self.date_field = DATE_FIELD.get(doc.doc_type)
        self.fields: list[Field] = []

    def _emit(
        self, name: str, vtype: ValueType, label: str | None, raw: str, bbox: BBox, conf: float,
        page: int, source: TextSource,
    ) -> Field | None:
        raw = raw.strip(" :-–|")
        if not raw:
            return None
        if vtype == N or name == "employer_name":
            raw = _repair_name(raw)
        if name == "pan_number":
            raw = repair_pan(raw) or raw
        field = Field(
            doc_id=self.doc.id,
            name=name,
            label_raw=label,
            value_raw=raw,
            value_norm=_normalize(name, vtype, raw),
            value_type=vtype,
            confidence=round(float(conf), 3),
            page=page,
            bbox=bbox,
            source=source,
        )
        self.fields.append(field)
        return field

    def _below(self, lines: list[Line], idx: int, hit_box: BBox, x_limit: float) -> tuple[Line, int, int] | None:
        """Value directly under its label."""
        cur = lines[idx]
        for nxt in lines[idx + 1 : idx + 3]:
            if nxt.y - cur.y > 2.6 * cur.height:
                return None
            for i, c in enumerate(nxt.chars):
                b = nxt.span_bbox(i, i + 1)
                if b.x0 >= hit_box.x0 - cur.height and b.x0 <= hit_box.x1:
                    j = i
                    while j < len(nxt.chars):
                        cb = nxt.span_bbox(j, j + 1)
                        if cb.x0 > x_limit:
                            break
                        if j > i and cb.x0 - nxt.span_bbox(j - 1, j).x1 > 2.2 * nxt.height:
                            break
                        j += 1
                    return nxt, i, j
                if b.x0 > hit_box.x1:
                    break
        return None

    def _continue_address(self, lines: list[Line], idx: int, x0: float, x_limit: float, first_box: BBox) -> list[tuple[Line, int, int]]:
        """Further address lines: same left edge, no label of their own, right below."""
        parts: list[tuple[Line, int, int]] = []
        prev_y = lines[idx].y
        h = lines[idx].height
        for k in range(idx + 1, min(idx + 4, len(lines))):
            ln = lines[k]
            if ln.y - prev_y > 2.8 * h:
                break
            chars = [i for i in range(len(ln.chars)) if x0 - 1.2 * h <= ln.span_bbox(i, i + 1).x0 < x_limit]
            if not chars:
                break
            # Anything printed left of the value column means this row starts a new label.
            if chars[0] > 0:
                break
            a, b = chars[0], chars[-1] + 1
            if abs(ln.span_bbox(a, a + 1).x0 - x0) > 1.5 * h:
                break
            segment = ln.squished[a:b]
            if any(segment.startswith(key) or (key in segment and len(key) >= 5) for key, *_ in self.table):
                break
            if ":" in segment:
                break
            parts.append((ln, a, b))
            prev_y = ln.y
        return parts

    def run_page(self, page_index: int) -> None:
        lines = doc_lines(self.doc, page_index)
        page = self.doc.pages[page_index]
        for idx, line in enumerate(lines):
            hits = _find_labels(line, self.table)
            for hi, hit in enumerate(hits):
                name = hit.name
                if name == "_date":
                    name = self.date_field or "document_date"
                if name.startswith("!"):
                    continue
                next_start = hits[hi + 1].start if hi + 1 < len(hits) else len(line.chars)
                start, end = _value_span(line, hit, next_start)
                label_box = line.span_bbox(hit.start, hit.end)
                x_limit = float(page.width)
                if hi + 1 < len(hits):
                    x_limit = line.span_bbox(hits[hi + 1].start, hits[hi + 1].start + 1).x0
                value_line, a, b = line, start, end
                quality = 1.0
                used_below = False
                raw = line.span_text(a, b) if b > a else ""
                fit = _fit_value(raw, hit.vtype, name) if raw else None
                if fit is None:
                    below = self._below(lines, idx, label_box, x_limit)
                    if below is None:
                        continue
                    value_line, a, b = below
                    raw = value_line.span_text(a, b)
                    fit = _fit_value(raw, hit.vtype, name)
                    if fit is None:
                        continue
                    quality = 0.9
                    used_below = True
                a2, b2 = a + fit[0], a + fit[1]
                raw_value = value_line.span_text(a2, b2)
                bbox = value_line.span_bbox(a2, b2)
                conf = value_line.span_conf(a2, b2) * quality
                source = value_line.words[value_line.chars[a2].word_index].source
                if hit.vtype == A:
                    extras = self._continue_address(
                        lines, lines.index(value_line), bbox.x0, x_limit, bbox
                    )
                    for ln, ea, eb in extras:
                        raw_value += ", " + ln.span_text(ea, eb) if not raw_value.endswith(",") else " " + ln.span_text(ea, eb)
                        bbox = union_bbox([bbox, ln.span_bbox(ea, eb)])
                        conf = min(conf, ln.span_conf(ea, eb))
                _ = used_below
                self._emit(name, hit.vtype, hit.synonym, raw_value, bbox, conf, page_index, source)

    def fallbacks(self) -> None:
        """Values printed without a label, located by format or position."""
        have = {f.name for f in self.fields}
        for page in self.doc.pages:
            lines = doc_lines(self.doc, page.index)
            if not lines:
                continue
            for line in lines:
                raw = line.text.upper()
                if "pan_number" not in have and self._wants("pan_number"):
                    m = PAN_RE.search(line.squished.upper())
                    if m:
                        self._emit_regex("pan_number", I, line, m.start(), m.end(), page.index)
                        have.add("pan_number")
                if "ifsc" not in have and self._wants("ifsc"):
                    m = IFSC_RE.search(line.squished.upper())
                    if m:
                        self._emit_regex("ifsc", I, line, m.start(), m.end(), page.index)
                        have.add("ifsc")
                if "id_number" not in have and self._wants("id_number"):
                    m = re.search(r"\d{12}", re.sub(r"[^\d]", "#", line.squished).replace("#", "x"))
                    m2 = AADHAAR_RE.search(raw)
                    if m2 and not re.search(r"\d", raw[m2.end() : m2.end() + 1] or " "):
                        digits = re.sub(r"\D", "", m2.group(0))
                        pos = line.squished.find(digits)
                        if pos >= 0:
                            self._emit_regex("id_number", I, line, pos, pos + len(digits), page.index)
                            have.add("id_number")
                    _ = m
                if "email" not in have and self._wants("email"):
                    m = EMAIL_RE.search(line.squished)
                    if m:
                        self._emit_regex("email", S, line, m.start(), m.end(), page.index)
                        have.add("email")

        dtype = self.doc.doc_type
        first_lines = doc_lines(self.doc, 0)
        if dtype == DocType.id_proof:
            self._id_proof_fallbacks(first_lines, have)
        if dtype == DocType.salary_slip and "employer_name" not in have:
            self._header_org("employer_name", first_lines, r"(pvt|ltd|limited|llp|inc|corp|technolog|solutions|industries|systems|tools|services)")
        if dtype == DocType.bank_statement and "bank_name" not in have:
            self._header_org("bank_name", first_lines, r"\bbank\b")
        if dtype == DocType.address_proof and "issuer_name" not in have:
            self._header_org("issuer_name", first_lines)
        if dtype == DocType.declaration:
            self._declaration_prose(have)

    def _wants(self, name: str) -> bool:
        return name in FIELDS_BY_TYPE.get(self.doc.doc_type, [])

    def _emit_regex(self, name, vtype, line: Line, a: int, b: int, page: int, quality: float = 0.8):
        return self._emit(
            name, vtype, None, line.span_text(a, b), line.span_bbox(a, b),
            line.span_conf(a, b) * quality, page, line.words[line.chars[a].word_index].source,
        )

    def _header_org(self, name: str, lines: list[Line], pattern: str | None = None) -> None:
        """The organisation name printed at the top: its row's first chunk, in the tallest type."""
        chunks: list[tuple[Line, int, int]] = []
        for line in lines[:8]:
            if re.search(r"(?i)specimen|synthetic|fictional|not a real", line.text):
                continue
            end = len(line.chars)
            for j in range(1, len(line.chars)):
                if line.span_bbox(j, j + 1).x0 - line.span_bbox(j - 1, j).x1 > 2.5 * line.height:
                    end = j
                    break
            chunks.append((line, 0, end))
        chunks = [c for c in chunks if sum(ch.ch.isalpha() for ch in c[0].chars[c[1] : c[2]]) >= 4
                  and not re.search(r"(?i)statement|slip|bill\b|application|declaration", c[0].span_text(c[1], c[2]))]
        if pattern:
            matching = [c for c in chunks if re.search(pattern, c[0].span_text(c[1], c[2]), re.I)]
            chunks = matching or chunks
        if chunks:
            line, a, b = max(chunks, key=lambda c: c[0].height)
            self._emit_regex(name, S, line, a, b, line.page, quality=0.75)

    def _id_proof_fallbacks(self, lines: list[Line], have: set[str]) -> None:
        if "id_type" not in have:
            pattern = re.compile(r"(aadhaar|aadhar|pan|voter|passport|national)[-\s]*(style|format|id|card)?", re.I)
            for line in lines:
                if not any(k in line.squished for k in ("aadhaar", "aadhar", "permanentaccountnumber", "nationalid", "voter", "passport", "pan-style", "panstyle", "pan-format")):
                    continue
                m = pattern.search(line.squished)
                if m:
                    self._emit_regex("id_type", S, line, m.start(), m.end(), 0, quality=0.8)
                    break
        if "person_name" not in have:
            # On ID cards the name often sits unlabelled directly above the date of birth.
            dob = next((f for f in self.fields if f.name == "date_of_birth"), None)
            if dob:
                for k, line in enumerate(lines):
                    if line.bbox.y0 <= dob.bbox.y0 <= line.bbox.y1 and k > 0:
                        prev = lines[k - 1]
                        if re.fullmatch(r"[A-Za-z .'-]{3,}", prev.text):
                            self._emit_regex("person_name", N, prev, 0, len(prev.chars), 0, quality=0.7)
                        break

    def _declaration_prose(self, have: set[str]) -> None:
        """Narrative declarations: 'I, X, residing at Y, employed with Z ...'."""
        all_lines = [ln for p in self.doc.pages for ln in doc_lines(self.doc, p.index)]
        # Build one searchable stream over the running text with a map back to line positions.
        stream = ""
        index: list[tuple[int, int]] = []
        for li, ln in enumerate(all_lines):
            pieces = ln.span_text(0, len(ln.chars))
            nonspace = 0
            for ch in pieces:
                stream += ch
                if ch.isspace():
                    index.append((li, nonspace))
                else:
                    index.append((li, nonspace))
                    nonspace += 1
            stream += " "
            index.append((li, nonspace))

        patterns = [
            ("person_name", N, r"\bI,?\s+(?:Mr\.?\s+|Ms\.?\s+|Mrs\.?\s+|Shri\s+|Smt\.?\s+)?([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){0,4})\s*,?\s*(?:son|daughter|wife|aged|born|residing|resident|employed|working|hereby|do\s)"),
            ("date_of_birth", D, r"(?:born\s+on|date\s+of\s+birth(?:\s+is)?|dob)[:\s]+(" + DATE_RE.pattern + r")"),
            ("address", A, r"(?:residing\s+at|resident\s+of|living\s+at|my\s+address\s+is)[:\s]+(.+?)(?:,?\s+(?:do\s+hereby|hereby|and\s+(?:am|that)|am\s+employed|employed|working)|\.\s|$)"),
            ("employer_name", S, r"(?:employed\s+(?:with|by|at)|working\s+(?:with|at|for)|employee\s+of)\s+([A-Z][\w&.' -]+?)(?:\s+as\b|\s+since\b|,|\.\s|\s+and\b)"),
            ("declared_monthly_income", M, r"(?:monthly\s+(?:income|salary)[\w\s]*?(?:is|of|:)\s*(?:approximately\s+)?)((?:Rs\.?\s*|INR\s*|₹\s*)?\d[\d,]*(?:\.\d{1,2})?)"),
        ]
        have_names = {f.name for f in self.fields}
        for name, vtype, pattern in patterns:
            if name in have_names:
                continue
            m = re.search(pattern, stream, flags=re.S)
            if not m:
                continue
            s, e = m.start(1), m.end(1)
            raw = stream[s:e].strip(" ,.")
            if not raw:
                continue
            start_li, start_c = index[s]
            end_li, end_c = index[max(e - 1, s)]
            boxes = []
            confs = []
            source = all_lines[start_li].words[0].source
            for li in range(start_li, end_li + 1):
                ln = all_lines[li]
                a = start_c if li == start_li else 0
                b = (end_c + 1) if li == end_li else len(ln.chars)
                b = min(b, len(ln.chars))
                if b > a:
                    boxes.append(ln.span_bbox(a, b))
                    confs.append(ln.span_conf(a, b))
            if boxes:
                self._emit(name, vtype, None, raw, union_bbox(boxes), min(confs) * 0.8, all_lines[start_li].page, source)


def _token_is_numeric(text: str) -> bool:
    t = text.strip().replace(",", "").replace("₹", "")
    t = re.sub(r"^(rs\.?|inr)", "", t, flags=re.I)
    t = t.replace("/-", "")
    return bool(re.fullmatch(r"-?\d+(\.\d+)?", t)) or t in ("-", "--", "—")


def _extract_transactions(doc: Document) -> list[Table]:
    tables: list[Table] = []
    current: Table | None = None
    columns: list[tuple[str, float, float]] = []
    for page in doc.pages:
        lines = doc_lines(doc, page.index)
        idx = 0
        while idx < len(lines):
            line = lines[idx]
            s = line.squished
            is_header = "date" in s and "balance" in s and ("debit" in s or "withdrawal" in s) and ("credit" in s or "deposit" in s)
            if is_header:
                cols = _header_columns(line)
                if cols:
                    columns = cols
                    if current is None:
                        current = Table(
                            doc_id=doc.id, name="transactions", page=page.index,
                            headers=["date", "description", "debit", "credit", "balance"],
                        )
                        tables.append(current)
                idx += 1
                continue
            if current is not None and columns:
                row = _transaction_row(line, columns)
                if row is not None:
                    current.rows.append(row)
                    box = line.bbox
                    current.bbox = union_bbox([current.bbox, box]) if current.bbox else box
                elif current.rows and re.search(r"(?i)closing|total|end of|summary", line.text):
                    columns = []
            idx += 1
    return tables


def _header_columns(line: Line) -> list[tuple[str, float, float]]:
    """(canonical, x0, x1) per column, from a header row that may have lost spaces."""
    aliases = {
        "date": ["transactiondate", "txndate", "valuedate", "date"],
        "description": ["description", "particulars", "narration", "details"],
        "debit": ["withdrawal", "debit"],
        "credit": ["deposit", "credit"],
        "balance": ["balance"],
    }
    out = []
    s = line.squished
    for canon, keys in aliases.items():
        for key in keys:
            i = s.find(key)
            if i >= 0:
                b = line.span_bbox(i, i + len(key))
                out.append((canon, b.x0, b.x1))
                break
    out.sort(key=lambda c: c[1])
    return out if len(out) >= 4 else []


def _transaction_row(line: Line, columns: list[tuple[str, float, float]]) -> list[TableCell] | None:
    if not line.words:
        return None
    first = line.text[:14]
    m = DATE_RE.match(first.strip())
    if not m or not looks_like_date(m.group(0)):
        return None
    cells: dict[str, list] = {c[0]: [] for c in columns}
    numeric_cols = [c for c in columns if c[0] in ("debit", "credit", "balance")]
    desc_col = next((c for c in columns if c[0] == "description"), None)
    date_col = next((c for c in columns if c[0] == "date"), None)
    for w in line.words:
        cx = (w.bbox.x0 + w.bbox.x1) / 2
        if _token_is_numeric(w.text) and numeric_cols and (not desc_col or cx > desc_col[1] + 0.5 * (numeric_cols[0][1] - desc_col[1])):
            target = min(numeric_cols, key=lambda c: min(abs(w.bbox.x1 - c[2]), abs(cx - (c[1] + c[2]) / 2)))
            cells[target[0]].append(w)
        elif date_col and w.bbox.x0 < (desc_col[1] if desc_col else date_col[2]) - 2:
            cells["date"].append(w)
        elif desc_col:
            cells["description"].append(w)
    row: list[TableCell] = []
    for canon in ("date", "description", "debit", "credit", "balance"):
        ws = cells.get(canon) or []
        if ws:
            ws.sort(key=lambda w: w.bbox.x0)
            row.append(
                TableCell(
                    text=" ".join(w.text for w in ws),
                    confidence=round(min(w.confidence for w in ws), 3),
                    bbox=union_bbox([w.bbox for w in ws]),
                )
            )
        else:
            row.append(TableCell(text="", confidence=0.0, bbox=None))
    if not row[0].text or not any(row[i].text for i in (2, 3, 4)):
        return None
    return row


def _extract_pay_tables(doc: Document) -> list[Table]:
    """Earnings and deductions: rows of 'component ... amount', in one or two columns."""
    tables: list[Table] = []
    for page in doc.pages:
        lines = doc_lines(doc, page.index)
        earn_x: tuple[float, float] | None = None
        ded_x: tuple[float, float] | None = None
        earn: Table | None = None
        ded: Table | None = None
        started = False
        for line in lines:
            s = line.squished
            e_i = s.find("earnings")
            d_i = s.find("deductions")
            is_total = bool(re.search(r"(?i)^(total|gross|net|take)", s))
            is_heading = (e_i >= 0 or d_i >= 0) and not re.search(r"\d", s) and "total" not in s and "gross" not in s
            if is_heading:
                if e_i >= 0:
                    earn_x = (line.span_bbox(e_i, e_i + 8).x0, float(page.width))
                    earn = earn or Table(doc_id=doc.id, name="earnings", page=page.index, headers=["component", "amount"])
                    started = True
                if d_i >= 0:
                    ded_x = (line.span_bbox(d_i, d_i + 10).x0, float(page.width))
                    ded = ded or Table(doc_id=doc.id, name="deductions", page=page.index, headers=["component", "amount"])
                    started = True
                    if earn_x and e_i >= 0:
                        earn_x = (earn_x[0], ded_x[0] - 1)
                    elif earn_x and earn_x[0] < ded_x[0] and e_i < 0:
                        pass
                continue
            if not started:
                continue
            if "netpay" in s or "netsalary" in s or "takehome" in s:
                break
            words = sorted(line.words, key=lambda w: w.bbox.x0)
            two_col = earn_x is not None and ded_x is not None and ded_x[0] > earn_x[0] + 50
            left_words = [w for w in words if not two_col or w.bbox.x0 < ded_x[0] - 2]
            right_words = [w for w in words if two_col and w.bbox.x0 >= ded_x[0] - 2]
            if two_col:
                _pay_row(earn, left_words)
                _pay_row(ded, right_words)
            else:
                target = ded if (ded_x is not None and earn_x is None) or (ded is not None and ded_x and earn_x and ded_x[0] <= earn_x[0] and line.y > 0 and _after_deductions(lines, line)) else earn
                if not is_total:
                    _pay_row(target, left_words)
        for t in (earn, ded):
            if t and t.rows:
                boxes = [c.bbox for r in t.rows for c in r if c.bbox]
                t.bbox = union_bbox(boxes) if boxes else None
                tables.append(t)
    return tables


def _after_deductions(lines: list[Line], line: Line) -> bool:
    for ln in lines:
        if ln is line:
            return False
        if "deductions" in ln.squished and not re.search(r"\d", ln.squished):
            return True
    return False


def _pay_row(table: Table | None, words: list) -> None:
    if table is None or not words:
        return
    text = " ".join(w.text for w in words)
    if re.match(r"(?i)^\s*(total|gross)", text):
        return
    numeric = [w for w in words if _token_is_numeric(w.text) and any(c.isdigit() for c in w.text)]
    if not numeric:
        return
    amount = numeric[-1]
    label_words = [w for w in words if w.bbox.x1 <= amount.bbox.x0 and not re.fullmatch(r"(?i)rs\.?|inr|₹", w.text)]
    if not label_words:
        return
    table.rows.append(
        [
            TableCell(
                text=" ".join(w.text for w in label_words),
                confidence=round(min(w.confidence for w in label_words), 3),
                bbox=union_bbox([w.bbox for w in label_words]),
            ),
            TableCell(text=amount.text, confidence=round(amount.confidence, 3), bbox=amount.bbox),
        ]
    )


def extract_fields(doc: Document) -> Document:
    if not is_processable(doc):
        return doc
    try:
        ex = _Extractor(doc)
        for page in doc.pages:
            if page.words:
                ex.run_page(page.index)
        ex.fallbacks()
        doc.fields = _dedupe(ex.fields)
        if doc.doc_type == DocType.bank_statement:
            doc.tables = _extract_transactions(doc)
        elif doc.doc_type == DocType.salary_slip:
            doc.tables = _extract_pay_tables(doc)
    except Exception as exc:
        log.exception("field extraction failed")
        doc.metadata["extraction_error"] = type(exc).__name__
    return doc


def _dedupe(fields: list[Field]) -> list[Field]:
    seen: set[tuple[str, int, int, int]] = set()
    out = []
    for f in fields:
        key = (f.name, f.page, int(f.bbox.x0), int(f.bbox.y0))
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out
