"""Verify this report: is a dossier PDF exactly as this system issued it?

Every dossier PDF the system produces has its SHA-256 written into the hash-chained audit trail.
An uploaded file is hashed and looked up there. A match proves the bytes are unchanged since that
entry, and the chain check shows whether the trail itself is intact. A file that names a case but
matches nothing was changed after it was issued, or wasn't issued here.

This proves a report is unaltered, not that its findings are right: they still need a person.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from audit import chain
from backend import db

ISSUE_ACTIONS = ("dossier.issued", "stage.dossier")
_CASE_ID = re.compile(r"\bcase_[0-9a-f]{12}\b")


def _named_case(pdf: bytes) -> str | None:
    """The case a PDF says it belongs to: its metadata first, then its text."""
    try:
        import pymupdf

        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            meta = " ".join(str(v) for v in (doc.metadata or {}).values() if v)
            found = _CASE_ID.search(meta)
            if found:
                return found.group(0)
            for page in doc.pages(0, min(doc.page_count, 3)):
                found = _CASE_ID.search(page.get_text())
                if found:
                    return found.group(0)
    except Exception:
        return None
    return None


def verify(pdf: bytes, filename: str | None = None) -> dict[str, Any]:
    digest = hashlib.sha256(pdf).hexdigest()
    result: dict[str, Any] = {"sha256": digest, "filename": filename, "size_bytes": len(pdf)}
    if not pdf.startswith(b"%PDF"):
        return {**result, "result": "not_pdf",
                "message": "This isn't a PDF file. Upload a dossier PDF downloaded from the Report tab."}
    integrity = chain.verify()
    result["chain"] = integrity.model_dump()
    issued = chain.find_entries(digest, ISSUE_ACTIONS)
    if issued:
        entry = issued[0]
        case = db.get_case(entry.case_id) if entry.case_id else None
        variant = entry.payload.get("variant", "full")
        trail = "and the history it's recorded in is intact." if integrity.ok else (
            f"but the history has been changed since entry #{integrity.first_bad_seq}, so treat this with care.")
        return {**result, "result": "original", "case_id": entry.case_id, "case_name": case.name if case else None,
                "issued_at": entry.ts.isoformat(), "entry_seq": entry.seq, "variant": variant,
                "message": f"This is an original report, unchanged since it was issued (history entry #{entry.seq}), {trail}"}
    named = _named_case(pdf)
    case = db.get_case(named) if named else None
    if case:
        return {**result, "result": "modified", "case_id": case.id, "case_name": case.name,
                "message": f"This file names '{case.name}', but it doesn't match any report issued for that case. "
                           "It has been changed since it was produced, or re-saved by another program."}
    return {**result, "result": "unknown",
            "message": "This file doesn't match any report issued by this system, and doesn't name a case here."}


def record_issued(case_id: str, pdf_path, variant: str = "full") -> str:
    from pathlib import Path

    digest = hashlib.sha256(Path(pdf_path).read_bytes()).hexdigest()
    chain.append("dossier.issued", "system", case_id, {"pdf_sha256": digest, "variant": variant})
    return digest
