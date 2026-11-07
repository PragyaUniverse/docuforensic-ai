"""Seen before: details from this application that also appear in another application on this system.

One person or group applying many times is a common pattern that a single application can't reveal.
Each run records a fingerprint of the identifying details on every document: phone, email, bank
account, PAN and ID numbers exactly, and the applicant photo and signatures as small image hashes. A
new application is compared with every other one on record.

A repeated detail is reported as just that, with innocent explanations. It is never a verdict, and
a match under the same applicant name is only an observation, since people reapply.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import imagehash
import numpy as np
from PIL import Image
from rapidfuzz import fuzz

from backend import db
from models.schemas import (
    BBox,
    Case,
    CaseStatus,
    Document,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingCategory,
    FindingStatus,
    Severity,
)

log = logging.getLogger("docuforensic.crosscase")
DETECTOR = "crosscase.repeated_element"
TEXT_FIELDS = {
    "phone": "Mobile number", "email": "Email address", "bank_account_number": "Bank account number",
    "pan_number": "PAN", "id_number": "ID number",
}
IMAGE_KINDS = {"photo": "Applicant photo", "signature": "Signature"}
LABELS = {**TEXT_FIELDS, **IMAGE_KINDS}
# Strong details are hard to share innocently. Phone and email are often shared within a family.
STRONG = {"photo", "signature", "bank_account_number", "pan_number", "id_number"}
# A perceptual hash finds candidates, and correlation of aligned thumbnails confirms them. Photos are
# compared in colour: portraits share a head-and-shoulders layout, so grey alone is too forgiving.
# Measured on the demo set: the repeated photo scores 0.995 to 1.000, different portraits at most 0.863.
THUMB = {"photo": 16, "signature": 24}
PHASH_MAX = {"photo": 12, "signature": 8}
MIN_CORR = {"photo": 0.95, "signature": 0.93}
MAX_MEAN_DIFF = {"photo": 14.0, "signature": 255.0}
SAME_NAME = 85  # rapidfuzz token_set_ratio


# ---------------------------------------------------------------- fingerprints
def _norm_text(kind: str, value: str) -> str | None:
    if kind == "email":
        v = value.strip().casefold()
        return v if "@" in v else None
    if kind == "pan_number":
        v = re.sub(r"[^A-Z0-9]", "", value.upper())
        return v if len(v) == 10 else None
    digits = re.sub(r"\D", "", value)
    if kind == "phone":
        return digits[-10:] if len(digits) >= 10 else None
    return digits if len(digits) >= 8 else None


def mask(kind: str, value: str) -> str:
    """Enough to recognise a detail without printing it in full."""
    if kind == "email":
        user, _, domain = value.partition("@")
        return f"{user[:1]}•••@{domain}"
    tail = re.sub(r"[^A-Za-z0-9]", "", value)[-4:]
    return f"•••• {tail}"


def _page_rgb(doc: Document, page: int) -> np.ndarray | None:
    from pipeline.common import from_rel

    if not 0 <= page < len(doc.pages):
        return None
    try:
        with Image.open(from_rel(doc.pages[page].image_path)) as im:
            return np.asarray(im.convert("RGB"))
    except OSError:
        return None


def _image_print(kind: str, rgb: np.ndarray, bbox: BBox) -> dict[str, Any] | None:
    h, w = rgb.shape[:2]
    x0, y0 = max(0, int(bbox.x0)), max(0, int(bbox.y0))
    x1, y1 = min(w, int(bbox.x1)), min(h, int(bbox.y1))
    if x1 - x0 < 12 or y1 - y0 < 12:
        return None
    crop = rgb[y0:y1, x0:x1]
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    if float(gray.std()) < 4:  # blank
        return None
    size = THUMB[kind]
    source = crop if kind == "photo" else gray
    thumb = cv2.resize(source, (size, size), interpolation=cv2.INTER_AREA)
    return {"phash": str(imagehash.phash(Image.fromarray(gray))), "thumb": thumb.astype(int).flatten().tolist()}


def fingerprints(docs: list[Document]) -> list[dict[str, Any]]:
    """Identifying details on each document, with where they are."""
    out: list[dict[str, Any]] = []
    for doc in docs:
        if not doc.pages:
            continue
        for f in doc.fields:
            if f.name in TEXT_FIELDS:
                value = _norm_text(f.name, f.value_raw)
                if value:
                    out.append({"doc_id": doc.id, "kind": f.name, "value": value, "page": f.page,
                                "bbox": f.bbox.model_dump(), "field_id": f.id})
        regions: list[tuple[str, int, dict]] = []
        for page, boxes in (doc.metadata.get("photo_regions") or {}).items():
            regions += [("photo", int(page), b) for b in boxes]
        for sig in doc.metadata.get("signatures") or []:
            if sig.get("ink_found"):
                regions.append(("signature", int(sig["page"]), sig["bbox"]))
        pages: dict[int, np.ndarray | None] = {}
        for kind, page, box in regions:
            if page not in pages:
                pages[page] = _page_rgb(doc, page)
            rgb = pages[page]
            if rgb is None:
                continue
            try:
                bbox = BBox(**box)
                printed = _image_print(kind, rgb, bbox)
            except Exception:
                continue
            if printed:
                out.append({"doc_id": doc.id, "kind": kind, "value": printed["phash"], "page": page,
                            "bbox": bbox.model_dump(), "thumb": printed["thumb"]})
    return out


def applicant_name(docs: list[Document]) -> str | None:
    names: dict[str, int] = defaultdict(int)
    shown: dict[str, str] = {}
    for doc in docs:
        for f in doc.fields:
            if f.name == "person_name" and f.value_raw.strip():
                key = " ".join(f.value_raw.split()).casefold()
                names[key] += 1
                shown.setdefault(key, " ".join(f.value_raw.split()))
    if not names:
        return None
    return shown[max(names, key=lambda k: names[k])]


def record(case: Case, docs: list[Document]) -> int:
    """Stores this case's fingerprints, replacing any from an earlier run."""
    prints = fingerprints(docs)
    db.replace_fingerprints(case.id, prints, applicant_name(docs))
    return len(prints)


# ---------------------------------------------------------------- matching
def _corr(a: list[int], b: list[int]) -> float:
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    x, y = x - x.mean(), y - y.mean()
    denom = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / denom) if denom else 0.0


def _same(a: dict, b: dict) -> float | None:
    """Similarity in 0..1 when two fingerprints are the same detail, else None."""
    if a["kind"] != b["kind"]:
        return None
    if a["kind"] in TEXT_FIELDS:
        return 1.0 if a["value"] == b["value"] else None
    kind = a["kind"]
    if len(a.get("thumb", [])) != len(b.get("thumb", [])) or not a.get("thumb"):
        return None
    distance = imagehash.hex_to_hash(a["value"]) - imagehash.hex_to_hash(b["value"])
    if distance > PHASH_MAX[kind]:
        return None
    corr = _corr(a["thumb"], b["thumb"])
    diff = float(np.abs(np.asarray(a["thumb"], dtype=float) - np.asarray(b["thumb"], dtype=float)).mean())
    return round(corr, 3) if corr >= MIN_CORR[kind] and diff <= MAX_MEAN_DIFF[kind] else None


def _same_applicant(a: str | None, b: str | None) -> bool:
    return bool(a and b and fuzz.token_set_ratio(a.casefold(), b.casefold()) >= SAME_NAME)


def _skip_pair(case: Case, other: Case) -> bool:
    # The same demo files loaded twice are the same application, not a repeat.
    return bool(case.is_demo and other.is_demo and case.demo_key and case.demo_key == other.demo_key)


def backfill() -> int:
    """Fingerprints finished cases analysed before this check existed, so they can be matched too."""
    known = db.fingerprint_applicants()
    done = 0
    for c in db.list_cases():
        if c.id in known or c.status != CaseStatus.complete:
            continue
        try:
            record(c, db.list_documents(c.id))
            done += 1
        except Exception as exc:  # one unreadable case mustn't stop the comparison
            log.warning("fingerprint backfill failed case=%s: %s", c.id, type(exc).__name__)
    return done


def matches(case_id: str) -> dict[str, Any]:
    """Every other application sharing a detail with this one, grouped by application."""
    backfill()
    case = db.get_case(case_id)
    mine = db.list_fingerprints(case_id)
    others = db.list_fingerprints_except(case_id)
    cases = {c.id: c for c in db.list_cases()}
    names = db.fingerprint_applicants()
    docs = {d.id: d for d in db.list_documents(case_id)}
    other_docs: dict[str, Document | None] = {}
    groups: dict[str, dict[str, Any]] = {}
    seen: set[tuple] = set()
    for b in others:
        other = cases.get(b["case_id"])
        if other is None or case is None or _skip_pair(case, other):
            continue
        for a in mine:
            sim = _same(a, b)
            if sim is None:
                continue
            key = (b["case_id"], a["kind"], a["value"] if a["kind"] in TEXT_FIELDS else a["doc_id"] + str(a["page"]))
            if key in seen:
                continue
            seen.add(key)
            if b["doc_id"] not in other_docs:
                other_docs[b["doc_id"]] = db.get_document(b["doc_id"])
            here_doc, there_doc = docs.get(a["doc_id"]), other_docs[b["doc_id"]]
            g = groups.setdefault(b["case_id"], {
                "case_id": other.id, "case_name": other.name, "created_at": other.created_at.isoformat(),
                "applicant_here": names.get(case_id), "applicant_there": names.get(other.id),
                "same_applicant": _same_applicant(names.get(case_id), names.get(other.id)), "elements": [],
            })
            g["elements"].append({
                "kind": a["kind"], "label": LABELS[a["kind"]], "strong": a["kind"] in STRONG,
                "value": mask(a["kind"], a["value"]) if a["kind"] in TEXT_FIELDS else None,
                "similarity": sim,
                "here": {"doc_id": a["doc_id"], "filename": here_doc.filename if here_doc else None,
                         "doc_type": here_doc.doc_type.value if here_doc else None, "page": a["page"], "bbox": a["bbox"],
                         "field_id": a.get("field_id")},
                "there": {"case_id": other.id, "doc_id": b["doc_id"], "filename": there_doc.filename if there_doc else None,
                          "doc_type": there_doc.doc_type.value if there_doc else None, "page": b["page"], "bbox": b["bbox"],
                          "field_id": b.get("field_id")},
            })
    # The same demo loaded several times is one application: keep its newest copy.
    newest: dict[str, dict[str, Any]] = {}
    for g in groups.values():
        other = cases[g["case_id"]]
        key = f"demo:{other.demo_key}" if other.is_demo and other.demo_key else other.id
        g["copies"] = newest[key]["copies"] + 1 if key in newest else 1
        if key not in newest or g["created_at"] > newest[key]["created_at"]:
            newest[key] = g
        else:
            newest[key]["copies"] = g["copies"]
    ordered = sorted(newest.values(), key=lambda g: (g["same_applicant"], -sum(e["strong"] for e in g["elements"]), -len(g["elements"])))
    distinct = {f"demo:{cases[i].demo_key}" if cases[i].is_demo and cases[i].demo_key else i
                for i in {b["case_id"] for b in others} if i in cases and case and not _skip_pair(case, cases[i])}
    checked = len(distinct)
    return {"case_id": case_id, "checked_cases": checked, "fingerprints": len(mine), "groups": ordered}


# ---------------------------------------------------------------- findings
def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _crop_uri(doc_id: str, page: int, bbox: dict, workdir: Path, name: str) -> str | None:
    from pipeline.common import load_page_rgb, save_crop

    doc = db.get_document(doc_id)
    if doc is None or not 0 <= page < len(doc.pages):
        return None
    try:
        return save_crop(load_page_rgb(doc, page), BBox(**bbox), Path(workdir), doc, name, margin=16)
    except Exception:
        return None


def findings_for(case: Case, docs: list[Document], workdir: Path) -> list[Finding]:
    """One finding per other application that shares details with this one."""
    result = matches(case.id)
    out: list[Finding] = []
    by_id = {d.id: d for d in docs}
    for g in result["groups"]:
        elements = g["elements"]
        kinds = list(dict.fromkeys(e["label"].lower() if e["kind"] not in ("pan_number", "id_number") else e["label"] for e in elements))
        first = elements[0]["here"]
        doc = by_id.get(first["doc_id"])
        if doc is None:
            continue
        strong = any(e["strong"] for e in elements)
        what = _join(kinds)
        verb = "appears" if len(kinds) == 1 else "appear"
        if g["same_applicant"]:
            status, severity, confidence = FindingStatus.OBSERVATION, Severity.low, 0.5
            title = "An earlier application in the same name"
            explanation = (
                f"The {what} on this application also {verb} in '{g['case_name']}', an application in the same name. "
                "That's usually a reapplication or an update, and it's noted so the two can be read together."
            )
        else:
            status = FindingStatus.INCONSISTENCY
            severity, confidence = (Severity.high, 0.9) if strong else (Severity.medium, 0.7)
            n = len(kinds)
            title = f"{n} detail{'s' if n != 1 else ''} from this application appear{'s' if n == 1 else ''} in another one"
            other_name = f" ({g['applicant_there']})" if g["applicant_there"] else ""
            explanation = (
                f"The {what} on this application also {verb} in '{g['case_name']}', an application under a different name{other_name}. "
                "Each document here can agree with the others and still repeat details from someone else's application, "
                "which only a comparison across applications can show."
            )
        evidence: list[EvidenceItem] = []
        for i, e in enumerate(elements):
            here, there = e["here"], e["there"]
            uri = _crop_uri(there["doc_id"], there["page"], there["bbox"], workdir, f"seen_{g['case_id']}_{i}")
            evidence.append(EvidenceItem(
                kind=EvidenceKind.comparison,
                label=f"{e['label']} also in '{g['case_name']}' ({there['filename']})",
                uri=uri, doc_id=here["doc_id"], page=here["page"], bbox=BBox(**here["bbox"]), field_id=here.get("field_id"),
                data={"other_case_id": g["case_id"], "other_case_name": g["case_name"], "other_document": there["filename"],
                      "other_page": there["page"] + 1, "detail": e["label"], "value": e["value"] or "image match",
                      "similarity": e["similarity"]},
            ))
        related = sorted({e["here"]["doc_id"] for e in elements} - {doc.id})
        out.append(Finding(
            case_id=case.id, status=status, category=FindingCategory.cross_document, severity=severity,
            confidence=confidence, title=title, doc_id=doc.id, page=first["page"], bbox=BBox(**first["bbox"]),
            related_doc_ids=related, related_field_ids=[e["here"]["field_id"] for e in elements if e["here"].get("field_id")],
            evidence=evidence, explanation=explanation, detector=DETECTOR,
            benign_alternatives=[
                "Family members often share a phone number, an email address or a joint bank account.",
                "A photo or document may have been attached to the wrong application by mistake.",
                "The other application may be a duplicate entry or a test.",
            ] if not g["same_applicant"] else ["The applicant may be reapplying or updating an earlier application."],
            recommended_verification=[
                "Ask the applicant about the shared details.",
                "Confirm the account holder's name with the bank.",
                "Compare the photo with the person at a video or in-branch identity check.",
                f"Read '{g['case_name']}' alongside this application.",
            ] if not g["same_applicant"] else [f"Read '{g['case_name']}' alongside this application."],
        ))
        out[-1].fused_score = confidence
    return out
