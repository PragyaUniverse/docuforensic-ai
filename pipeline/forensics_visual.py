"""Pixel-level forensics. Every detector measures the real page image and reports its numbers.

Individually these signals are weak: text edges, scanners and printers all leave traces that look
like edits. Single findings therefore stay low-confidence observations, and `pipeline.fusion`
decides whether independent signals agree on one region.

Peer comparisons are local to the document itself: a word is compared with words in the same row
or column of the same page. Nothing here uses filenames, field values or ground truth.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy import ndimage as ndi

from models.schemas import BBox, Document, DocFormat, EvidenceItem, EvidenceKind, Finding, FindingCategory, Word
from pipeline.common import (
    clip_bbox,
    crop_evidence,
    expand_bbox,
    heatmap_evidence,
    is_processable,
    load_page_rgb,
    log,
    make_finding,
    measurement,
    save_crop,
    save_heatmap,
    union_bbox,
)
from pipeline.layout import Line, group_lines

BENIGN_SCAN = [
    "Scanner or photocopier artefacts, such as uneven lighting or dust.",
    "Different compression applied by the device or software that produced the file.",
    "Legitimate design elements such as shading, stamps or form boxes.",
]
VERIFY_ORIGINAL = [
    "Compare this region with the original document or an issuer-held copy.",
    "Ask for a fresh copy of the document directly from the issuing organisation.",
]


@dataclass
class PageCtx:
    index: int
    rgb: np.ndarray
    gray: np.ndarray
    ink: np.ndarray  # True on printed or written marks
    word_mask: np.ndarray  # True inside dilated word boxes
    words: list[Word]
    lines: list[Line]
    skew: float
    median_word_h: float

    @property
    def shape(self) -> tuple[int, int]:
        return self.gray.shape[:2]


def build_ctx(doc: Document, page_index: int) -> PageCtx:
    rgb = load_page_rgb(doc, page_index)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = ink_mask(gray)
    word_mask = np.zeros(gray.shape, dtype=bool)
    page = doc.pages[page_index]
    h, w = gray.shape
    for wd in page.words:
        b = clip_bbox(expand_bbox(wd.bbox, 4), w, h)
        word_mask[int(b.y0) : int(b.y1) + 1, int(b.x0) : int(b.x1) + 1] = True
    skew = float((doc.metadata.get("skew_deg") or {}).get(str(page_index), 0.0))
    heights = [wd.bbox.y1 - wd.bbox.y0 for wd in page.words]
    return PageCtx(
        index=page_index, rgb=rgb, gray=gray, ink=ink, word_mask=word_mask, words=page.words,
        lines=group_lines(page.words, skew, page_index), skew=skew,
        median_word_h=float(np.median(heights)) if heights else 30.0,
    )


def ink_mask(gray: np.ndarray) -> np.ndarray:
    """Dark marks relative to the local paper level. Tolerates uneven scanner lighting."""
    small = cv2.resize(gray, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    bg = cv2.GaussianBlur(bg, (0, 0), 3)
    bg = cv2.resize(bg, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    return (bg.astype(np.int16) - gray.astype(np.int16)) > 28


def _robust(values: np.ndarray, floor: float) -> tuple[float, float]:
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med))) * 1.4826
    return med, max(mad, floor)


def _components(mask: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """(x0, y0, x1, y1, area) of connected components in a boolean grid."""
    labels, n = ndi.label(mask)
    out = []
    for i, sl in enumerate(ndi.find_objects(labels), start=1):
        area = int((labels[sl] == i).sum())
        out.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop, area))
    return out


def _grid(values: np.ndarray, valid: np.ndarray, size: int, min_valid: float) -> tuple[np.ndarray, np.ndarray]:
    """Block mean of `values` over valid pixels. Returns (means, block_is_valid)."""
    h, w = values.shape
    gh, gw = h // size, w // size
    v = values[: gh * size, : gw * size].astype(np.float64)
    m = valid[: gh * size, : gw * size].astype(np.float64)
    vs = (v * m).reshape(gh, size, gw, size).sum(axis=(1, 3))
    cs = m.reshape(gh, size, gw, size).sum(axis=(1, 3))
    means = np.divide(vs, cs, out=np.zeros_like(vs), where=cs > 0)
    return means, cs >= min_valid * size * size


# ------------------------------------------------------------------------------------------ ELA
def detect_ela(ctx: PageCtx, doc: Document, workdir: Path, photos: list[BBox]) -> list[Finding]:
    """Error Level Analysis: how much a region changes when recompressed at a fixed quality."""
    ok, enc = cv2.imencode(".jpg", ctx.gray, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        return []
    rec = cv2.imdecode(enc, cv2.IMREAD_GRAYSCALE)
    diff = cv2.absdiff(ctx.gray, rec).astype(np.float32)
    smooth = cv2.GaussianBlur(diff, (0, 0), 2.0)
    scale = max(float(np.percentile(smooth, 99.8)), 1.0)
    uri = save_heatmap(smooth / scale, workdir, doc, "ela", ctx.index)
    heat = heatmap_evidence("ELA heatmap", uri, doc, ctx.index)
    findings: list[Finding] = []

    # Words: residual relative to edge energy, so bold or dense text isn't an outlier by itself.
    grad = np.abs(cv2.Sobel(ctx.gray, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(ctx.gray, cv2.CV_32F, 0, 1))
    records = []
    for wd in ctx.words:
        if len(wd.text) < 3:
            continue
        b = wd.bbox
        x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1) + 1, int(b.y1) + 1
        edge = float(grad[y0:y1, x0:x1].sum())
        if edge < 100:
            continue
        records.append((wd, float(diff[y0:y1, x0:x1].sum()) / edge))
    if len(records) >= 8:
        ratios = np.array([r[1] for r in records])
        med, sigma = _robust(ratios, floor=max(0.0002, 0.08 * float(np.median(ratios))))
        outliers = [(wd, (ratio - med) / sigma, ratio) for wd, ratio in records if abs(ratio - med) / sigma >= 6.0]
        outliers.sort(key=lambda t: -abs(t[1]))
        for wd, z, ratio in outliers[:3]:
            conf = min(0.5, 0.2 + abs(z) / 40.0)
            crop = save_crop(ctx.rgb, wd.bbox, workdir, doc, f"ela_w_p{ctx.index}_{int(wd.bbox.x0)}_{int(wd.bbox.y0)}")
            findings.append(
                make_finding(
                    doc, "visual.ela", "Compression response differs for this text",
                    f"The text '{wd.text}' responds to recompression differently from other words on the page "
                    f"({abs(z):.1f} robust deviations). Text edited in after the page was created can behave this way, "
                    "but ELA alone is weak evidence on printed text.",
                    confidence=conf, page=ctx.index, bbox=wd.bbox,
                    evidence=[
                        measurement("ELA per unit of edge energy", doc, ctx.index, wd.bbox, word_ratio=ratio, page_median=med, robust_z=float(z), quality=90),
                        crop_evidence("Region", crop, doc, ctx.index, wd.bbox), heat,
                    ],
                    benign=BENIGN_SCAN, verify=VERIFY_ORIGINAL,
                )
            )

    # Background: residual where there should be only paper.
    valid = ~(cv2.dilate(ctx.ink.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) | ctx.word_mask)
    for p in photos:
        valid[int(max(p.y0, 0)) : int(p.y1), int(max(p.x0, 0)) : int(p.x1)] = False
    means, ok_blocks = _grid(diff, valid, 16, 0.7)
    if ok_blocks.sum() > 50:
        med, sigma = _robust(means[ok_blocks], floor=0.25)
        mask = ok_blocks & (means > med + 6 * sigma)
        comps = [c for c in _components(mask) if c[4] >= 6]
        comps.sort(key=lambda c: -c[4])
        for x0, y0, x1, y1, area in comps[:2]:
            box = BBox(x0=x0 * 16, y0=y0 * 16, x1=x1 * 16, y1=y1 * 16)
            level = float(means[y0:y1, x0:x1].max())
            findings.append(
                make_finding(
                    doc, "visual.ela", "Background compresses differently here",
                    "This background area carries more recompression error than the rest of the paper. "
                    "That can indicate pasted content, or simply a stain or a printed texture.",
                    confidence=min(0.45, 0.2 + area / 400.0), page=ctx.index, bbox=box,
                    evidence=[
                        measurement("Background ELA", doc, ctx.index, box, region_max=level, page_median=med, sigma=sigma, blocks=area),
                        heat,
                    ],
                    benign=BENIGN_SCAN, verify=VERIFY_ORIGINAL,
                )
            )
    return findings


# ---------------------------------------------------------------------------------- noise residual
def _noise_map(ctx: PageCtx, block: int = 24) -> tuple[np.ndarray, np.ndarray]:
    gray = ctx.gray.astype(np.float32)
    hp = gray - cv2.GaussianBlur(gray, (0, 0), 1.6)
    valid = ~(cv2.dilate(_structure_mask(ctx), np.ones((9, 9), np.uint8)).astype(bool))
    means, ok = _grid(hp * hp, valid, block, 0.55)
    return np.sqrt(means), ok


def _structure_mask(ctx: PageCtx) -> np.ndarray:
    """Ink plus faint structure (watermarks, hairlines, shading edges), which isn't paper grain."""
    smooth = cv2.GaussianBlur(ctx.gray.astype(np.float32), (0, 0), 1.5)
    grad = np.abs(cv2.Sobel(smooth, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(smooth, cv2.CV_32F, 0, 1))
    return (ctx.ink | (grad > 7.0)).astype(np.uint8)


def detect_noise(ctx: PageCtx, doc: Document, workdir: Path, photos: list[BBox]) -> list[Finding]:
    """Paper and sensor noise should be statistically even; a foreign patch usually isn't."""
    block = 24
    noise, ok = _noise_map(ctx, block)
    if ok.sum() < 40:
        return []
    logn = np.log(np.maximum(noise, 0.05))
    med, sigma = _robust(logn[ok], floor=0.12)
    z = np.where(ok, (logn - med) / sigma, 0.0)
    heat = np.zeros(ctx.shape, dtype=np.float32)
    up = cv2.resize(np.abs(z).astype(np.float32), (ctx.shape[1] // block * block, ctx.shape[0] // block * block), interpolation=cv2.INTER_NEAREST)
    heat[: up.shape[0], : up.shape[1]] = np.clip(up / 8.0, 0, 1)
    uri = save_heatmap(heat, workdir, doc, "noise", ctx.index)
    evidence_heat = heatmap_evidence("Noise residual inconsistency", uri, doc, ctx.index)

    findings: list[Finding] = []
    # On a noiseless (digitally rendered) page "too quiet" isn't informative.
    paper_noise = math.exp(med)
    mask = np.abs(z) >= 5.5
    if paper_noise < 0.25:
        mask = z >= 5.5
    comps = [c for c in _components(mask) if c[4] >= 3]
    comps.sort(key=lambda c: -c[4])
    for x0, y0, x1, y1, area in comps[:4]:
        box = BBox(x0=x0 * block, y0=y0 * block, x1=x1 * block, y1=y1 * block)
        if any(_overlap_ratio(box, p) > 0.5 for p in photos):
            continue
        # Long thin bands follow rows or rules; a paste is a compact block.
        if (x1 - x0) * block > 0.4 * ctx.shape[1] or (x1 - x0) > 9 * max(y1 - y0, 1):
            continue
        if area / max((x1 - x0) * (y1 - y0), 1) < 0.35:
            continue
        region = float(np.median(noise[y0:y1, x0:x1][ok[y0:y1, x0:x1]])) if ok[y0:y1, x0:x1].any() else 0.0
        peak = float(np.abs(z[y0:y1, x0:x1]).max())
        conf = min(0.7, 0.25 + peak / 25.0 + min(area, 30) / 150.0)
        direction = "quieter" if region < paper_noise else "noisier"
        findings.append(
            make_finding(
                doc, "visual.noise", f"Background is {direction} than the surrounding paper",
                f"The fine grain in this area is {direction} than the rest of the page "
                f"({region:.2f} vs {paper_noise:.2f} grey levels). Content pasted or painted in often carries different noise.",
                confidence=conf, page=ctx.index, bbox=box,
                evidence=[
                    measurement("Noise residual", doc, ctx.index, box, region_noise=region, page_noise=paper_noise, peak_robust_z=peak, blocks=area),
                    evidence_heat,
                ],
                benign=BENIGN_SCAN, verify=VERIFY_ORIGINAL,
            )
        )
    return findings


def _overlap_ratio(a: BBox, b: BBox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    if w <= 0 or h <= 0 or a.area <= 0:
        return 0.0
    return w * h / a.area


# -------------------------------------------------------------------------------- overwrite patches
def detect_overwrite(ctx: PageCtx, doc: Document, workdir: Path, photos: list[BBox]) -> list[Finding]:
    """A value painted over usually sits on a small rectangle of slightly different paper."""
    block = 6
    gray = ctx.gray.astype(np.float32)
    valid = ~(cv2.dilate(_structure_mask(ctx), np.ones((5, 5), np.uint8)).astype(bool))
    means, ok = _grid(gray, valid, block, 0.35)
    if ok.sum() < 200:
        return _local_grain_patches(ctx, doc, workdir, photos)
    filled = means.copy()
    global_med = float(np.median(means[ok]))
    filled[~ok] = global_med
    # Page-local paper level, ignoring small features. Smooth illumination changes cancel out.
    local = ndi.median_filter(filled[::2, ::2], size=41, mode="nearest")
    local = cv2.resize(local.astype(np.float32), (filled.shape[1], filled.shape[0]), interpolation=cv2.INTER_LINEAR)
    dev = filled - local
    sigma = max(_robust(dev[ok], floor=0.25)[1], 0.25)
    thresh = max(1.6, 4.5 * sigma)
    mask = ok & (np.abs(dev) >= thresh)
    mask = ndi.binary_closing(mask, structure=np.ones((3, 3)), iterations=2)

    # Local grain, to compare the inside of a patch with the paper around it.
    hp = gray - cv2.GaussianBlur(gray, (0, 0), 1.6)
    grain, _ = _grid(hp * hp, valid, block, 0.35)
    grain = np.sqrt(grain)

    heat = np.zeros(ctx.shape, dtype=np.float32)
    up = cv2.resize(np.abs(dev).astype(np.float32), (filled.shape[1] * block, filled.shape[0] * block), interpolation=cv2.INTER_NEAREST)
    heat[: up.shape[0], : up.shape[1]] = np.clip(up / max(thresh * 3, 1), 0, 1) * (up >= thresh)

    h, w = ctx.shape
    candidates = []
    for x0, y0, x1, y1, area in _components(mask):
        bw, bh = (x1 - x0) * block, (y1 - y0) * block
        box = BBox(x0=x0 * block, y0=y0 * block, x1=x1 * block, y1=y1 * block)
        if bw < 24 or bh < 14 or area < 12:
            continue
        # Bands across most of the page and large panels are layout, not local edits.
        if bw > 0.45 * w or bh > 0.2 * h:
            continue
        if any(_overlap_ratio(box, p) > 0.3 for p in photos):
            continue
        fill = area / max((x1 - x0) * (y1 - y0), 1)
        if fill < 0.55:
            continue
        inside = dev[y0:y1, x0:x1][ok[y0:y1, x0:x1]]
        if inside.size < 8:
            continue
        delta = float(np.median(inside))
        if abs(delta) > 45:  # strong shading is a designed element
            continue
        candidates.append((x0, y0, x1, y1, box, fill, delta))

    # Repeated same-sized, same-tone boxes are form design rather than local edits.
    def is_design(c) -> bool:
        peers = 0
        for o in candidates:
            if o is c:
                continue
            same_h = abs((o[4].y1 - o[4].y0) - (c[4].y1 - c[4].y0)) <= 12
            same_tone = abs(o[6] - c[6]) <= 1.5
            same_edge = abs(o[4].x0 - c[4].x0) <= 12 or abs(o[4].y0 - c[4].y0) <= 12
            if same_h and same_tone and same_edge:
                peers += 1
        return peers >= 2

    findings: list[Finding] = _local_grain_patches(ctx, doc, workdir, photos)
    uri = None
    ranked = sorted(candidates, key=lambda c: -abs(c[6]) * c[5])
    for c in ranked[:6]:
        if is_design(c):
            continue
        x0, y0, x1, y1, box, fill, delta = c
        words_in = [wd for wd in ctx.words if _overlap_ratio(wd.bbox, box) > 0.5]
        if not words_in:
            continue
        pad = 5
        ring = np.zeros_like(ok)
        ring[max(y0 - pad, 0) : y1 + pad, max(x0 - pad, 0) : x1 + pad] = True
        ring[y0:y1, x0:x1] = False
        ring &= ok
        if ring.sum() < 8:
            continue
        inside_grain = float(np.median(grain[y0:y1, x0:x1][ok[y0:y1, x0:x1]]))
        ring_grain = float(np.median(grain[ring]))
        grain_ratio = (inside_grain + 0.05) / (ring_grain + 0.05)
        conf = 0.45 + min(abs(delta) / 12.0, 0.25) + min((fill - 0.55), 0.15)
        if grain_ratio < 0.6 or grain_ratio > 1.6:
            conf += 0.15
        conf = min(conf, 0.92)
        text = " ".join(wd.text for wd in sorted(words_in, key=lambda z: z.bbox.x0))[:60]
        if uri is None:
            uri = save_heatmap(heat, workdir, doc, "background", ctx.index)
        crop = save_crop(ctx.rgb, box, workdir, doc, f"overwrite_p{ctx.index}_{int(box.x0)}_{int(box.y0)}", margin=30)
        findings.append(
            make_finding(
                doc, "visual.overwrite", "Text sits on a patch of different background",
                f"The text '{text}' sits on a rectangular patch whose background differs from the surrounding paper by "
                f"{abs(delta):.1f} grey levels, with grain {grain_ratio:.2f}x that of the area around it. "
                "This pattern fits a value painted over and retyped, and needs checking against the original.",
                confidence=conf, page=ctx.index, bbox=box,
                evidence=[
                    measurement("Background patch", doc, ctx.index, box, delta_grey=delta, rectangularity=fill, grain_ratio=grain_ratio, paper_sigma=sigma),
                    crop_evidence("Patch and surroundings", crop, doc, ctx.index, box),
                    heatmap_evidence("Background deviation", uri, doc, ctx.index),
                ],
                benign=[
                    "A printed highlight or shaded box that is part of the form design.",
                    "A correction made and countersigned by the issuer.",
                    "Scanner lighting or a sticker on the paper.",
                ],
                verify=["Compare the value with the issuer's records.", *VERIFY_ORIGINAL],
            )
        )
    return findings


def _local_grain_patches(ctx: PageCtx, doc: Document, workdir: Path, photos: list[BBox]) -> list[Finding]:
    """Paper grain right behind a value compared with the paper just around it. A background patch
    can match the paper's brightness closely and still give itself away by being too smooth."""
    gray = ctx.gray.astype(np.float32)
    hp = gray - cv2.GaussianBlur(gray, (0, 0), 1.6)
    struct = cv2.dilate(_structure_mask(ctx), np.ones((3, 3), np.uint8)).astype(bool)
    overall = float(np.std(hp[~struct])) if (~struct).any() else 0.0
    if overall < 0.5:  # a noiseless page has no grain to compare
        return []
    h, w = ctx.shape
    fields = [f for f in doc.fields if f.page == ctx.index]
    results: list[tuple[float, BBox, Word, float, float, float]] = []
    for wd in ctx.words:
        is_value = any(c.isdigit() for c in wd.text) or any(_overlap_ratio(wd.bbox, f.bbox) > 0.5 for f in fields)
        if not is_value or len(wd.text) < 3 or any(_overlap_ratio(wd.bbox, p) > 0.3 for p in photos):
            continue
        b = wd.bbox
        x0, y0, x1, y1 = int(b.x0) - 8, int(b.y0) - 8, int(b.x1) + 9, int(b.y1) + 9
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
        inner = struct[y0:y1, x0:x1]
        pad = 26
        rx0, ry0, rx1, ry1 = max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, w), min(y1 + pad, h)
        ring = np.zeros((ry1 - ry0, rx1 - rx0), dtype=bool)
        ring[:] = True
        ring[y0 - ry0 - 4 if y0 - ry0 > 4 else 0 : y1 - ry0 + 4, x0 - rx0 - 4 if x0 - rx0 > 4 else 0 : x1 - rx0 + 4] = False
        ring &= ~struct[ry0:ry1, rx0:rx1]
        clear = ~inner
        if clear.sum() < 500 or ring.sum() < 500:
            continue
        inside_std = float(np.std(hp[y0:y1, x0:x1][clear]))
        ring_std = float(np.std(hp[ry0:ry1, rx0:rx1][ring]))
        ratio = inside_std / max(ring_std, 0.1)
        if ratio <= 0.78 and ring_std > 0.5:
            delta = float(gray[y0:y1, x0:x1][clear].mean() - gray[ry0:ry1, rx0:rx1][ring].mean())
            box = BBox(x0=x0, y0=y0, x1=x1, y1=y1)
            results.append((ratio, box, wd, inside_std, ring_std, delta))
    results.sort(key=lambda r: r[0])
    findings: list[Finding] = []
    for ratio, box, wd, inside_std, ring_std, delta in results[:3]:
        crop = save_crop(ctx.rgb, box, workdir, doc, f"grain_p{ctx.index}_{int(box.x0)}_{int(box.y0)}", margin=30)
        findings.append(
            make_finding(
                doc, "visual.overwrite", "Paper behind this value is smoother than the paper around it",
                f"The paper grain behind '{wd.text}' is {ratio:.2f}x that of the paper just around it ({inside_std:.2f} vs {ring_std:.2f}). "
                "That fits a patch laid over the original value, since a patch doesn't carry the page's grain.",
                confidence=min(0.85, 0.5 + (0.78 - ratio) * 1.5), page=ctx.index, bbox=box,
                evidence=[
                    measurement("Local grain", doc, ctx.index, box, inner_grain=inside_std, surrounding_grain=ring_std, grain_ratio=ratio, delta_grey=delta),
                    crop_evidence("Value and surrounding paper", crop, doc, ctx.index, box),
                ],
                benign=["A sticker, correction tape or a smudge on the paper.", "Uneven scanner response."],
                verify=["Compare the value with the issuer's records.", *VERIFY_ORIGINAL],
            )
        )
    return findings


# ------------------------------------------------------------------------------ typography features
@dataclass
class WordStyle:
    word: Word
    numeric: bool
    stroke: float
    height: float
    width_per_char: float
    darkness: float
    chroma: float
    slant: float
    sharpness: float
    row: int
    baseline: float


def _slant_deg(binary: np.ndarray) -> float:
    """Dominant stroke slant: the shear that makes vertical strokes line up best."""
    h, w = binary.shape
    if h < 8 or w < 8:
        return 0.0
    best, best_score = 0.0, -1.0
    ys = np.arange(h, dtype=np.float32) - h / 2
    yy, xx = np.nonzero(binary)
    if len(xx) < 20:
        return 0.0
    for angle in np.arange(-20, 21, 4):
        shift = xx + (yy - h / 2) * math.tan(math.radians(float(angle)))
        hist, _ = np.histogram(shift, bins=w + h, range=(-h, w + h))
        score = float((hist.astype(np.float64) ** 2).sum())
        if score > best_score:
            best, best_score = float(angle), score
    _ = ys
    return best


def word_style(ctx: PageCtx, wd: Word, row: int) -> WordStyle | None:
    h, w = ctx.shape
    b = clip_bbox(expand_bbox(wd.bbox, 2), w, h)
    x0, y0, x1, y1 = int(b.x0), int(b.y0), int(b.x1) + 1, int(b.y1) + 1
    if x1 - x0 < 6 or y1 - y0 < 6:
        return None
    crop = ctx.gray[y0:y1, x0:x1]
    t, binary = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ink = binary > 0
    frac = ink.mean()
    if frac < 0.03 or frac > 0.75:
        return None
    if int(crop.max()) - int(crop.min()) < 40:
        return None
    rows = np.nonzero(ink.any(axis=1))[0]
    cols = np.nonzero(ink.any(axis=0))[0]
    if len(rows) < 4 or len(cols) < 4:
        return None
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    ridge = dist[ink]
    stroke = float(np.percentile(ridge, 85)) * 2.0
    core = crop[dist >= max(float(np.percentile(ridge, 60)), 0.5)]
    darkness = float(np.median(core)) if core.size else float(np.median(crop[ink]))
    rgb_crop = ctx.rgb[y0:y1, x0:x1].astype(np.float32)
    chroma = float(np.median((rgb_crop.max(axis=2) - rgb_crop.min(axis=2))[ink]))
    gy = cv2.Sobel(crop, cv2.CV_32F, 0, 1)
    gx = cv2.Sobel(crop, cv2.CV_32F, 1, 0)
    mag = np.sqrt(gx * gx + gy * gy)
    contrast = max(float(np.median(crop[~ink])) - darkness, 10.0) if (~ink).any() else 40.0
    sharpness = float(np.percentile(mag, 97)) / contrast
    text = wd.text
    digits = sum(c.isdigit() for c in text)
    return WordStyle(
        word=wd, numeric=digits >= max(1, 0.5 * len(text)), stroke=stroke,
        height=float(rows[-1] - rows[0] + 1),
        width_per_char=float(cols[-1] - cols[0] + 1) / max(len(text), 1),
        darkness=darkness, chroma=chroma, slant=_slant_deg(ink), sharpness=sharpness, row=row,
        baseline=float(y0 + rows[-1] + 1),
    )


def collect_styles(ctx: PageCtx) -> list[WordStyle]:
    styles = []
    for ri, line in enumerate(ctx.lines):
        for wd in line.words:
            alnum = sum(c.isalnum() for c in wd.text)
            if alnum < 2:
                continue
            s = word_style(ctx, wd, ri)
            if s:
                styles.append(s)
    return styles


def _style_deviation(s: WordStyle, peers: list[WordStyle]) -> dict[str, float]:
    """Per-feature deviation from the peers' medians, 0 when within normal variation."""
    def med(attr: str) -> float:
        return float(np.median([getattr(p, attr) for p in peers]))

    dev: dict[str, float] = {}
    dev["stroke"] = max(0.0, abs(s.stroke / max(med("stroke"), 1.0) - 1.0) - 0.30) / 0.30
    dev["height"] = max(0.0, abs(s.height / max(med("height"), 1.0) - 1.0) - 0.16) / 0.16
    dev["width"] = max(0.0, abs(s.width_per_char / max(med("width_per_char"), 1.0) - 1.0) - 0.22) / 0.22
    dev["chroma"] = max(0.0, abs(s.chroma - med("chroma")) - 14.0) / 14.0
    dev["slant"] = max(0.0, abs(s.slant - med("slant")) - 6.0) / 6.0
    return dev


def _ink_profile_deviation(s: WordStyle, styles: list[WordStyle]) -> tuple[float, float, int]:
    """Text produced by one process keeps a steady link between stroke width, ink darkness and edge
    sharpness. Compare with words of similar stroke width. Returns (darkness dev, sharpness dev, n)."""
    peers = [p for p in styles if p is not s and p.row != s.row and abs(p.stroke - s.stroke) <= 0.2 * max(s.stroke, 1.0)]
    if len(peers) < 3:
        return 0.0, 0.0, len(peers)
    dark = float(np.median([p.darkness for p in peers]))
    sharp = float(np.median([p.sharpness for p in peers]))
    d = max(0.0, abs(s.darkness - dark) - 10.0) / 10.0
    q = max(0.0, abs(s.sharpness / max(sharp, 0.1) - 1.0) - 0.12) / 0.12
    return d, q, len(peers)


def _matches_a_style(s: WordStyle, styles: list[WordStyle]) -> bool:
    """True if at least three other words on the page share this word's look: a template style."""
    count = 0
    for p in styles:
        if p is s or p.numeric != s.numeric:
            continue
        if (
            abs(p.stroke / max(s.stroke, 1.0) - 1.0) <= 0.28
            and abs(p.height / max(s.height, 1.0) - 1.0) <= 0.16
            and abs(p.darkness - s.darkness) <= 10
            and abs(p.chroma - s.chroma) <= 12
            and abs(p.slant - s.slant) <= 6
            and abs(p.sharpness / max(s.sharpness, 0.1) - 1.0) <= 0.12
        ):
            count += 1
            if count >= 3:
                return True
    return False


def detect_font_consistency(
    ctx: PageCtx, doc: Document, workdir: Path, styles: list[WordStyle], pdf_fonts: dict | None = None
) -> list[Finding]:
    """A value that looks unlike its row, column and every other style on the page.

    Only values are examined (numeric words and extracted fields), since those are what an edit
    would change. Headings and footers have their own looks by design.
    """
    if len(styles) < 8:
        return []
    fields = [f for f in doc.fields if f.page == ctx.index]
    by_row: dict[int, list[WordStyle]] = {}
    for s in styles:
        by_row.setdefault(s.row, []).append(s)
    flagged: list[tuple[WordStyle, float, dict[str, float], int]] = []
    for s in styles:
        is_value = s.numeric or any(_overlap_ratio(s.word.bbox, f.bbox) > 0.5 for f in fields)
        if not is_value or _matches_a_style(s, styles):
            continue
        cx = (s.word.bbox.x0 + s.word.bbox.x1) / 2
        peers = [
            p for p in styles
            if p is not s and p.numeric == s.numeric and p.row != s.row
            and abs(p.word.bbox.y0 - s.word.bbox.y0) < 0.45 * ctx.shape[0]
            and (p.word.bbox.x0 - 60 <= cx <= p.word.bbox.x1 + 60 or abs((p.word.bbox.x0 + p.word.bbox.x1) / 2 - cx) < 150)
        ]
        if len(peers) < 3:
            peers = [p for p in styles if p is not s and p.numeric == s.numeric and p.row != s.row]
        if len(peers) < 3:
            continue
        dev = _style_deviation(s, peers)
        # A whole row printed bold or large is design. Discount shape features its mates share.
        mates = [m for m in by_row[s.row] if m is not s]
        for m in mates:
            mp = [p for p in styles if p.numeric == m.numeric and p.row != m.row and p is not m]
            if len(mp) >= 3:
                md = _style_deviation(m, mp)
                for k in list(dev):
                    if md.get(k, 0) > 0.2:
                        dev[k] = 0.0
        # Ink profile comes last: it isn't explained by a row being bold or large.
        ink_dark, ink_sharp, n_ink = _ink_profile_deviation(s, styles)
        dev["ink_darkness"] = ink_dark
        dev["edge_sharpness"] = ink_sharp
        strong = {k: v for k, v in dev.items() if v > 0}
        score = sum(min(v, 2.0) for v in strong.values())
        has_ink = dev["ink_darkness"] > 0 or dev["edge_sharpness"] > 0
        # Shape alone is common in templates, so it needs to be much further out to be reported.
        if (has_ink and score >= 0.9 and len(strong) >= 2) or (not has_ink and score >= 3.0):
            flagged.append((s, score, dev, len(peers)))

    findings: list[Finding] = []
    flagged.sort(key=lambda t: (t[0].row, t[0].word.bbox.x0))
    groups: list[list[tuple[WordStyle, float, dict[str, float], int]]] = []
    for item in flagged:
        if groups and groups[-1][-1][0].row == item[0].row and item[0].word.bbox.x0 - groups[-1][-1][0].word.bbox.x1 < 3 * ctx.median_word_h:
            groups[-1].append(item)
        else:
            groups.append([item])
    groups.sort(key=lambda g: -max(i[1] for i in g))
    for group in groups[:4]:
        box = union_bbox([i[0].word.bbox for i in group])
        top = max(group, key=lambda i: i[1])
        s, score, dev, n_peers = top
        features = [k for k, v in dev.items() if v > 0]
        has_ink = "ink_darkness" in features or "edge_sharpness" in features
        conf = min(0.88, 0.35 + score / 5.0) if has_ink else min(0.4, 0.2 + score / 20.0)
        crop = save_crop(ctx.rgb, box, workdir, doc, f"font_p{ctx.index}_{int(box.x0)}_{int(box.y0)}", margin=24)
        text = " ".join(i[0].word.text for i in group)
        findings.append(
            make_finding(
                doc, "visual.font_consistency", "Typography differs from other text on the page",
                f"'{text}' doesn't match comparable text or any style used elsewhere on this page. It differs in: {', '.join(features)}. "
                "A value typed in later often uses a different font, weight or ink.",
                confidence=conf, page=ctx.index, bbox=box,
                evidence=[
                    measurement(
                        "Word style against peers", doc, ctx.index, box,
                        stroke_width=s.stroke, height_px=s.height, width_per_char=s.width_per_char,
                        darkness=s.darkness, chroma=s.chroma, slant_deg=s.slant, edge_sharpness=s.sharpness,
                        peers=n_peers, deviating_features=features, score=score,
                    ),
                    crop_evidence("Word in context", crop, doc, ctx.index, box),
                ],
                benign=[
                    "Bold or emphasized printing that is part of the template.",
                    "Handwritten or stamped fill-in on a printed form.",
                    "A template that mixes fonts by design.",
                ],
                verify=["Compare with another document issued from the same template.", *VERIFY_ORIGINAL],
            )
        )
    return findings


def detect_alignment(ctx: PageCtx, doc: Document, styles: list[WordStyle]) -> list[Finding]:
    """A lone word off its row's baseline, or a value just missing its column's edge."""
    findings: list[Finding] = []
    tan = math.tan(math.radians(ctx.skew))
    by_row: dict[int, list[WordStyle]] = {}
    for s in styles:
        by_row.setdefault(s.row, []).append(s)

    for row, items in by_row.items():
        if len(items) < 4:
            continue
        adj = [s.baseline - tan * (s.word.bbox.x0 + s.word.bbox.x1) / 2 for s in items]
        med = float(np.median(adj))
        h = float(np.median([s.height for s in items]))
        limit = max(5.0, 0.28 * h)
        off = [(s, a - med) for s, a in zip(items, adj) if abs(a - med) >= limit and not (a > med and any(c in s.word.text for c in "gjpqy,;()"))]
        if len(off) != 1:  # several words off together means the row grouping, not an edit
            continue
        s, offset = off[0]
        findings.append(
            make_finding(
                doc, "visual.alignment", "Word sits off the baseline of its row",
                f"'{s.word.text}' sits {abs(offset):.1f}px {'below' if offset > 0 else 'above'} the baseline shared by its row.",
                confidence=min(0.4, 0.2 + abs(offset) / max(2 * h, 1.0)), page=ctx.index, bbox=s.word.bbox,
                category=FindingCategory.visual,
                evidence=[measurement("Baseline offset", doc, ctx.index, s.word.bbox, offset_px=offset, row_height_px=h, row_words=len(items))],
                benign=["Slight paper movement while scanning.", "Handwritten or stamped entries."],
                verify=VERIFY_ORIGINAL,
            )
        )

    # Column edges. Labelled values define a left edge; numbers in a column define a right edge.
    def deskew_x(x: float, y: float) -> float:
        return x + tan * y

    left: list[tuple[float, Word]] = []
    right: list[tuple[float, Word]] = []
    for line in ctx.lines:
        ws = line.words
        for i in range(1, len(ws)):
            gap = ws[i].bbox.x0 - ws[i - 1].bbox.x1
            if gap < 1.5 * line.height:
                continue
            digits = sum(c.isdigit() for c in ws[i].text)
            if digits >= 0.6 * len(ws[i].text) and ("." in ws[i].text or "," in ws[i].text):
                right.append((deskew_x(ws[i].bbox.x1, ws[i].bbox.y0), ws[i]))
            elif digits == 0:
                left.append((deskew_x(ws[i].bbox.x0, ws[i].bbox.y0), ws[i]))

    reported: list[Finding] = []
    for coords, edge in ((left, "left"), (right, "right")):
        if len(coords) < 5:
            continue
        xs = np.array([c[0] for c in coords])
        for x, wd in coords:
            near = xs[np.abs(xs - x) < 24]
            if len(near) < 5:
                continue
            mode = float(np.median(near))
            spread = float(np.median(np.abs(near - mode)))
            off = x - mode
            if abs(off) >= max(8.0, 3.5 * spread + 5.0) and spread <= 2.5:
                reported.append(
                    make_finding(
                        doc, "visual.alignment", "Value is off its column edge",
                        f"'{wd.text}' is {abs(off):.1f}px away from the {edge} edge that {len(near) - 1} other values on this page share.",
                        confidence=min(0.4, 0.2 + abs(off) / 60.0), page=ctx.index, bbox=wd.bbox,
                        evidence=[measurement("Column alignment", doc, ctx.index, wd.bbox, offset_px=off, column_edge_px=mode, column_spread_px=spread, peers=int(len(near) - 1), edge=edge)],
                        benign=["Template with mixed alignment.", "Slight paper movement while scanning."],
                        verify=VERIFY_ORIGINAL,
                    )
                )
    reported.sort(key=lambda f: -f.confidence)
    return findings[:3] + reported[:3]


# ------------------------------------------------------------------------------------- copy-move
def _align_compare(ctx: PageCtx, hp: np.ndarray, struct: np.ndarray, a: BBox, b: BBox) -> dict | None:
    """Best small alignment of box a over box b; pixel and noise agreement at that alignment."""
    h, w = ctx.shape
    x0, y0, x1, y1 = int(a.x0), int(a.y0) - 4, int(a.x1), int(a.y1) + 4
    bw, bh = x1 - x0, y1 - y0
    bx, by = int(b.x0), int(b.y0) - 4
    if x0 < 0 or y0 < 0 or x1 > w or y1 > h or bw < 20 or bh < 8:
        return None
    pad_x, pad_y = 3, 5
    sx0, sy0 = max(bx - pad_x, 0), max(by - pad_y, 0)
    sx1, sy1 = min(bx + bw + pad_x, w), min(by + bh + pad_y, h)
    if sx1 - sx0 < bw or sy1 - sy0 < bh:
        return None
    template = ctx.gray[y0:y1, x0:x1]
    if template.std() < 2:
        return None
    scores = cv2.matchTemplate(ctx.gray[sy0:sy1, sx0:sx1], template, cv2.TM_CCOEFF_NORMED)
    _, corr, _, loc = cv2.minMaxLoc(scores)
    corr = float(corr)
    u0, v0 = sx0 + loc[0], sy0 + loc[1]
    if corr < 0:
        return None
    pa = template.astype(np.float32)
    pb = ctx.gray[v0 : v0 + bh, u0 : u0 + bw].astype(np.float32)
    mask = ~(struct[y0:y1, x0:x1].astype(bool) | struct[v0 : v0 + bh, u0 : u0 + bw].astype(bool))
    noise = None
    if mask.sum() > 150:
        ha, hb = hp[y0:y1, x0:x1][mask], hp[v0 : v0 + bh, u0 : u0 + bw][mask]
        if ha.std() > 0.2 and hb.std() > 0.2:
            noise = float(np.corrcoef(ha, hb)[0, 1])
    return {"pixel_corr": corr, "mean_abs_diff": float(np.abs(pa - pb).mean()), "noise_corr": noise}


def _repeated_runs(ctx: PageCtx) -> list[tuple[str, BBox, BBox]]:
    """Runs of words printed identically on two different rows of the page."""
    def key(text: str) -> str:
        return text.casefold()

    out: list[tuple[str, BBox, BBox]] = []
    lines = [ln for ln in ctx.lines if len(ln.words) >= 2]
    for i, a in enumerate(lines):
        for b in lines[i + 1 :]:
            ka = [key(w.text) for w in a.words]
            kb = [key(w.text) for w in b.words]
            best = None
            for ai in range(len(ka)):
                for bi in range(len(kb)):
                    n = 0
                    while ai + n < len(ka) and bi + n < len(kb) and ka[ai + n] == kb[bi + n]:
                        n += 1
                    if n >= 2 and (best is None or n > best[2]):
                        best = (ai, bi, n)
            if best is None:
                continue
            ai, bi, n = best
            words_a, words_b = a.words[ai : ai + n], b.words[bi : bi + n]
            text = " ".join(w.text for w in words_a)
            if len(text.replace(" ", "")) < 12:
                continue
            out.append((text, union_bbox([w.bbox for w in words_a]), union_bbox([w.bbox for w in words_b])))
    return out[:500]


def detect_copy_move(ctx: PageCtx, doc: Document, workdir: Path) -> list[Finding]:
    """Cloned regions. Templates repeat text legitimately, so a repeat alone never counts.

    Text: rows with the same words are compared pixel by pixel. Separately printed repeats differ
    in watermark, grain and sub-pixel position; a clone stands out against the page's other repeats.
    Non-text: keypoint translations, confirmed by pixel correlation.
    """
    gray32 = ctx.gray.astype(np.float32)
    hp = gray32 - cv2.GaussianBlur(gray32, (0, 0), 1.6)
    struct = cv2.dilate(_structure_mask(ctx), np.ones((5, 5), np.uint8))
    results: list[dict] = []

    measured = []
    for text, a, b in _repeated_runs(ctx):
        m = _align_compare(ctx, hp, struct, a, b)
        if m:
            measured.append((text, a, b, m))
    if measured:
        diffs = np.array([m["mean_abs_diff"] for *_, m in measured])
        for text, a, b, m in measured:
            others = np.delete(diffs, measured.index((text, a, b, m)))
            typical = float(np.median(others)) if len(others) else None
            noise = m["noise_corr"]
            if m["pixel_corr"] < 0.985 or noise is None or noise < 0.75 or m["mean_abs_diff"] < 0.3:
                continue
            if typical is not None and m["mean_abs_diff"] > 0.5 * typical:
                continue
            if typical is None and noise < 0.9:
                continue
            results.append({"a": a, "b": b, "conf": min(0.93, 0.6 + 0.35 * noise), "kind": "text", "text": text, **m, "typical_repeat_diff": typical})

    results += _keypoint_clones(ctx, hp, struct)
    if not results:
        return []
    results.sort(key=lambda r: -r["conf"])
    heat = np.zeros(ctx.shape, dtype=np.float32)
    for r in results[:3]:
        for bb in (r["a"], r["b"]):
            heat[int(bb.y0) : int(bb.y1), int(bb.x0) : int(bb.x1)] = 0.8
    uri = save_heatmap(heat, workdir, doc, "copy_move", ctx.index)
    findings: list[Finding] = []
    for r in results[:3]:
        a, b = r["a"], r["b"]
        crop_a = save_crop(ctx.rgb, a, workdir, doc, f"clone_a_p{ctx.index}_{int(a.x0)}_{int(a.y0)}")
        crop_b = save_crop(ctx.rgb, b, workdir, doc, f"clone_b_p{ctx.index}_{int(b.x0)}_{int(b.y0)}")
        data = {k: v for k, v in r.items() if k not in ("a", "b", "conf")}
        if r["kind"] == "text":
            detail = (
                f"'{r['text']}' appears twice on this page, and the two copies match at {r['pixel_corr']:.3f} pixel correlation, including "
                f"the background grain ({r['noise_corr']:.2f}). Their mean difference is {r['mean_abs_diff']:.2f} grey levels"
                + (f", against a typical {r['typical_repeat_diff']:.2f} for other repeated text on this page." if r["typical_repeat_diff"] is not None else ".")
            )
        else:
            detail = f"These two non-text regions match at {r['pixel_corr']:.3f} pixel correlation."
        findings.append(
            make_finding(
                doc, "visual.copy_move", "Two regions of this page look copied from one another",
                detail + " One may have been copied onto the other, or a logo or stamp may be repeated by design.",
                confidence=r["conf"], page=ctx.index, bbox=b,
                evidence=[
                    measurement("Clone match", doc, ctx.index, b, **data),
                    EvidenceItem(kind=EvidenceKind.comparison, label="Possible source region", uri=crop_a, doc_id=doc.id, page=ctx.index, bbox=a),
                    crop_evidence("Possible copied region", crop_b, doc, ctx.index, b),
                    heatmap_evidence("Clone map", uri, doc, ctx.index),
                ],
                benign=["A logo, stamp or pattern printed repeatedly by design.", "A genuinely repeated entry that the source system printed identically."],
                verify=["Check this entry against the issuer's records.", *VERIFY_ORIGINAL],
            )
        )
    return findings


def _keypoint_clones(ctx: PageCtx, hp: np.ndarray, struct: np.ndarray) -> list[dict]:
    orb = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, nlevels=4, edgeThreshold=15, patchSize=15, fastThreshold=12)
    # Text is excluded here: repeated glyphs would swamp the voting.
    mask = (~ctx.word_mask).astype(np.uint8) * 255
    kps, desc = orb.detectAndCompute(ctx.gray, mask)
    if desc is None or len(kps) < 40:
        return []
    pts = np.array([k.pt for k in kps], dtype=np.float32)
    knn = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(desc, desc, k=4)
    shifts: dict[tuple[int, int], list[int]] = {}
    for candidates in knn:
        for m in candidates[1:]:
            if m.distance > 24 or m.queryIdx == m.trainIdx:
                continue
            dx, dy = pts[m.trainIdx] - pts[m.queryIdx]
            if dx * dx + dy * dy < 80 * 80 or dy < 0 or (dy == 0 and dx < 0):
                continue
            shifts.setdefault((int(round(float(dx) / 6)), int(round(float(dy) / 6))), []).append(m.queryIdx)
    out: list[dict] = []
    for key, sources in sorted(shifts.items(), key=lambda kv: -len(kv[1]))[:8]:
        unique = sorted(set(sources))
        if len(unique) < 14:
            continue
        src = pts[unique]
        x0, y0 = np.percentile(src, 5, axis=0)
        x1, y1 = np.percentile(src, 95, axis=0)
        if x1 - x0 < 40 or y1 - y0 < 24:
            continue
        a = BBox(x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1))
        b = BBox(x0=float(x0) + key[0] * 6, y0=float(y0) + key[1] * 6, x1=float(x1) + key[0] * 6, y1=float(y1) + key[1] * 6)
        m = _align_compare(ctx, hp, struct, a, b)
        if not m or m["pixel_corr"] < 0.97:
            continue
        if float(ctx.word_mask[int(y0) : int(y1), int(x0) : int(x1)].mean()) > 0.15:
            continue
        strong = m["noise_corr"] is not None and m["noise_corr"] >= 0.7
        out.append({"a": a, "b": b, "conf": 0.88 if strong else 0.5, "kind": "image", "keypoints": len(unique), **m})
    return out


# ------------------------------------------------------------------------------- photo regions
def find_photo_regions(ctx: PageCtx) -> list[BBox]:
    """Non-text rectangles with continuous tones: passport photos and similar images."""
    small = cv2.resize(ctx.rgb, None, fx=0.25, fy=0.25, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY).astype(np.float32)
    paper = float(np.median(gray))
    chroma = small.max(axis=2).astype(np.int16) - small.min(axis=2).astype(np.int16)
    # Mid-tones or colour, both of which are rare on a text page outside of images.
    tone = (np.abs(gray - paper) > 22) & ~(gray < 70)
    mask = tone | (chroma > 25)
    wm = cv2.resize(ctx.word_mask.astype(np.uint8), (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_NEAREST).astype(bool)
    mask = mask & ~wm
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
    mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8)).astype(bool)
    h, w = gray.shape
    out = []
    for x0, y0, x1, y1, area in _components(mask):
        bw, bh = x1 - x0, y1 - y0
        if bw < 25 or bh < 30 or bw > 0.7 * w or bh > 0.6 * h:
            continue
        if area / max(bw * bh, 1) < 0.6:
            continue
        aspect = bw / bh
        if not 0.4 <= aspect <= 1.8:
            continue
        # Flat shaded boxes are not photographs.
        if gray[y0:y1, x0:x1].std() < 8 and chroma[y0:y1, x0:x1].std() < 8:
            continue
        out.append(BBox(x0=x0 * 4, y0=y0 * 4, x1=x1 * 4, y1=y1 * 4))
    return out


def _blockiness(gray: np.ndarray) -> float:
    """JPEG 8x8 grid strength: step across block boundaries over steps elsewhere."""
    if gray.shape[0] < 32 or gray.shape[1] < 32:
        return 1.0
    g = gray.astype(np.float32)
    dx = np.abs(g[:, 1:] - g[:, :-1])
    best = 1.0
    profile = np.array([dx[:, i::8].mean() for i in range(8)])
    if profile.mean() > 0.01:
        best = float(profile.max() / max(np.median(profile), 1e-3))
    return best


def detect_photo_insert(ctx: PageCtx, doc: Document, workdir: Path, photos: list[BBox]) -> list[Finding]:
    """Compare a photo's edge and grain with the paper around it. Each measure is reported."""
    findings: list[Finding] = []
    h, w = ctx.shape
    gray = ctx.gray.astype(np.float32)
    hp = gray - cv2.GaussianBlur(gray, (0, 0), 1.6)
    noise, ok = _noise_map(ctx, 24)
    page_noise = float(np.median(noise[ok])) if ok.any() else 0.0
    page_block = _blockiness(ctx.gray)
    sharp_refs = []
    sobel = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0))
    for wd in ctx.words[:60]:
        b = wd.bbox
        patch = sobel[int(b.y0) : int(b.y1) + 1, int(b.x0) : int(b.x1) + 1]
        if patch.size > 40:
            sharp_refs.append(float(np.percentile(patch, 99.5)))
    for box in photos:
        x0, y0, x1, y1 = int(box.x0), int(box.y0), int(box.x1), int(box.y1)
        inner_margin = 8
        outer = 28
        ring_near = np.zeros(ctx.shape, dtype=bool)
        ring_near[max(y0 - 8, 0) : min(y1 + 8, h), max(x0 - 8, 0) : min(x1 + 8, w)] = True
        ring_near[max(y0 - 2, 0) : min(y1 + 2, h), max(x0 - 2, 0) : min(x1 + 2, w)] = False
        ring_far = np.zeros(ctx.shape, dtype=bool)
        ring_far[max(y0 - outer, 0) : min(y1 + outer, h), max(x0 - outer, 0) : min(x1 + outer, w)] = True
        ring_far[max(y0 - 12, 0) : min(y1 + 12, h), max(x0 - 12, 0) : min(x1 + 12, w)] = False
        clear = ~ctx.ink
        near, far = ring_near & clear, ring_far & clear
        if near.sum() < 100 or far.sum() < 100:
            continue
        halo = float(np.median(gray[near]) - np.median(gray[far]))
        ring_noise = float(np.std(hp[far]))
        ring_near_noise = float(np.std(hp[near]))
        crop = ctx.gray[y0 + inner_margin : y1 - inner_margin, x0 + inner_margin : x1 - inner_margin]
        block = _blockiness(crop)
        # Photo grain: high-pass energy on its smoothest quarter of pixels.
        hp_crop = hp[y0 + inner_margin : y1 - inner_margin, x0 + inner_margin : x1 - inner_margin]
        local = cv2.blur(np.abs(hp_crop), (9, 9))
        smooth = hp_crop[local <= np.percentile(local, 25)]
        photo_noise = float(np.std(smooth)) if smooth.size > 50 else 0.0
        grain_ratio = (photo_noise + 0.1) / (page_noise + 0.1)

        reasons: list[str] = []
        score = 0.0
        if abs(halo) >= 3.0:
            score += min(abs(halo) / 10.0, 0.3)
            reasons.append(f"the paper at its edge differs from nearby paper by {abs(halo):.1f} grey levels")
        if ring_near_noise > 1.8 * max(ring_noise, 0.3) and ring_near_noise > 1.0:
            score += 0.15
            reasons.append(f"edge grain is {ring_near_noise / max(ring_noise, 0.3):.1f}x that of nearby paper")
        if block >= 1.6 and block >= 1.3 * page_block:
            score += min((block - 1.2) / 2.0, 0.3)
            reasons.append(f"it carries a JPEG block pattern (strength {block:.2f}) that the page ({page_block:.2f}) doesn't")
        scanned = doc.format != DocFormat.digital_pdf  # a digital page is assembled, not scanned as one
        if scanned and page_noise > 0.5 and grain_ratio < 0.45:
            score += 0.62 if grain_ratio < 0.2 else 0.3
            reasons.append(f"its smooth areas have almost no grain ({photo_noise:.2f}) while the page has {page_noise:.2f}, so it wasn't scanned with the page")
        elif scanned and page_noise > 0.5 and grain_ratio > 2.5:
            score += 0.3
            reasons.append(f"its grain is {grain_ratio:.2f}x that of the page")
        # Text on the same page shows how blurred the page really is.
        text_sharp = float(np.median([s for s in sharp_refs])) if sharp_refs else None
        photo_edge = float(np.percentile(np.abs(cv2.Sobel(crop.astype(np.float32), cv2.CV_32F, 1, 0)), 99.5))
        if text_sharp and photo_edge > 1.5 * text_sharp:
            score += 0.2
            reasons.append(f"its edges are sharper ({photo_edge:.0f}) than the page's text ({text_sharp:.0f})")
        if not reasons or score < 0.2:
            continue
        crop_uri = save_crop(ctx.rgb, box, workdir, doc, f"photo_p{ctx.index}_{x0}_{y0}", margin=30)
        findings.append(
            make_finding(
                doc, "visual.photo_insert", "Photo differs from the surrounding page",
                "This image region shows signs that it wasn't produced together with the page: " + "; ".join(reasons) + ".",
                confidence=min(0.92, 0.25 + score), page=ctx.index, bbox=box,
                evidence=[
                    measurement("Photo region measurements", doc, ctx.index, box, edge_halo_grey=halo, near_ring_noise=ring_near_noise, far_ring_noise=ring_noise, photo_blockiness=block, page_blockiness=page_block, photo_grain=photo_noise, page_grain=page_noise),
                    crop_evidence("Photo and surroundings", crop_uri, doc, ctx.index, box),
                ],
                benign=[
                    "Photos are often attached or printed separately from the form.",
                    "A digital form that embeds a JPEG photo legitimately.",
                ],
                verify=[
                    "Compare the photo with the one on the applicant's ID document.",
                    "Check the physical original for signs of a replaced photo.",
                ],
            )
        )
    return findings


# ------------------------------------------------------------------------------------- orchestrate
def analyze_visual(doc: Document, workdir: Path) -> list[Finding]:
    if not is_processable(doc):
        return []
    workdir = Path(workdir)
    findings: list[Finding] = []
    failures: list[str] = []
    for page in doc.pages:
        try:
            ctx = build_ctx(doc, page.index)
        except Exception as exc:
            failures.append(f"page {page.index + 1}: {type(exc).__name__}")
            continue
        photos: list[BBox] = []
        try:
            photos = find_photo_regions(ctx)
            doc.metadata.setdefault("photo_regions", {})[str(page.index)] = [p.model_dump() for p in photos]
        except Exception as exc:
            failures.append(f"photo regions: {type(exc).__name__}")
        styles: list[WordStyle] = []
        try:
            styles = collect_styles(ctx)
        except Exception as exc:
            failures.append(f"typography: {type(exc).__name__}")

        steps = [
            ("ELA", lambda: detect_ela(ctx, doc, workdir, photos)),
            ("noise", lambda: detect_noise(ctx, doc, workdir, photos)),
            ("overwrite", lambda: detect_overwrite(ctx, doc, workdir, photos)),
            ("font consistency", lambda: detect_font_consistency(ctx, doc, workdir, styles)),
            ("alignment", lambda: detect_alignment(ctx, doc, styles)),
            ("copy-move", lambda: detect_copy_move(ctx, doc, workdir)),
            ("photo", lambda: detect_photo_insert(ctx, doc, workdir, photos)),
        ]
        for name, step in steps:
            try:
                findings.extend(step())
            except Exception as exc:
                log.warning("%s failed on page %d: %s", name, page.index, type(exc).__name__)
                failures.append(f"{name}: {type(exc).__name__}")
    if failures:
        doc.metadata["forensics_failures"] = failures
    return findings
