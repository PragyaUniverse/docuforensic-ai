"""Shared helpers for pipeline stages: paths, images, finding construction."""
from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image

from config.settings import settings
from models.schemas import (
    BBox,
    Document,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingCategory,
    FindingStatus,
    ProcessingStatus,
    Severity,
)

log = logging.getLogger("pipeline")

SKIP_STATUSES = {ProcessingStatus.unsupported, ProcessingStatus.failed}


def is_processable(doc: Document) -> bool:
    return doc.status not in SKIP_STATUSES and bool(doc.pages)


def to_rel(path: Path) -> str:
    """Path relative to settings.data_dir. Stays valid for workdirs outside it."""
    return os.path.relpath(Path(path).resolve(), Path(settings.data_dir).resolve())


def from_rel(rel: str) -> Path:
    p = Path(rel)
    if p.is_absolute():
        return p
    return (Path(settings.data_dir) / p).resolve()


def load_page_rgb(doc: Document, page_index: int) -> np.ndarray:
    page = doc.pages[page_index]
    with Image.open(from_rel(page.image_path)) as im:
        return np.asarray(im.convert("RGB"))


def source_path(doc: Document) -> Path | None:
    rel = doc.metadata.get("source_path")
    if not rel:
        return None
    p = from_rel(rel)
    return p if p.exists() else None


def clip_bbox(b: BBox, width: int, height: int) -> BBox:
    return BBox(
        x0=max(0.0, min(float(b.x0), width)),
        y0=max(0.0, min(float(b.y0), height)),
        x1=max(0.0, min(float(b.x1), width)),
        y1=max(0.0, min(float(b.y1), height)),
    )


def union_bbox(boxes: list[BBox]) -> BBox:
    return BBox(
        x0=min(b.x0 for b in boxes),
        y0=min(b.y0 for b in boxes),
        x1=max(b.x1 for b in boxes),
        y1=max(b.y1 for b in boxes),
    )


def expand_bbox(b: BBox, margin: float) -> BBox:
    return BBox(x0=b.x0 - margin, y0=b.y0 - margin, x1=b.x1 + margin, y1=b.y1 + margin)


def intersection_area(a: BBox, b: BBox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, w) * max(0.0, h)


def containment(inner: BBox, outer: BBox) -> float:
    """Share of `inner` covered by `outer`."""
    return intersection_area(inner, outer) / inner.area if inner.area > 0 else 0.0


def doc_dir(workdir: Path, doc: Document) -> Path:
    d = Path(workdir) / doc.id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_crop(
    img: np.ndarray, bbox: BBox, workdir: Path, doc: Document, name: str, margin: int = 12
) -> str:
    """Save an evidence crop and return its data_dir-relative uri."""
    h, w = img.shape[:2]
    b = clip_bbox(expand_bbox(bbox, margin), w, h)
    x0, y0, x1, y1 = int(b.x0), int(b.y0), max(int(b.x1), int(b.x0) + 1), max(int(b.y1), int(b.y0) + 1)
    out = doc_dir(workdir, doc) / "evidence"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    Image.fromarray(img[y0:y1, x0:x1]).save(path, compress_level=1)
    return to_rel(path)


def save_heatmap(
    values: np.ndarray, workdir: Path, doc: Document, kind: str, page: int
) -> str:
    """Write a page-sized RGBA heatmap. `values` is float in 0..1, already page sized."""
    v = np.clip(values, 0.0, 1.0)
    # Blue to yellow to red ramp; alpha follows intensity so the page stays readable.
    r = np.clip(2.0 * v, 0, 1)
    g = np.clip(2.0 * v, 0, 1) * np.clip(2.0 - 2.0 * v, 0, 1)
    b = np.clip(1.0 - 2.0 * v, 0, 1)
    a = np.clip(v * 1.6, 0, 0.85)
    rgba = (np.dstack([r, g, b, a]) * 255).astype(np.uint8)
    out = doc_dir(workdir, doc) / "overlays"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{kind}_p{page}.png"
    Image.fromarray(rgba, "RGBA").save(path, compress_level=1)
    return to_rel(path)


def make_finding(
    doc: Document,
    detector: str,
    title: str,
    explanation: str,
    status: FindingStatus = FindingStatus.OBSERVATION,
    category: FindingCategory = FindingCategory.visual,
    severity: Severity = Severity.low,
    confidence: float = 0.3,
    page: int | None = None,
    bbox: BBox | None = None,
    evidence: list[EvidenceItem] | None = None,
    benign: list[str] | None = None,
    verify: list[str] | None = None,
    related_doc_ids: list[str] | None = None,
) -> Finding:
    return Finding(
        case_id=doc.case_id,
        status=status,
        category=category,
        severity=severity,
        confidence=round(float(min(max(confidence, 0.0), 1.0)), 3),
        title=title,
        doc_id=doc.id,
        page=page,
        bbox=bbox,
        related_doc_ids=related_doc_ids or [],
        evidence=evidence or [],
        explanation=explanation,
        benign_alternatives=benign or [],
        recommended_verification=verify or [],
        detector=detector,
    )


def measurement(label: str, doc: Document, page: int | None, bbox: BBox | None, **data) -> EvidenceItem:
    return EvidenceItem(
        kind=EvidenceKind.raw_value,
        label=label,
        doc_id=doc.id,
        page=page,
        bbox=bbox,
        data={k: (round(float(v), 4) if isinstance(v, (float, np.floating)) else v) for k, v in data.items()},
    )


def crop_evidence(label: str, uri: str, doc: Document, page: int, bbox: BBox) -> EvidenceItem:
    return EvidenceItem(
        kind=EvidenceKind.crop, label=label, uri=uri, doc_id=doc.id, page=page, bbox=bbox
    )


def heatmap_evidence(label: str, uri: str, doc: Document, page: int) -> EvidenceItem:
    return EvidenceItem(kind=EvidenceKind.heatmap, label=label, uri=uri, doc_id=doc.id, page=page)


def set_degraded(doc: Document, message: str) -> None:
    """Mark degraded, keeping any earlier message. Never downgrades failed/unsupported."""
    if doc.status in SKIP_STATUSES:
        return
    doc.status = ProcessingStatus.degraded
    if doc.status_message and message not in doc.status_message:
        doc.status_message = f"{doc.status_message} {message}"
    elif not doc.status_message:
        doc.status_message = message
