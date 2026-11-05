"""Checks extracted identifiers against a registry of issued records.

The bundled registry is a synthetic test file, and every finding says so. A real government or bank
source needs authorized access, so it plugs in behind `lookup`. Nothing here contacts the outside world.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from backend.contextual import field_ref
from backend.normalize import compare_names, norm_id, parse_date
from config.settings import settings
from models.schemas import Document, Field, Finding, FindingCategory, FindingStatus, Severity

SOURCE = "the bundled synthetic test registry, not a government source"
_CHECKED = ("pan_number", "id_number")


def load() -> dict | None:
    path = Path(settings.demo_cases_dir) / "registry.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def lookup(registry: dict, id_value: str) -> dict | None:
    return registry.get("records", {}).get(norm_id(id_value))


def _finding(case_id: str, doc: Document, field: Field, title: str, text: str, status: FindingStatus,
             severity: Severity, confidence: float, detector: str, extra: list[Field]) -> Finding:
    involved = [field, *extra]
    return Finding(
        case_id=case_id, status=status, category=FindingCategory.contextual, severity=severity, confidence=confidence,
        title=title, doc_id=doc.id, page=field.page, bbox=field.bbox, related_doc_ids=[doc.id],
        related_field_ids=[f.id for f in involved], evidence=[field_ref(f) for f in involved],
        explanation=f"{text} Checked against {SOURCE}.", detector=detector,
        benign_alternatives=["An OCR misreading of the number or name.", "The record may be out of date."],
        recommended_verification=["Check the number against the issuer's own record."],
    )


def check(docs: list[Document], case_id: str) -> list[Finding]:
    registry = load()
    if registry is None:
        return []
    out: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for doc in docs:
        by_name = {f.name: f for f in doc.fields}
        for name in _CHECKED:
            field = by_name.get(name)
            if field is None:
                continue
            value = norm_id(field.value_raw)
            record = lookup(registry, value)
            if record is None:
                if ("missing", value) not in seen:
                    seen.add(("missing", value))
                    out.append(_finding(
                        case_id, doc, field, "This ID number isn't in the registry",
                        f"'{field.value_raw}' on {doc.filename} has no matching record.",
                        FindingStatus.OBSERVATION, Severity.low, 0.6, "registry.not_found", [],
                    ))
                continue
            person = by_name.get("person_name")
            if person is not None and not compare_names(person.value_raw, record["person_name"]).same:
                out.append(_finding(
                    case_id, doc, field, "The name doesn't match the registry record",
                    f"{doc.filename} gives the name '{person.value_raw}' for this number, but the record says "
                    f"'{record['person_name']}'.",
                    FindingStatus.INCONSISTENCY, Severity.medium, 0.8, "registry.name_mismatch", [person],
                ))
            dob = by_name.get("date_of_birth")
            stated: date | None = parse_date(dob.value_norm or dob.value_raw) if dob else None
            if dob is not None and stated and record.get("date_of_birth") and stated.isoformat() != record["date_of_birth"]:
                out.append(_finding(
                    case_id, doc, field, "The date of birth doesn't match the registry record",
                    f"{doc.filename} gives {dob.value_raw} for this number, but the record says {record['date_of_birth']}.",
                    FindingStatus.INCONSISTENCY, Severity.medium, 0.8, "registry.dob_mismatch", [dob],
                ))
    return out
