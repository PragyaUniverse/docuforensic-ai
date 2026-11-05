"""Investigation dossier: JSON plus a designed PDF with exactly sections 7.1 to 7.6."""
from __future__ import annotations

import io
import logging
from datetime import timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from PIL import Image as PILImage, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, Image, KeepTogether, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)

from audit import chain
from backend import db
from config.settings import settings
from llm import investigator
from models.schemas import (
    BBox, Document, Dossier, DossierDocumentOverview, EvidenceKind, Finding, FindingCategory,
    FindingStatus, ProcessingStatus, RiskLevel, Severity,
)

log = logging.getLogger("docuforensic.dossier")

DISCLAIMER = (
    "This dossier records automated observations for a human reviewer. It is not a determination "
    "about any person or document: every item is an observation, an inconsistency or a hypothesis that "
    "needs verification. OCR values may contain errors. The process is aligned with the principles of "
    "ISO/IEC 27037, 27041, 27042 and NIST SP 800-86; no formal compliance is claimed."
)
BASE_LIMITATIONS = [
    "OCR and text-layer values are unverified readings; check the source region before relying on one.",
    "Forensic signals are heuristic. Re-saving, scanning and compression can produce false positives, "
    "and a skilled edit can leave no signal, so an absence of findings isn't proof of authenticity.",
    "Detectors were tuned and measured on a synthetic dataset, so real documents may perform differently.",
    "Handwriting and languages other than English are not supported.",
    "No external register, issuer or bank was contacted; only the submitted documents were compared.",
    "The risk level orders review work. It is not a probability and not a finding about intent.",
]
_RANK = {Severity.high: 3, Severity.medium: 2, Severity.low: 1, Severity.info: 0}
_STATUS_ORDER = {FindingStatus.POTENTIAL_MANIPULATION: 2, FindingStatus.INCONSISTENCY: 1, FindingStatus.OBSERVATION: 0}


def _sort(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (-_STATUS_ORDER[f.status], -_RANK[f.severity], -f.confidence, f.title))


def _unique(items: list[str], limit: int) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.strip().casefold()
        if key and key not in seen:
            seen.add(key)
            out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def _traceability(findings: list[Finding], docs: dict[str, Document]) -> list[dict[str, Any]]:
    fields = {f.id: f for d in docs.values() for f in d.fields}
    out = []
    for f in _sort(findings):
        linked = []
        for fid in f.related_field_ids:
            field = fields.get(fid)
            if field:
                linked.append({
                    "field_id": field.id, "name": field.name, "value": field.value_raw,
                    "doc_id": field.doc_id, "filename": docs[field.doc_id].filename, "page": field.page,
                    "bbox": field.bbox.model_dump(), "confidence": field.confidence, "source": field.source.value,
                })
        doc = docs.get(f.doc_id or "")
        out.append({
            "finding_id": f.id, "title": f.title, "status": f.status.value, "category": f.category.value,
            "confidence": f.confidence, "detector": f.detector, "doc_id": f.doc_id,
            "filename": doc.filename if doc else None, "page": f.page,
            "bbox": f.bbox.model_dump() if f.bbox else None, "fields": linked,
            "evidence_uris": [e.uri for e in f.evidence if e.uri],
            "review": f.review.decision.value,
        })
    return out


def _modes(findings: list[Finding], summary_mode: str | None = None) -> list[str]:
    modes = []
    for f in findings:
        r = f.reasoning
        modes.append(r.mode if r.mode == "deterministic" else f"{r.mode}:{r.provider}/{r.model}")
    if summary_mode:
        modes.append(summary_mode)
    return sorted(set(modes)) or ["deterministic"]


def build_dossier(case_id: str, fresh_summary: bool = False) -> Dossier:
    case = db.get_case(case_id)
    if case is None:
        raise KeyError(case_id)
    docs = db.list_documents(case_id)
    findings = db.list_findings(case_id)
    by_id = {d.id: d for d in docs}
    active = [d for d in docs if d.status not in (ProcessingStatus.unsupported, ProcessingStatus.failed)]

    previous = None if fresh_summary else db.get_dossier(case_id)
    if previous:
        summary, summary_mode = previous.summary, None
        prior_modes = previous.reasoning_modes
    else:
        summary, provenance = investigator.summarize_case(findings, active, case.risk_level.value)
        summary_mode = "deterministic" if provenance.mode == "deterministic" else \
            f"{provenance.mode}:{provenance.provider}/{provenance.model}"
        prior_modes = []

    limitations = list(BASE_LIMITATIONS)
    for doc in docs:
        if doc.status != ProcessingStatus.ok and doc.status_message:
            limitations.append(f"{doc.filename}: {doc.status_message}")

    ordered = _sort(findings)
    attention = [f for f in ordered if f.status != FindingStatus.OBSERVATION or _RANK[f.severity] >= 2]
    dossier = Dossier(
        case_id=case.id, case_name=case.name, risk_level=case.risk_level,
        requires_human_review=case.requires_human_review, disclaimer=DISCLAIMER,
        overview=[DossierDocumentOverview(
            doc_id=d.id, filename=d.filename, sha256=d.sha256, doc_type=d.doc_type,
            doc_type_confidence=d.doc_type_confidence, format=d.format, pages=len(d.pages), status=d.status,
            status_message=d.status_message) for d in docs],
        extracted={d.id: d.fields for d in docs},
        structure={d.id: d.sections for d in docs},
        tables={d.id: d.tables for d in docs},
        contextual_findings=[f for f in ordered if f.category == FindingCategory.contextual],
        cross_document_findings=[f for f in ordered if f.category == FindingCategory.cross_document],
        missing_or_duplicated={d.id: {"missing": d.missing_fields, "duplicated": d.duplicated_fields} for d in docs},
        visual_findings=[f for f in ordered if f.category in (
            FindingCategory.visual, FindingCategory.structural, FindingCategory.metadata)],
        traceability=_traceability(ordered, by_id),
        summary=summary,
        potential_explanations=_unique([b for f in attention for b in f.benign_alternatives], 12),
        areas_for_verification=_unique([v for f in attention for v in f.recommended_verification], 12),
        limitations=limitations,
        reasoning_modes=sorted(set(_modes(findings, summary_mode)) | set(prior_modes)),
        audit_head_hash=chain.head_hash(),
    )
    db.save_dossier(dossier)
    return dossier


# ------------------------------------------------------------------ PDF
INK = colors.HexColor("#0F172A")
SUBTLE = colors.HexColor("#475569")
MUTED = colors.HexColor("#64748B")
RULE = colors.HexColor("#E2E8F0")
PANEL = colors.HexColor("#F8FAFC")
ACCENT = colors.HexColor("#0F172A")
STATUS_STYLE = {
    "OBSERVATION": (colors.HexColor("#1D4ED8"), colors.HexColor("#DBEAFE"), "Observation"),
    "INCONSISTENCY": (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7"), "Inconsistency"),
    "POTENTIAL_MANIPULATION": (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2"), "Potential manipulation"),
}
BOX_RGB = {"OBSERVATION": (37, 99, 235), "INCONSISTENCY": (217, 119, 6), "POTENTIAL_MANIPULATION": (220, 38, 38)}
RISK_STYLE = {
    RiskLevel.low: (colors.HexColor("#166534"), colors.HexColor("#DCFCE7")),
    RiskLevel.medium: (colors.HexColor("#B45309"), colors.HexColor("#FEF3C7")),
    RiskLevel.high: (colors.HexColor("#B91C1C"), colors.HexColor("#FEE2E2")),
    RiskLevel.undetermined: (colors.HexColor("#475569"), colors.HexColor("#E2E8F0")),
}
PAGE_W, PAGE_H = A4
MARGIN = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName="Helvetica", fontSize=9, leading=12.5, textColor=INK, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)


S = {
    "title": _style("title", fontName="Helvetica-Bold", fontSize=23, leading=27),
    "kicker": _style("kicker", fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=MUTED),
    "h1": _style("h1", fontName="Helvetica-Bold", fontSize=14.5, leading=18, spaceBefore=4, spaceAfter=6),
    "h2": _style("h2", fontName="Helvetica-Bold", fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=4),
    "body": _style("body"),
    "small": _style("small", fontSize=7.8, leading=10.5, textColor=SUBTLE),
    "cell": _style("cell", fontSize=7.8, leading=10.2),
    "cellb": _style("cellb", fontName="Helvetica-Bold", fontSize=7.8, leading=10.2),
    "th": _style("th", fontName="Helvetica-Bold", fontSize=7.2, leading=9.5, textColor=SUBTLE),
    "ftitle": _style("ftitle", fontName="Helvetica-Bold", fontSize=9.6, leading=12.5),
    "bullet": _style("bullet", fontSize=8.4, leading=11.4, leftIndent=9, bulletIndent=0),
    "note": _style("note", fontSize=8, leading=11, textColor=SUBTLE),
}


def _t(value: Any) -> str:
    """Escapes for ReportLab markup and maps characters the base-14 fonts can't draw."""
    text = "" if value is None else str(value)
    for old, new in (("₹", "Rs. "), ("→", "->"), ("≥", ">="), ("≤", "<="), ("≠", "!="), ("✓", "yes")):
        text = text.replace(old, new)
    text = text.encode("cp1252", "replace").decode("cp1252")
    return escape(text)


def _p(value: Any, style: str = "body") -> Paragraph:
    return Paragraph(_t(value), S[style])


_ACRONYMS = {"ifsc": "IFSC", "hra": "HRA", "id": "ID", "pan": "PAN", "pdf": "PDF", "png": "PNG", "jpg": "JPG", "dob": "DOB"}


def _human(value: str) -> str:
    words = value.replace("_", " ").strip().split()
    out = [_ACRONYMS.get(w.lower(), w) for w in words]
    if out and out[0] == words[0]:
        out[0] = out[0].capitalize()
    return " ".join(out)


_LEAD_INS = ("Why it matters:", "Corroboration:", "Cached AI reasoning", "AI reasoning")


def _rich(text: str) -> Paragraph:
    """Finding text with its parts on separate lines, so measurement and interpretation stay apart."""
    markup = _t(text)
    for lead in _LEAD_INS:
        if lead == "AI reasoning" and "Cached AI reasoning" in markup:
            continue
        markup = markup.replace(f" {lead}", f"<br/><b>{lead}</b>")
    return Paragraph(markup, S["body"])


def _pill(text: str, fg, bg, width: float | None = None) -> Table:
    style = _style(f"pill{text}", fontName="Helvetica-Bold", fontSize=7.4, leading=9.5, textColor=fg)
    table = Table([[Paragraph(_t(text), style)]], colWidths=[width] if width else None)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("ROUNDEDCORNERS", [3, 3, 3, 3]),
    ]))
    return table


def _grid(rows: list[list[Any]], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5), ("LINEBELOW", (0, 0), (-1, -1), 0.35, RULE),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), PANEL), ("LINEBELOW", (0, 0), (-1, 0), 0.7, MUTED)]
    table.setStyle(TableStyle(style))
    return table


def _page_file(doc: Document, page: int) -> Path | None:
    if page is None or page < 0 or page >= len(doc.pages):
        return None
    path = Path(doc.pages[page].image_path)
    path = path if path.is_absolute() else Path(settings.data_dir) / path
    return path if path.exists() else None


def _crop_image(doc: Document, page: int, bbox: BBox, status: str, max_w: float, max_h: float = 34 * mm) -> Image | None:
    source = _page_file(doc, page)
    if source is None:
        return None
    try:
        with PILImage.open(source) as im:
            im = im.convert("RGB")
            pad_x, pad_y = 90, 45
            x0, y0 = max(0, int(bbox.x0) - pad_x), max(0, int(bbox.y0) - pad_y)
            x1, y1 = min(im.width, int(bbox.x1) + pad_x), min(im.height, int(bbox.y1) + pad_y)
            if x1 <= x0 or y1 <= y0:
                return None
            crop = im.crop((x0, y0, x1, y1))
            ImageDraw.Draw(crop).rectangle(
                (bbox.x0 - x0, bbox.y0 - y0, bbox.x1 - x0, bbox.y1 - y0), outline=BOX_RGB[status], width=3)
            buf = io.BytesIO()
            crop.save(buf, "PNG", optimize=True)
            buf.seek(0)
            scale = min(max_w / crop.width, max_h / crop.height, 0.55)
            return Image(buf, width=crop.width * scale, height=crop.height * scale)
    except OSError as exc:
        log.warning("crop failed: %s", type(exc).__name__)
        return None


def _evidence_strip(finding: Finding, docs: dict[str, Document]) -> Table | None:
    """Source regions side by side: both sides of a cross-document conflict."""
    regions: list[tuple[Document, int, BBox, str]] = []

    def overlaps_existing(doc_id, page, bbox) -> bool:
        for doc, other_page, other, _ in regions:
            if doc.id == doc_id and other_page == page:
                ix = min(bbox.x1, other.x1) - max(bbox.x0, other.x0)
                iy = min(bbox.y1, other.y1) - max(bbox.y0, other.y0)
                if ix > 0 and iy > 0 and ix * iy / max(min(bbox.area, other.area), 1.0) > 0.3:
                    return True
        return False

    def add(doc_id, page, bbox, label):
        doc = docs.get(doc_id or "")
        if doc and bbox is not None and page is not None and not overlaps_existing(doc_id, page, bbox):
            regions.append((doc, page, bbox, label))

    add(finding.doc_id, finding.page, finding.bbox, "Highlighted region")
    for item in finding.evidence:
        if item.kind in (EvidenceKind.field_ref, EvidenceKind.raw_value):
            value = item.data.get("value") or item.data.get("amount") or item.data.get("stated")
            if value:
                add(item.doc_id, item.page, item.bbox, str(value))
    regions = regions[:3]
    if not regions:
        return None
    cell_w = (CONTENT_W - 16) / max(len(regions), 2)
    images, captions = [], []
    for doc, page, bbox, label in regions:
        img = _crop_image(doc, page, bbox, finding.status.value, cell_w - 8)
        if img is None:
            continue
        images.append(img)
        captions.append(Paragraph(f"<b>{_t(doc.filename)}</b>, page {page + 1}<br/>{_t(label)[:70]}", S["small"]))
    if not images:
        return None
    table = Table([images, captions], colWidths=[cell_w] * len(images), hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return table


def _bullets(items: list[str], limit: int = 5) -> list[Paragraph]:
    return [Paragraph(_t(i), S["bullet"], bulletText="•") for i in items[:limit]]


def _finding_block(finding: Finding, docs: dict[str, Document]) -> list[Any]:
    fg, bg, label = STATUS_STYLE[finding.status.value]
    doc = docs.get(finding.doc_id or "")
    where = f"{doc.filename}, page {finding.page + 1}" if doc and finding.page is not None else (
        doc.filename if doc else "Case level")
    reasoning = finding.reasoning
    mode = "Deterministic reasoning" if reasoning.mode == "deterministic" else (
        f"{'Cached' if reasoning.mode == 'demo_cache' else 'Live'} LLM reasoning, {reasoning.provider}/{reasoning.model}")
    score = f" | fused score {finding.fused_score:.2f}" if finding.fused_score is not None else ""
    meta = (f"{where} | severity {finding.severity.value} | confidence {finding.confidence:.2f}{score} | "
            f"{finding.detector} | {mode}")
    head = Table([[_pill(label, fg, bg), _p(finding.title, "ftitle")]], colWidths=[33 * mm, CONTENT_W - 33 * mm - 10])
    head.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    parts: list[Any] = [head, _p(meta, "small"), Spacer(1, 3), _rich(finding.explanation)]
    strip = _evidence_strip(finding, docs)
    if strip is not None:
        parts += [Spacer(1, 4), strip]
    if finding.benign_alternatives:
        parts += [Spacer(1, 3), _p("Possible benign explanations", "cellb")] + _bullets(finding.benign_alternatives, 4)
    if finding.recommended_verification:
        parts += [Spacer(1, 3), _p("Recommended verification", "cellb")] + _bullets(finding.recommended_verification, 4)
    if finding.review.decision.value != "pending":
        parts += [Spacer(1, 3), _p(
            f"Human review: {finding.review.decision.value} by {finding.review.reviewer or 'reviewer'}"
            + (f" ({finding.review.note})" if finding.review.note else ""), "cellb")]
    box = Table([[parts]], colWidths=[CONTENT_W])
    box.setStyle(TableStyle([
        ("LINEBEFORE", (0, 0), (0, -1), 2.4, fg), ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return [box, Spacer(1, 10)]


def _is_minor(finding: Finding) -> bool:
    return finding.status == FindingStatus.OBSERVATION and _RANK[finding.severity] <= 1


def _minor_table(findings: list[Finding], docs: dict[str, Document]) -> list[Any]:
    """Low-weight observations in compact form. All are listed, with their locations."""
    rows = [[_p(h, "th") for h in ("Observation", "Where", "Conf.", "Measured")]]
    for f in findings:
        doc = docs.get(f.doc_id or "")
        where = doc.filename if doc else "Case level"
        if f.page is not None:
            where += f", p.{f.page + 1}"
        if f.bbox:
            where += f" ({f.bbox.x0:.0f},{f.bbox.y0:.0f})"
        measured = f.explanation.split(" Why it matters:")[0]
        rows.append([_p(f.title, "cell"), _p(where, "cell"), _p(f"{f.confidence:.2f}", "cell"), _p(measured[:200], "cell")])
    return [_grid(rows, [38 * mm, 40 * mm, 11 * mm, CONTENT_W - 89 * mm]), Spacer(1, 8)]


def _page_thumbnails(findings: list[Finding], docs: dict[str, Document]) -> list[Any]:
    """Whole pages with every region highlighted."""
    per_page: dict[tuple[str, int], list[tuple[BBox, str]]] = {}
    for f in findings:
        if f.doc_id in docs and f.page is not None and f.bbox is not None:
            per_page.setdefault((f.doc_id, f.page), []).append((f.bbox, f.status.value))
        for ev in f.evidence:
            if ev.kind == EvidenceKind.field_ref and ev.doc_id in docs and ev.page is not None and ev.bbox:
                per_page.setdefault((ev.doc_id, ev.page), []).append((ev.bbox, f.status.value))
    cards = []
    for (doc_id, page), boxes in per_page.items():
        source = _page_file(docs[doc_id], page)
        if source is None:
            continue
        with PILImage.open(source) as im:
            im = im.convert("RGB")
            draw = ImageDraw.Draw(im)
            for bbox, status in boxes:
                draw.rectangle((bbox.x0 - 3, bbox.y0 - 3, bbox.x1 + 3, bbox.y1 + 3), outline=BOX_RGB[status], width=5)
            im.thumbnail((640, 900))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=78)
            buf.seek(0)
            w = (CONTENT_W - 18) / 3
            image = Image(buf, width=w, height=w * im.height / im.width)
        cards.append([image, Paragraph(f"<b>{_t(docs[doc_id].filename)}</b>, page {page + 1}, "
                                       f"{len(boxes)} highlighted", S["small"])])
    if not cards:
        return [_p("No region-level findings to highlight.", "note")]
    rows = []
    for i in range(0, len(cards), 3):
        row = cards[i:i + 3]
        rows.append(row + [""] * (3 - len(row)))
    table = Table(rows, colWidths=[(CONTENT_W) / 3] * 3)
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    return [table]


class _NumberedCanvas(rl_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved: list[dict] = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFont("Helvetica", 7)
            self.setFillColor(MUTED)
            self.drawRightString(PAGE_W - MARGIN, 10 * mm, f"Page {self._pageNumber} of {total}")
            super().showPage()
        super().save()


def _cover(dossier: Dossier, docs: list[Document], findings: list[Finding]) -> list[Any]:
    fg, bg = RISK_STYLE[dossier.risk_level]
    generated = dossier.generated_at.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")
    counts = {s: sum(1 for f in findings if f.status == s) for s in FindingStatus}
    tile_w = CONTENT_W / 4

    def tile(value: str, label: str, color=INK, back=PANEL) -> Table:
        value_style = _style(f"tile{label}", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=color)
        t = Table([[Paragraph(_t(value), value_style)], [_p(label, "small")]], colWidths=[tile_w - 6])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), back), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
                               ("BOTTOMPADDING", (0, 1), (-1, 1), 7), ("TOPPADDING", (0, 1), (-1, 1), 1)]))
        return t

    tiles = Table([[
        tile(_human(dossier.risk_level.value), "Risk level for review priority", fg, bg),
        tile(str(counts[FindingStatus.POTENTIAL_MANIPULATION]), "Potential manipulation", *STATUS_STYLE["POTENTIAL_MANIPULATION"][:2]),
        tile(str(counts[FindingStatus.INCONSISTENCY]), "Inconsistencies", *STATUS_STYLE["INCONSISTENCY"][:2]),
        tile(str(counts[FindingStatus.OBSERVATION]), "Observations", *STATUS_STYLE["OBSERVATION"][:2]),
    ]], colWidths=[tile_w] * 4)
    tiles.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    review = "Requires human review"
    return [
        _p("DOCUFORENSIC AI  |  INVESTIGATION DOSSIER", "kicker"), Spacer(1, 5),
        _p(dossier.case_name, "title"), Spacer(1, 4),
        _p(f"Case {dossier.case_id}  |  Generated {generated}  |  {len(docs)} document(s)  |  {review}", "small"),
        Spacer(1, 10), tiles, Spacer(1, 9), _p(dossier.disclaimer, "note"), Spacer(1, 12),
    ]


def render_pdf(dossier: Dossier, out: Path) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    docs_list = db.list_documents(dossier.case_id)
    docs = {d.id: d for d in docs_list}
    findings = dossier.contextual_findings + dossier.cross_document_findings + dossier.visual_findings
    story: list[Any] = _cover(dossier, docs_list, findings)

    # 7.1
    story.append(_p("7.1 Document Overview", "h1"))
    rows = [[_p(h, "th") for h in ("Document", "Identifier and SHA-256", "Type", "Format", "Pages", "Status")]]
    for o in dossier.overview:
        status = _human(o.status.value) + (f": {o.status_message}" if o.status_message else "")
        rows.append([
            _p(o.filename, "cellb"), _p(o.doc_id + " " + o.sha256[:16] + "...", "cell"),
            _p(f"{_human(o.doc_type.value)} ({o.doc_type_confidence:.2f})", "cell"), _p(_human(o.format.value), "cell"),
            _p(o.pages, "cell"), _p(status, "cell")])
    story += [_grid(rows, [36 * mm, 38 * mm, 30 * mm, 19 * mm, 12 * mm, CONTENT_W - 135 * mm]), Spacer(1, 12)]

    # 7.2
    story.append(_p("7.2 Extracted Information", "h1"))
    story.append(_p("Readings with their confidence and source location. They are not treated as verified facts.", "note"))
    for o in dossier.overview:
        fields = dossier.extracted.get(o.doc_id, [])
        story.append(CondPageBreak(35 * mm))
        story.append(_p(f"{o.filename} ({_human(o.doc_type.value)})", "h2"))
        if not fields:
            story.append(_p("No fields were extracted from this document.", "note"))
        else:
            rows = [[_p(h, "th") for h in ("Field", "Value", "Conf.", "Source", "Page", "Location (px)")]]
            for f in fields:
                rows.append([_p(_human(f.name), "cell"), _p(f.value_raw, "cell"), _p(f"{f.confidence:.2f}", "cell"),
                             _p(f.source.value.replace("_", " "), "cell"), _p(f.page + 1, "cell"),
                             _p(f"{f.bbox.x0:.0f},{f.bbox.y0:.0f} to {f.bbox.x1:.0f},{f.bbox.y1:.0f}", "cell")])
            story.append(_grid(rows, [38 * mm, CONTENT_W - 112 * mm, 12 * mm, 20 * mm, 10 * mm, 32 * mm]))
        sections = dossier.structure.get(o.doc_id, [])
        tables = dossier.tables.get(o.doc_id, [])
        if sections or tables:
            names = ", ".join(s.name for s in sections[:14]) or "none identified"
            table_text = ", ".join(f"{t.name} ({len(t.rows)} rows)" for t in tables) or "none"
            story += [Spacer(1, 3), _p(f"Structure: sections {names}; tables {table_text}.", "small")]

    # 7.3
    story += [Spacer(1, 12), CondPageBreak(110 * mm), _p("7.3 Contextual Analysis", "h1")]
    story.append(_p("Cross-document discrepancies", "h2"))
    if dossier.cross_document_findings:
        for f in dossier.cross_document_findings:
            story += _finding_block(f, docs)
    else:
        story.append(_p("No conflicts were found between the documents that could be compared.", "note"))
    story.append(CondPageBreak(80 * mm))
    story.append(_p("Field-level inconsistencies within a document", "h2"))
    contextual = [f for f in dossier.contextual_findings if f.detector not in ("context.missing_field", "context.duplicate_field")]
    if contextual:
        for f in contextual:
            story += _finding_block(f, docs)
    else:
        story.append(_p("No within-document inconsistencies were found.", "note"))
    story.append(CondPageBreak(30 * mm))
    story.append(_p("Missing or duplicated information", "h2"))
    rows = [[_p(h, "th") for h in ("Document", "Missing", "Duplicated")]]
    any_rows = False
    for o in dossier.overview:
        entry = dossier.missing_or_duplicated.get(o.doc_id, {})
        if entry.get("missing") or entry.get("duplicated"):
            any_rows = True
            rows.append([_p(o.filename, "cell"), _p(", ".join(_human(x) for x in entry.get("missing", [])) or "None", "cell"),
                         _p(", ".join(_human(x) for x in entry.get("duplicated", [])) or "None", "cell")])
    story.append(_grid(rows, [50 * mm, CONTENT_W - 100 * mm, 50 * mm]) if any_rows
                 else _p("None identified.", "note"))

    # 7.4
    story += [Spacer(1, 12), CondPageBreak(90 * mm), _p("7.4 Visual Forensic Findings", "h1")]
    groups = [
        ("Suspicious regions and potential alterations", ("visual.ela", "visual.noise", "visual.overwrite", "visual.copy_move", "fusion")),
        ("Font, alignment and structural inconsistencies", ("visual.font_consistency", "visual.alignment", "pdf.")),
        ("Image manipulation observations", ("visual.photo_insert", "metadata.")),
        ("Signature-related observations", ("visual.signature",)),
    ]
    major = [f for f in dossier.visual_findings if not _is_minor(f)]
    minor = [f for f in dossier.visual_findings if _is_minor(f)]
    remaining = list(major)
    if not dossier.visual_findings:
        story.append(_p("The forensic detectors flagged no regions. This doesn't establish authenticity.", "note"))
    for title, prefixes in groups:
        chosen = [f for f in remaining if f.detector.startswith(prefixes)]
        if chosen:
            story.append(CondPageBreak(80 * mm))
            story.append(_p(title, "h2"))
            for f in chosen:
                story += _finding_block(f, docs)
            remaining = [f for f in remaining if f not in chosen]
    if remaining:
        story += [CondPageBreak(80 * mm), _p("Other forensic signals", "h2")]
        for f in remaining:
            story += _finding_block(f, docs)
    if minor:
        story += [CondPageBreak(40 * mm), _p("Low-weight observations", "h2"),
                  _p("Measured facts with weak signals. Each is expected to occur on some genuine documents, and "
                     "alone none of them is a reason for concern.", "note"), Spacer(1, 3)]
        story += _minor_table(_sort(minor), docs)

    # 7.5
    story += [PageBreak(), _p("7.5 Evidence and Traceability", "h1")]
    story.append(_p("Each finding maps to its original document, page and pixel region. Box colours follow the status legend: "
                    "blue observation, amber inconsistency, red potential manipulation.", "note"))
    story += [Spacer(1, 6), _p("Highlighted regions", "h2")] + _page_thumbnails(findings, docs)
    story += [CondPageBreak(40 * mm), _p("Finding to source map", "h2")]
    rows = [[_p(h, "th") for h in ("Finding", "Status", "Conf.", "Primary source", "Associated extracted values", "Evidence")]]
    for entry in dossier.traceability:
        bbox = entry.get("bbox")
        loc = f"{entry.get('filename') or 'Case level'}"
        if entry.get("page") is not None:
            loc += f", p.{entry['page'] + 1}"
        if bbox:
            loc += f" ({bbox['x0']:.0f},{bbox['y0']:.0f} to {bbox['x1']:.0f},{bbox['y1']:.0f})"
        values = "; ".join(f"{x['filename']}: {_human(x['name'])} = {x['value']} (p.{x['page'] + 1})" for x in entry["fields"][:5])
        rows.append([_p(entry["title"], "cell"), _p(STATUS_STYLE[entry["status"]][2], "cell"),
                     _p(f"{entry['confidence']:.2f}", "cell"), _p(loc, "cell"), _p(values or "None", "cell"),
                     _p(f"{len(entry['evidence_uris'])} item(s)", "cell")])
    if len(rows) > 1:
        story.append(_grid(rows, [38 * mm, 21 * mm, 10 * mm, 37 * mm, CONTENT_W - 120 * mm, 14 * mm]))
    else:
        story.append(_p("No findings were recorded.", "note"))

    # 7.6
    story += [Spacer(1, 12), CondPageBreak(60 * mm), _p("7.6 Investigation Summary", "h1")]
    for paragraph in dossier.summary.split("\n\n"):
        story += [_p(paragraph), Spacer(1, 5)]
    attention = [f for f in findings if f.status != FindingStatus.OBSERVATION]
    if attention:
        story.append(_p("Identified anomalies and supporting evidence", "h2"))
        rows = [[_p(h, "th") for h in ("Anomaly", "Status", "Conf.", "Evidence")]]
        for f in _sort(attention):
            kinds = sorted({e.kind.value.replace("_", " ") for e in f.evidence})
            rows.append([_p(f.title, "cell"), _p(STATUS_STYLE[f.status.value][2], "cell"),
                         _p(f"{f.confidence:.2f}", "cell"), _p(", ".join(kinds) or "See finding", "cell")])
        story.append(_grid(rows, [CONTENT_W - 90 * mm, 30 * mm, 12 * mm, 48 * mm]))
    if dossier.potential_explanations:
        story += [_p("Potential explanations", "h2")] + _bullets(dossier.potential_explanations, 12)
    if dossier.areas_for_verification:
        story += [_p("Areas requiring additional verification", "h2")] + _bullets(dossier.areas_for_verification, 12)
    story += [_p("Investigation limitations", "h2")] + _bullets(dossier.limitations, 20)
    story += [_p("How this text was produced", "h2"),
              _p("Reasoning modes: " + ", ".join(dossier.reasoning_modes) + ". An LLM can add reasoning but can't create "
                 "findings or change a status, a confidence or a location.", "cell")]
    if dossier.audit_head_hash:
        story += [Spacer(1, 4), _p(f"Audit chain head at generation: {dossier.audit_head_hash}", "small")]

    def decorate(canvas, doc_template) -> None:
        canvas.saveState()
        canvas.setStrokeColor(RULE)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(MARGIN, 10 * mm, f"DocuForensic AI | {dossier.case_id} | For human review only")
        canvas.restoreState()

    template = BaseDocTemplate(
        str(out), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=16 * mm, bottomMargin=18 * mm,
        title=f"Investigation Dossier: {dossier.case_name}", author="DocuForensic AI",
    )
    frame = Frame(MARGIN, 18 * mm, CONTENT_W, PAGE_H - 34 * mm, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    template.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=decorate)])
    template.build(story, canvasmaker=_NumberedCanvas)
    return out


__all__ = ["build_dossier", "render_pdf", "KeepTogether"]
