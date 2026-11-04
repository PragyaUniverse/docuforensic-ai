"""Evidence fusion: one explainable score per suspicious region.

A single weak signal stays a low-confidence observation. POTENTIAL_MANIPULATION requires agreement
from at least two independent signal families, or one very strong signal. Fusion never upgrades a
hypothesis to a fact, and each fused finding lists what contributed and how much.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.schemas import (
    BBox,
    Document,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingCategory,
    FindingStatus,
    Severity,
)
from pipeline.common import expand_bbox, union_bbox


@dataclass(frozen=True)
class Signal:
    family: str  # signals in one family aren't independent of each other
    weight: float  # how much this detector can contribute, given its false-positive behaviour
    can_stand_alone: bool = False


SIGNALS: dict[str, Signal] = {
    "visual.ela": Signal("compression", 0.35),
    "visual.noise": Signal("noise", 0.45),
    "visual.overwrite": Signal("background", 0.75),
    "visual.font_consistency": Signal("typography", 0.7),
    "visual.alignment": Signal("geometry", 0.3),
    "visual.copy_move": Signal("clone", 0.92, can_stand_alone=True),
    # Its score already requires several measurements of the region to agree.
    "visual.photo_insert": Signal("image", 0.75, can_stand_alone=True),
    "pdf.text_vs_pixels": Signal("pdf_content", 0.95, can_stand_alone=True),
    "pdf.incremental_update": Signal("pdf_history", 0.8),
    "pdf.overlay_object": Signal("pdf_content", 0.8),
    "metadata.exif": Signal("metadata", 0.3),
}

CORROBORATION_MIN_CONF = 0.3  # a family counts as corroborating only above this
POTENTIAL_MIN_SCORE = 0.6
STANDALONE_MIN_CONF = 0.85
WEAK_OBSERVATION_CAP = 0.5
# These never merge: they are document-level facts or already case-level conclusions.
PASS_THROUGH = {"visual.signature_reuse", "visual.signature_placement", "pdf.producer_mismatch", "metadata.pdf_dates"}


def _touches(a: BBox, b: BBox, margin: float) -> bool:
    ea = expand_bbox(a, margin)
    ix = min(ea.x1, b.x1) - max(ea.x0, b.x0)
    iy = min(ea.y1, b.y1) - max(ea.y0, b.y0)
    if ix <= 0 or iy <= 0:
        return False
    inter = ix * iy
    return inter / max(min(a.area, b.area), 1.0) >= 0.25


def _clusters(items: list[Finding]) -> list[list[Finding]]:
    """Group findings whose regions overlap. Very large boxes don't act as bridges."""
    clusters: list[list[Finding]] = []
    for f in sorted(items, key=lambda x: x.bbox.area):  # small, precise regions anchor clusters
        placed = False
        for cluster in clusters:
            anchor = cluster[0].bbox
            if f.bbox.area > 60 * max(anchor.area, 1.0):
                continue
            if any(_touches(f.bbox, g.bbox, 10) for g in cluster):
                cluster.append(f)
                placed = True
                break
        if not placed:
            clusters.append([f])
    return clusters


def _weighted(f: Finding) -> float:
    signal = SIGNALS.get(f.detector, Signal(f.detector, 0.4))
    return signal.weight * f.confidence


def _score(cluster: list[Finding]) -> tuple[float, dict[str, float]]:
    """Noisy-OR over families, using the strongest signal per family."""
    families: dict[str, float] = {}
    for f in cluster:
        fam = SIGNALS.get(f.detector, Signal(f.detector, 0.4)).family
        families[fam] = max(families.get(fam, 0.0), _weighted(f))
    remaining = 1.0
    for v in families.values():
        remaining *= 1.0 - v
    return 1.0 - remaining, families


def _decide(cluster: list[Finding], score: float) -> FindingStatus:
    if any(f.status == FindingStatus.POTENTIAL_MANIPULATION for f in cluster):
        return FindingStatus.POTENTIAL_MANIPULATION
    corroborating: set[str] = set()
    for f in cluster:
        sig = SIGNALS.get(f.detector, Signal(f.detector, 0.4))
        if f.confidence >= CORROBORATION_MIN_CONF and sig.family != "geometry":
            corroborating.add(sig.family)
    if len(corroborating) >= 2 and score >= POTENTIAL_MIN_SCORE:
        return FindingStatus.POTENTIAL_MANIPULATION
    for f in cluster:
        sig = SIGNALS.get(f.detector, Signal(f.detector, 0.4))
        if sig.can_stand_alone and f.confidence >= STANDALONE_MIN_CONF:
            return FindingStatus.POTENTIAL_MANIPULATION
    return FindingStatus.OBSERVATION


def _merge(cluster: list[Finding], doc_fields: list) -> Finding:
    score, families = _score(cluster)
    status = _decide(cluster, score)
    lead = max(cluster, key=_weighted)
    # Precise detectors define the region: the box drawn around the value, not the surroundings.
    precise = [f for f in cluster if SIGNALS.get(f.detector, Signal("", 0)).weight >= 0.65]
    box = union_bbox([f.bbox for f in precise]) if precise else lead.bbox

    detectors = sorted({f.detector for f in cluster})
    evidence: list[EvidenceItem] = [
        EvidenceItem(
            kind=EvidenceKind.raw_value, label="Fused region score", doc_id=lead.doc_id, page=lead.page, bbox=box,
            data={
                "fused_score": round(score, 3),
                "formula": "1 - product(1 - weight*confidence) over independent signal families",
                "families": {k: round(v, 3) for k, v in families.items()},
                "contributing_detectors": detectors,
            },
        )
    ]
    seen = set()
    for f in cluster:
        for ev in f.evidence:
            key = (ev.kind, ev.label, ev.uri, str(ev.data)[:80])
            if key not in seen:
                seen.add(key)
                evidence.append(ev)

    explanation = lead.explanation
    others = [f for f in cluster if f is not lead and f.detector != lead.detector]
    if others:
        details = "; ".join(f"{f.detector} (confidence {f.confidence:.2f}): {f.explanation}" for f in others[:4])
        explanation = f"{lead.explanation} Other signals on this region: {details}"
    benign, verify = [], []
    for f in cluster:
        for b in f.benign_alternatives:
            if b not in benign:
                benign.append(b)
        for v in f.recommended_verification:
            if v not in verify:
                verify.append(v)

    if status == FindingStatus.POTENTIAL_MANIPULATION:
        confidence = round(min(score, 0.97), 3)
        severity = Severity.high if score >= 0.75 else Severity.medium
        title = lead.title if len(detectors) == 1 else f"{lead.title} ({len(detectors)} signals agree)"
    else:
        confidence = round(min(lead.confidence, WEAK_OBSERVATION_CAP), 3)
        severity = Severity.low
        title = lead.title

    related = [fld.id for fld in doc_fields if fld.page == lead.page and _touches(box, fld.bbox, 6)]
    return lead.model_copy(
        update={
            "status": status,
            "severity": severity,
            "confidence": confidence,
            "title": title,
            "bbox": box,
            "evidence": evidence[:14],
            "explanation": explanation,
            "benign_alternatives": benign[:6],
            "recommended_verification": verify[:6],
            "related_field_ids": related,
            "fused_score": round(score, 3),
            "category": FindingCategory.structural if lead.detector.startswith("pdf.") else lead.category,
        }
    )


def fuse_regions(findings: list[Finding], doc: Document) -> list[Finding]:
    mine = [f for f in findings if f.doc_id == doc.id]
    others = [f for f in findings if f.doc_id != doc.id]
    out: list[Finding] = list(others)
    regional: dict[int, list[Finding]] = {}
    for f in mine:
        if f.bbox is None or f.page is None or f.detector in PASS_THROUGH or f.status == FindingStatus.INCONSISTENCY:
            if f.fused_score is None:
                f.fused_score = round(f.confidence, 3) if f.status == FindingStatus.POTENTIAL_MANIPULATION else None
            out.append(f)
        else:
            regional.setdefault(f.page, []).append(f)
    for page, items in regional.items():
        for cluster in _clusters(items):
            out.append(_merge(cluster, doc.fields))
    return out
