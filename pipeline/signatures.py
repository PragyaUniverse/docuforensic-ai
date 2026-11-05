"""Signature analysis: locate signature ink near its label, check placement, compare across documents.

No two genuine pen signatures are pixel-identical. A perceptual hash finds candidates cheaply, then
normalized correlation on aligned pixels confirms them, so a resemblance alone is never reported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from models.schemas import (
    BBox,
    DocFormat,
    Document,
    EvidenceItem,
    EvidenceKind,
    Finding,
    FindingCategory,
    FindingStatus,
    Severity,
)
from pipeline.common import (
    crop_evidence,
    is_processable,
    load_page_rgb,
    log,
    make_finding,
    measurement,
    save_crop,
    source_path,
)
from pipeline.forensics_visual import ink_mask
from pipeline.layout import doc_lines

LABEL_RE = re.compile(r"(signature|signatory|signed\s*by|sign\.?$|^sign\b|sign\s+here|thumb\s*impression)", re.IGNORECASE)
PHASH_MAX_DISTANCE = 14
IDENTICAL_CORR = 0.93
# Softening makes everything more alike, so it needs a higher bar. Measured: real copies on degraded
# scans score 0.987 or more, and the closest pair of genuinely different signatures scored 0.944.
SOFTENED_IDENTICAL_CORR = 0.97


@dataclass
class SigRegion:
    doc: Document
    page: int
    bbox: BBox
    label: str | None
    label_box: BBox | None
    crop: np.ndarray  # gray, tight on the ink


def _label_lines(doc: Document, page_index: int) -> list[tuple[str, BBox]]:
    out = []
    for line in doc_lines(doc, page_index):
        # Only short label-like rows. A sentence mentioning a signature isn't a signature block.
        if len(line.words) <= 6 and LABEL_RE.search(line.text):
            out.append((line.text, line.bbox))
    return out


def _ink_candidates(gray: np.ndarray, doc: Document, page_index: int) -> list[tuple[BBox, float]]:
    """Connected ink groups that aren't OCR text, and look like pen strokes rather than rules."""
    ink = ink_mask(gray)
    h, w = gray.shape
    mask = ink.copy()
    # Remove confident OCR text. Low-confidence "words" over a signature are usually misreads.
    for wd in doc.pages[page_index].words:
        if wd.confidence >= 0.6 and sum(c.isalnum() for c in wd.text) >= 2:
            b = wd.bbox
            mask[max(int(b.y0) - 3, 0) : int(b.y1) + 3, max(int(b.x0) - 3, 0) : int(b.x1) + 3] = False
    # Remove long straight rules, including the signing line.
    long_h = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((1, 90), np.uint8))
    long_v = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((90, 1), np.uint8))
    mask = mask & ~(long_h.astype(bool) | long_v.astype(bool))
    joined = cv2.dilate(mask.astype(np.uint8), np.ones((9, 25), np.uint8))
    labels, n = ndi.label(joined)
    out = []
    for i, sl in enumerate(ndi.find_objects(labels), start=1):
        region = (labels[sl] == i) & mask[sl]
        if not region.any():
            continue
        ys, xs = np.nonzero(region)
        x0, x1 = sl[1].start + xs.min(), sl[1].start + xs.max() + 1
        y0, y1 = sl[0].start + ys.min(), sl[0].start + ys.max() + 1
        bw, bh = x1 - x0, y1 - y0
        if bw < 70 or bh < 18 or bw > 0.6 * w or bh > 0.2 * h:
            continue
        density = float(region.sum()) / (bw * bh)
        if not 0.02 <= density <= 0.5:
            continue
        # Pen strokes are thin relative to the shape they make.
        dist = cv2.distanceTransform(region.astype(np.uint8), cv2.DIST_L2, 3)
        stroke = float(np.percentile(dist[region], 90)) * 2
        if stroke > 12:
            continue
        out.append((BBox(x0=x0, y0=y0, x1=x1, y1=y1), density))
    return out


def find_signatures(doc: Document) -> list[SigRegion]:
    regions: list[SigRegion] = []
    for page in doc.pages:
        labels = _label_lines(doc, page.index)
        if not labels:
            continue
        try:
            rgb = load_page_rgb(doc, page.index)
        except Exception:
            continue
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        candidates = _ink_candidates(gray, doc, page.index)
        for text, lb in labels:
            lh = max(lb.y1 - lb.y0, 10)
            best = None
            best_dist = 1e9
            for box, _density in candidates:
                # Signatures sit above, beside or just below their label.
                dy = max(lb.y0 - box.y1, box.y0 - lb.y1, 0)
                dx = max(lb.x0 - box.x1, box.x0 - lb.x1, 0)
                dist = dy + 0.5 * dx
                if dist < best_dist and dy < 9 * lh and dx < 18 * lh:
                    best, best_dist = box, dist
            if best is None:
                regions.append(SigRegion(doc, page.index, lb, text, lb, np.zeros((0, 0), np.uint8)))
                continue
            crop = gray[int(best.y0) : int(best.y1), int(best.x0) : int(best.x1)]
            regions.append(SigRegion(doc, page.index, best, text, lb, crop))
    # One ink region can serve only one label: keep the nearest pairing.
    seen: dict[tuple[int, int, int], SigRegion] = {}
    empties: list[SigRegion] = []
    for r in regions:
        if r.crop.size == 0:
            empties.append(r)
            continue
        key = (r.page, int(r.bbox.x0), int(r.bbox.y0))
        if key not in seen:
            seen[key] = r
    return list(seen.values()) + empties


def _phash(crop: np.ndarray) -> imagehash.ImageHash:
    return imagehash.phash(Image.fromarray(crop))


def _native_corr(a: np.ndarray, b: np.ndarray) -> float:
    """Best correlation at native scale. A copied signature keeps its pixels, but ink detection can
    draw slightly different bounds around each copy, and resizing to a common size would blur that
    into a poor match. The core of the smaller crop is searched for inside the larger."""
    small, large = (a, b) if a.size <= b.size else (b, a)
    h, w = small.shape[:2]
    if min(h, w) < 16 or max(small.shape[0] / large.shape[0], large.shape[0] / small.shape[0]) > 1.3:
        return 0.0
    if max(small.shape[1] / large.shape[1], large.shape[1] / small.shape[1]) > 1.3:
        return 0.0
    mx, my = max(2, int(w * 0.08)), max(2, int(h * 0.08))
    core = small[my : h - my, mx : w - mx]
    if core.std() < 4:
        return 0.0
    pad = 12
    field = cv2.copyMakeBorder(large, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
    if field.shape[0] < core.shape[0] or field.shape[1] < core.shape[1]:
        return 0.0
    return float(cv2.matchTemplate(field, core, cv2.TM_CCOEFF_NORMED).max())


def _degraded_corr(a: np.ndarray, b: np.ndarray) -> float:
    """The same comparison for scans. Softening both crops removes blur and JPEG differences, and a
    small rotation search handles a skewed page. Different writers stay far below the threshold, since
    softening doesn't make different strokes line up."""
    soft_a = cv2.GaussianBlur(a, (0, 0), 1.6)
    soft_b = cv2.GaussianBlur(b, (0, 0), 1.6)
    best = _native_corr(soft_a, soft_b)
    h, w = soft_b.shape[:2]
    for angle in (-2.5, -2.0, -1.5, -1.0, -0.5, 0.5, 1.0, 1.5, 2.0, 2.5):
        turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        turned = cv2.warpAffine(soft_b, turn, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        best = max(best, _native_corr(soft_a, turned))
    return best


def _pixel_corr(a: np.ndarray, b: np.ndarray) -> float:
    """Correlation of two signature crops: at native scale, after softening, or after aligning size."""
    if a.size == 0 or b.size == 0:
        return 0.0
    native = _native_corr(a, b)
    if native >= IDENTICAL_CORR:
        return native
    degraded = _degraded_corr(a, b)
    if degraded >= SOFTENED_IDENTICAL_CORR:
        return degraded
    aspect_a, aspect_b = a.shape[1] / a.shape[0], b.shape[1] / b.shape[0]
    if max(aspect_a, aspect_b) / min(aspect_a, aspect_b) > 1.25:
        return 0.0
    size = (320, 120)
    ra = cv2.resize(a, size, interpolation=cv2.INTER_AREA).astype(np.float32)
    rb = cv2.resize(b, size, interpolation=cv2.INTER_AREA).astype(np.float32)
    best = -1.0
    for dx in range(-4, 5, 2):
        for dy in range(-4, 5, 2):
            shifted = np.roll(np.roll(rb, dx, axis=1), dy, axis=0)
            if ra.std() < 1 or shifted.std() < 1:
                continue
            best = max(best, float(np.corrcoef(ra.ravel(), shifted.ravel())[0, 1]))
    return best


def _placement_findings(reg: SigRegion, workdir: Path) -> list[Finding]:
    doc = reg.doc
    if reg.crop.size == 0:
        return [
            make_finding(
                doc, "visual.signature_placement", "No signature ink found near this signature label",
                f"The label '{reg.label}' is printed here, but no pen-like ink was found around it.",
                confidence=0.45, page=reg.page, bbox=reg.label_box,
                evidence=[measurement("Signature search", doc, reg.page, reg.label_box, signature_label=reg.label, ink_found=False)],
                benign=["The signature may be faint, or on a page that wasn't submitted.", "The form may not require a signature at this stage."],
                verify=["Check the physical document for a signature."],
            )
        ]
    findings = []
    words = doc.pages[reg.page].words
    overlap_words = []
    for wd in words:
        if wd.confidence < 0.6 or sum(c.isalnum() for c in wd.text) < 2:
            continue
        ix = min(reg.bbox.x1, wd.bbox.x1) - max(reg.bbox.x0, wd.bbox.x0)
        iy = min(reg.bbox.y1, wd.bbox.y1) - max(reg.bbox.y0, wd.bbox.y0)
        if ix > 0 and iy > 0 and ix * iy / max(wd.bbox.area, 1) > 0.5:
            overlap_words.append(wd.text)
    lb = reg.label_box
    lh = max(lb.y1 - lb.y0, 10)
    gap = max(lb.y0 - reg.bbox.y1, reg.bbox.y0 - lb.y1, 0)
    if len(overlap_words) >= 3 or gap > 6 * lh:
        reason = (
            f"it overlaps printed text ({' '.join(overlap_words[:4])})" if len(overlap_words) >= 3
            else f"it is {gap:.0f}px from its label ('{reg.label}')"
        )
        findings.append(
            make_finding(
                doc, "visual.signature_placement", "Signature placement looks unusual",
                f"The signature ink is unusually placed: {reason}.",
                confidence=0.4, page=reg.page, bbox=reg.bbox,
                evidence=[measurement("Signature placement", doc, reg.page, reg.bbox, gap_to_label_px=gap, overlapped_words=len(overlap_words), signature_label=reg.label)],
                benign=["Signatures often stray from the signing line.", "Layouts vary across issuers."],
                verify=["Check the physical document."],
            )
        )
    return findings


def _software_outliers(docs: list[Document]) -> list[Finding]:
    """Files of one application usually come through one device. Report a lone exception."""
    seen: dict[str, list[Document]] = {}
    for doc in docs:
        if not is_processable(doc) or doc.format not in (DocFormat.png, DocFormat.jpg):
            continue
        src = source_path(doc)
        if not src:
            continue
        try:
            with Image.open(src) as im:
                exif = im.getexif()
                value = (exif.get(0x0131) if exif else None) or im.info.get("Software") or im.info.get("software")
        except Exception:
            continue
        if value:
            seen.setdefault(str(value)[:80], []).append(doc)
    if len(seen) < 2:
        return []
    common, most = max(seen.items(), key=lambda kv: len(kv[1]))
    if len(most) < 2:
        return []
    findings = []
    for value, items in seen.items():
        if value == common or len(items) > 1:
            continue
        doc = items[0]
        findings.append(
            make_finding(
                doc, "metadata.exif", "This file came through different software from the others",
                f"Its metadata names '{value}', while {len(most)} other images in this case name '{common}'.",
                category=FindingCategory.metadata, confidence=0.5,
                evidence=[EvidenceItem(kind=EvidenceKind.metadata, label="Software across the case", doc_id=doc.id, data={"this_file": value, "other_files": common, "other_file_count": len(most)})],
                benign=["Applicants often gather scans from different devices or apps."],
                verify=["Ask how this file was produced, or request the original."],
                related_doc_ids=[d.id for d in most],
            )
        )
    return findings


def analyze_signatures(docs: list[Document], workdir: Path, case_id: str) -> list[Finding]:
    workdir = Path(workdir)
    findings: list[Finding] = []
    regions: list[SigRegion] = []
    try:
        findings.extend(_software_outliers(docs))
    except Exception as exc:
        log.warning("software comparison failed: %s", type(exc).__name__)
    for doc in docs:
        if not is_processable(doc):
            continue
        try:
            found = find_signatures(doc)
            regions.extend(found)
            doc.metadata["signatures"] = [
                {"page": r.page, "bbox": r.bbox.model_dump(), "label": r.label, "ink_found": r.crop.size > 0}
                for r in found
            ]
            for r in found:
                findings.extend(_placement_findings(r, workdir))
        except Exception as exc:
            log.warning("signature search failed: %s", type(exc).__name__)
            doc.metadata.setdefault("forensics_failures", []).append(f"signatures: {type(exc).__name__}")

    inked = [r for r in regions if r.crop.size > 0]
    hashes = {}
    for i, r in enumerate(inked):
        try:
            hashes[i] = _phash(r.crop)
        except Exception:
            continue
    reported: set[tuple[int, int]] = set()
    for i in hashes:
        for j in hashes:
            if j <= i or (i, j) in reported:
                continue
            a, b = inked[i], inked[j]
            if a.doc.id == b.doc.id and a.page == b.page:
                continue
            distance = hashes[i] - hashes[j]
            # The hash is only a shortcut. It can't rule out a copy whose crop bounds differ.
            if distance > PHASH_MAX_DISTANCE and _native_corr(a.crop, b.crop) < IDENTICAL_CORR and _degraded_corr(a.crop, b.crop) < SOFTENED_IDENTICAL_CORR:
                continue
            corr = _pixel_corr(a.crop, b.crop)
            if corr < IDENTICAL_CORR:
                continue
            reported.add((i, j))
            uri_a = save_crop(load_page_rgb(a.doc, a.page), a.bbox, workdir, a.doc, f"sig_p{a.page}_{int(a.bbox.x0)}_{int(a.bbox.y0)}")
            uri_b = save_crop(load_page_rgb(b.doc, b.page), b.bbox, workdir, b.doc, f"sig_p{b.page}_{int(b.bbox.x0)}_{int(b.bbox.y0)}")
            finding = make_finding(
                b.doc, "visual.signature_reuse", "The same signature pixels appear on two documents",
                f"The signature on '{b.doc.filename}' matches the one on '{a.doc.filename}' at {corr:.3f} pixel correlation. "
                "Pen signatures vary every time they're written, so a near-exact pixel match suggests one image was copied, "
                "unless a shared digital signature image is expected here.",
                status=FindingStatus.POTENTIAL_MANIPULATION, category=FindingCategory.visual, severity=Severity.high,
                confidence=min(0.97, 0.75 + (corr - IDENTICAL_CORR) * 3),
                page=b.page, bbox=b.bbox,
                evidence=[
                    measurement("Signature comparison", b.doc, b.page, b.bbox, phash_distance=int(distance), pixel_correlation=corr),
                    crop_evidence("This signature", uri_b, b.doc, b.page, b.bbox),
                    EvidenceItem(kind=EvidenceKind.comparison, label="Matching signature", uri=uri_a, doc_id=a.doc.id, page=a.page, bbox=a.bbox),
                ],
                benign=[
                    "An organisation may apply one digital signature image to every document it issues.",
                    "Both pages may be copies of one signed original.",
                ],
                verify=[
                    "Ask for a freshly signed original.",
                    "Confirm with the issuer whether it uses a digital signature image.",
                ],
                related_doc_ids=[a.doc.id] if a.doc.id != b.doc.id else [],
            )
            finding.fused_score = finding.confidence
            findings.append(finding)
    for f in findings:
        f.case_id = case_id
    return findings
