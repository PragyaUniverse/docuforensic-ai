"""Structural understanding: section hierarchy, expected fields, field relationships."""
from __future__ import annotations

import re

import numpy as np

from models.schemas import BBox, DocType, Document, Section
from pipeline.common import is_processable, log
from pipeline.layout import Line, doc_lines

# Fields each document type is expected to carry. Their absence is reported, not assumed wrong.
REQUIRED_FIELDS: dict[DocType, list[str]] = {
    DocType.application_form: [
        "application_id", "person_name", "date_of_birth", "address", "employer_name",
        "declared_monthly_income", "application_date",
    ],
    DocType.id_proof: ["id_number", "person_name", "date_of_birth"],
    DocType.salary_slip: [
        "person_name", "employer_name", "pay_period", "basic_pay", "gross_pay", "total_deductions", "net_pay",
    ],
    DocType.bank_statement: ["person_name", "bank_name", "bank_account_number", "statement_period", "opening_balance", "closing_balance"],
    DocType.address_proof: ["person_name", "address", "bill_date"],
    DocType.declaration: ["person_name", "declaration_date"],
}

SECTION_WORDS = re.compile(
    r"(?i)\b(details|information|particulars|summary|earnings|deductions|transactions|declaration|"
    r"personal|employment|financial|applicant|address|contact|bank|loan|income|signature|statement|"
    r"charges|account|verification|attachments|documents)\b"
)


def _is_heading(line: Line, median_h: float) -> bool:
    text = line.text.strip()
    if not text or ":" in text or len(line.words) > 7 or len(text) > 60:
        return False
    if sum(c.isdigit() for c in text) > 2:
        return False
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return False
    caps = sum(c.isupper() for c in letters) / len(letters)
    tall = line.height >= 1.18 * median_h
    return tall or (caps >= 0.75 and len(letters) >= 4) or (bool(SECTION_WORDS.search(text)) and caps >= 0.3 and len(line.words) <= 4)


def _build_sections(doc: Document) -> list[Section]:
    roots: list[Section] = []
    for page in doc.pages:
        lines = doc_lines(doc, page.index)
        if not lines:
            continue
        median_h = float(np.median([ln.height for ln in lines]))
        heads = [ln for ln in lines if _is_heading(ln, median_h)]
        page_fields = [f for f in doc.fields if f.page == page.index]
        content_bbox = BBox(
            x0=min(ln.bbox.x0 for ln in lines), y0=min(ln.bbox.y0 for ln in lines),
            x1=max(ln.bbox.x1 for ln in lines), y1=max(ln.bbox.y1 for ln in lines),
        )
        # A document title is the tallest heading in the top third.
        title = None
        top = [h for h in heads if h.bbox.y0 < page.height / 3]
        if top:
            title = max(top, key=lambda h: h.height)
        root = Section(name=(title.text if title else f"Page {page.index + 1}"), page=page.index, bbox=content_bbox)
        body_heads = [h for h in heads if h is not title]
        # Fields above the first sub-heading belong directly to the root.
        for i, head in enumerate(body_heads):
            y0 = head.bbox.y0
            y1 = body_heads[i + 1].bbox.y0 if i + 1 < len(body_heads) else content_bbox.y1 + 1
            members = [f.id for f in page_fields if y0 <= (f.bbox.y0 + f.bbox.y1) / 2 < y1]
            section = Section(
                name=head.text, page=page.index,
                bbox=BBox(x0=content_bbox.x0, y0=y0, x1=content_bbox.x1, y1=min(y1, content_bbox.y1)),
                field_ids=members,
            )
            root.children.append(section)
            for f in page_fields:
                if f.id in members:
                    f.section = head.text
        grouped = {m for c in root.children for m in c.field_ids}
        root.field_ids = [f.id for f in page_fields if f.id not in grouped]
        for f in page_fields:
            if f.id in root.field_ids:
                f.section = root.name
        roots.append(root)
    return roots


def _relationships(doc: Document) -> list[dict]:
    """Field dependencies the contextual stage can check. Listed only when the fields exist."""
    names = {f.name: f.id for f in reversed(doc.fields)}
    rel: list[dict] = []

    def add(kind: str, target: str, parts: list[str], desc: str) -> None:
        present = [p for p in parts if p in names]
        if target in names and present:
            rel.append({"relation": kind, "target": names[target], "target_name": target,
                        "parts": [names[p] for p in present], "part_names": present, "description": desc})

    add("sum_of", "gross_pay", ["basic_pay", "hra", "other_allowances"], "Gross pay should equal its earnings components.")
    add("difference_of", "net_pay", ["gross_pay", "total_deductions"], "Net pay should equal gross pay less deductions.")
    add("balance_flow", "closing_balance", ["opening_balance"], "Closing balance should equal opening balance plus credits less debits.")
    add("precedes", "application_date", ["date_of_birth"], "A date of birth must come before an application date.")
    return rel


def analyze_structure(doc: Document) -> Document:
    if not is_processable(doc):
        return doc
    try:
        doc.sections = _build_sections(doc)
        names = {f.name for f in doc.fields}
        required = REQUIRED_FIELDS.get(doc.doc_type, [])
        doc.missing_fields = [n for n in required if n not in names]
        # Repeats on a later page (running headers) are normal. Report repeats on the same page
        # and any repeat with a different value.
        dup: set[str] = set()
        by_name: dict[str, list] = {}
        for f in doc.fields:
            by_name.setdefault(f.name, []).append(f)
        for name, items in by_name.items():
            if len(items) < 2:
                continue
            pages = [f.page for f in items]
            values = {f.value_norm or f.value_raw for f in items}
            if len(set(pages)) < len(pages) or len(values) > 1:
                dup.add(name)
        doc.duplicated_fields = sorted(dup)
        doc.metadata["relationships"] = _relationships(doc)
        doc.metadata["layout"] = {
            "sections": sum(1 + len(s.children) for s in doc.sections),
            "tables": [t.name for t in doc.tables],
            "field_count": len(doc.fields),
        }
    except Exception as exc:
        log.exception("structure analysis failed")
        doc.metadata["structure_error"] = type(exc).__name__
    return doc
