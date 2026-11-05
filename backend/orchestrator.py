"""Runs the ten investigation stages for a case, auditing and publishing progress at each one.

Pipeline modules are imported lazily. A missing or failing detector degrades its stage with a
stated reason; it never crashes the case and never produces stand-in results.
"""
from __future__ import annotations

import hashlib
import importlib
import logging
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from PIL import Image, ImageDraw

from audit import chain
from backend import contextual, crossdoc, db, dossier as dossier_mod
from config.settings import settings
from llm import investigator
from llm.client import get_client
from models.schemas import (
    BBox, Case, CaseStatus, Document, EvidenceItem, EvidenceKind, Finding, FindingStatus, PipelineStage, ProcessingStatus, RiskLevel, Severity, StageProgress, TextSource,
    utcnow,
)

log = logging.getLogger("docuforensic.orchestrator")

STATUS_COLOR = {
    FindingStatus.OBSERVATION: (37, 99, 235),
    FindingStatus.INCONSISTENCY: (217, 119, 6),
    FindingStatus.POTENTIAL_MANIPULATION: (220, 38, 38),
}
_SKIP = (ProcessingStatus.unsupported, ProcessingStatus.failed)
_RANK = {Severity.info: 0, Severity.low: 1, Severity.medium: 2, Severity.high: 3}


def case_workdir(case_id: str) -> Path:
    path = Path(settings.data_dir) / "cases" / case_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def rel(path: Path) -> str:
    return str(Path(path).resolve().relative_to(Path(settings.data_dir).resolve()))


def pipeline_fn(module: str, name: str) -> Callable | None:
    try:
        return getattr(importlib.import_module(f"pipeline.{module}"), name)
    except Exception as exc:  # noqa: BLE001 - an absent or broken module is reported, not raised
        log.warning("pipeline module unavailable module=%s error=%s", module, type(exc).__name__)
        return None


def new_progress() -> list[StageProgress]:
    return [StageProgress(stage=s) for s in PipelineStage]


class _Stage:
    def __init__(self) -> None:
        self.degraded: list[str] = []
        self.payload: dict = {}

    def degrade(self, message: str) -> None:
        self.degraded.append(message)


class Run:
    def __init__(self, case: Case) -> None:
        self.case = case

    def _progress(self, stage: PipelineStage) -> StageProgress:
        return next(p for p in self.case.progress if p.stage == stage)

    @contextmanager
    def stage(self, stage: PipelineStage) -> Iterator[_Stage]:
        progress = self._progress(stage)
        progress.state, progress.started_at = "running", utcnow()
        db.save_case(self.case)
        ctx = _Stage()
        start = time.monotonic()
        failure = None
        try:
            yield ctx
        except Exception as exc:  # noqa: BLE001 - later stages still run on what exists
            log.exception("stage failed stage=%s", stage.value)
            failure = f"{type(exc).__name__} in this stage; later stages used the results available."
        progress.duration_ms = int((time.monotonic() - start) * 1000)
        progress.finished_at = utcnow()
        if failure:
            progress.state, progress.message = "failed", failure
        elif ctx.degraded:
            progress.state, progress.message = "degraded", " ".join(dict.fromkeys(ctx.degraded))
        else:
            progress.state = "done"
            progress.message = ctx.payload.get("message")
        db.save_case(self.case)
        chain.append(f"stage.{stage.value}", f"pipeline.{stage.value}", self.case.id, {
            "state": progress.state, "duration_ms": progress.duration_ms, "message": progress.message,
            **{k: v for k, v in ctx.payload.items() if k != "message"},
        })


def _for_each_doc(docs: list[Document], ctx: _Stage, label: str, fn: Callable[[Document], Document]) -> None:
    for i, doc in enumerate(docs):
        if doc.status in _SKIP:
            continue
        try:
            docs[i] = fn(doc)
        except Exception as exc:  # noqa: BLE001
            log.exception("%s failed", label)
            doc.status = ProcessingStatus.degraded
            doc.status_message = f"{label} could not complete ({type(exc).__name__})."
            ctx.degrade(f"{label} failed for {doc.filename}.")
        db.save_document(docs[i])


def _safe_findings(ctx: _Stage, label: str, fn: Callable[[], list[Finding]]) -> list[Finding]:
    try:
        return fn() or []
    except Exception as exc:  # noqa: BLE001
        log.exception("%s failed", label)
        ctx.degrade(f"{label} did not complete ({type(exc).__name__}); its absence isn't a clean result.")
        return []


def _regions_overlap(a: BBox, b: BBox) -> bool:
    ix, iy = min(a.x1, b.x1) - max(a.x0, b.x0), min(a.y1, b.y1) - max(a.y0, b.y0)
    return ix > 0 and iy > 0 and ix * iy / max(min(a.area, b.area), 1.0) >= 0.3


def apply_visible_readings(docs: list[Document], findings: list[Finding]) -> int:
    """Where a PDF's text layer disagrees with its pixels, later checks use what a person sees.

    A digital PDF's text layer can hold a value nobody sees. Contextual checks should test the
    value the document presents, or an overlay would pass them. The hidden value stays recorded
    in the finding and in doc.metadata['visible_readings'].
    """
    by_id = {d.id: d for d in docs}
    changed = 0
    for finding in findings:
        if finding.detector != "pdf.text_vs_pixels" or finding.doc_id not in by_id:
            continue
        doc = by_id[finding.doc_id]
        for item in finding.evidence:
            visible = item.data.get("rendered_ocr")
            if not visible or item.bbox is None or not item.data.get("digits_differ", True):
                continue
            conf = float(item.data.get("ocr_confidence") or 0.8)
            page = item.page if item.page is not None else finding.page
            for field in doc.fields:
                if field.page == page and _regions_overlap(field.bbox, item.bbox) and field.value_raw != visible:
                    doc.metadata.setdefault("visible_readings", []).append(
                        {"field": field.name, "text_layer": field.value_raw, "visible": visible, "finding_id": finding.id})
                    field.value_raw, field.value_norm = visible, None
                    field.source, field.confidence = TextSource.ocr_rapid, conf
                    if field.id not in finding.related_field_ids:
                        finding.related_field_ids.append(field.id)
                    changed += 1
            for table in doc.tables:
                if table.page != page:
                    continue
                for row in table.rows:
                    for cell in row:
                        if cell.bbox is not None and _regions_overlap(cell.bbox, item.bbox) and cell.text != visible:
                            doc.metadata.setdefault("visible_readings", []).append(
                                {"table": table.name, "text_layer": cell.text, "visible": visible, "finding_id": finding.id})
                            cell.text, cell.confidence = visible, conf
                            changed += 1
    return changed


def compute_risk(findings: list[Finding], docs: list[Document]) -> RiskLevel:
    """Rules in docs/CONTRACTS.md section 5. A prioritization aid, not a verdict."""
    if not any(d.status not in _SKIP and d.pages for d in docs):
        return RiskLevel.undetermined
    manip = [f for f in findings if f.status == FindingStatus.POTENTIAL_MANIPULATION]
    incons = [f for f in findings if f.status == FindingStatus.INCONSISTENCY and _RANK[f.severity] >= 2]
    strong = any((f.fused_score if f.fused_score is not None else f.confidence) >= 0.6 for f in manip)
    if strong or len(incons) >= 3:
        return RiskLevel.high
    if manip or incons:
        return RiskLevel.medium
    return RiskLevel.low


def _page_path(doc: Document, page: int) -> Path | None:
    if page < 0 or page >= len(doc.pages):
        return None
    path = Path(doc.pages[page].image_path)
    path = path if path.is_absolute() else Path(settings.data_dir) / path
    return path if path.exists() else None


def write_crop(doc: Document, page: int, bbox: BBox, out: Path, color: tuple[int, int, int]) -> str | None:
    source = _page_path(doc, page)
    if source is None:
        return None
    with Image.open(source) as image:
        image = image.convert("RGB")
        pad = 30
        x0, y0 = max(0, int(bbox.x0) - pad), max(0, int(bbox.y0) - pad)
        x1, y1 = min(image.width, int(bbox.x1) + pad), min(image.height, int(bbox.y1) + pad)
        if x1 <= x0 or y1 <= y0:
            return None
        crop = image.crop((x0, y0, x1, y1))
        ImageDraw.Draw(crop).rectangle(
            (bbox.x0 - x0, bbox.y0 - y0, bbox.x1 - x0, bbox.y1 - y0), outline=color, width=3)
        out.parent.mkdir(parents=True, exist_ok=True)
        crop.save(out)
    return rel(out)


def clip(bbox: BBox, doc: Document, page: int) -> BBox:
    pg = doc.pages[page]
    return BBox(x0=max(0.0, min(bbox.x0, pg.width)), y0=max(0.0, min(bbox.y0, pg.height)),
                x1=max(0.0, min(bbox.x1, pg.width)), y1=max(0.0, min(bbox.y1, pg.height)))


def materialize_evidence(findings: list[Finding], docs: list[Document], ctx: _Stage) -> None:
    """Writes highlighted crops for each finding and EACH linked field, and audits every finding."""
    by_id = {d.id: d for d in docs}
    unmapped = 0
    for finding in findings:
        color = STATUS_COLOR[finding.status]
        doc = by_id.get(finding.doc_id or "")
        if doc and finding.bbox is not None and finding.page is not None and finding.page < len(doc.pages):
            finding.bbox = clip(finding.bbox, doc, finding.page)
            if not any(e.kind == EvidenceKind.crop for e in finding.evidence):
                out = case_workdir(finding.case_id) / doc.id / "evidence" / f"{finding.id}.png"
                uri = write_crop(doc, finding.page, finding.bbox, out, color)
                if uri:
                    finding.evidence.insert(0, EvidenceItem(
                        kind=EvidenceKind.crop, label="Highlighted source region", uri=uri, doc_id=doc.id,
                        page=finding.page, bbox=finding.bbox))
        elif finding.status != FindingStatus.OBSERVATION and finding.bbox is None:
            unmapped += 1
        for n, item in enumerate(finding.evidence):
            other = by_id.get(item.doc_id or "")
            if item.kind in (EvidenceKind.field_ref, EvidenceKind.raw_value) and item.uri is None and other \
                    and item.bbox is not None and item.page is not None and item.page < len(other.pages):
                out = case_workdir(finding.case_id) / other.id / "evidence" / f"{finding.id}_{n}.png"
                item.uri = write_crop(other, item.page, clip(item.bbox, other, item.page), out, color)
        digests = []
        for item in finding.evidence:
            if item.uri:
                path = Path(settings.data_dir) / item.uri
                if path.exists():
                    digests.append(hashlib.sha256(path.read_bytes()).hexdigest()[:16])
        chain.append("finding.recorded", f"detector.{finding.detector}", finding.case_id, {
            "finding_id": finding.id, "status": finding.status.value, "detector": finding.detector,
            "confidence": finding.confidence, "doc_id": finding.doc_id, "page": finding.page,
            "bbox": finding.bbox.model_dump() if finding.bbox else None,
            "field_ids": finding.related_field_ids, "evidence_sha256": digests,
            "reasoning_mode": finding.reasoning.mode, "reasoning_provider": finding.reasoning.provider,
        })
    ctx.payload["findings"] = len(findings)
    if unmapped:
        ctx.payload["message"] = f"{unmapped} finding(s) are document-level and have no single region."


def _reset_doc(doc: Document) -> Document:
    if doc.status not in _SKIP:
        doc.fields, doc.tables, doc.sections = [], [], []
        doc.missing_fields, doc.duplicated_fields = [], []
        for page in doc.pages:
            page.words = []
        doc.status, doc.status_message = ProcessingStatus.processing, None
    return doc


def start_case(case: Case) -> Case:
    """Marks a case as running before the background thread starts, so a double start is refused."""
    case.status = CaseStatus.running
    case.progress = new_progress()
    return db.save_case(case)


def run_case(case_id: str) -> None:
    case = db.get_case(case_id)
    if case is None:
        return
    if not case.progress:
        case.progress = new_progress()
    case.status = CaseStatus.running
    db.save_case(case)
    try:
        _run(case)
        case.status = CaseStatus.complete
    except Exception as exc:  # noqa: BLE001 - the case records the failure; the server keeps running
        log.exception("case run failed")
        case.status = CaseStatus.failed
        chain.append("case.failed", "system", case_id, {"error": type(exc).__name__})
    db.save_case(case)
    chain.append("case.finished", "system", case_id, {
        "status": case.status.value, "risk_level": case.risk_level.value,
        "requires_human_review": case.requires_human_review})


def _run(case: Case) -> None:
    run = Run(case)
    workdir = case_workdir(case.id)
    docs = [_reset_doc(d) for d in db.list_documents(case.id)]
    findings: list[Finding] = []
    entities = []
    db.replace_findings(case.id, [])
    db.replace_entities(case.id, [])
    chain.append("case.started", "system", case.id, {"documents": len(docs)})

    with run.stage(PipelineStage.submission) as ctx:
        ctx.payload["documents"] = [
            {"doc_id": d.id, "filename": d.filename, "sha256": d.sha256, "format": d.format.value,
             "status": d.status.value} for d in docs]
        for d in docs:
            if d.status in _SKIP:
                ctx.degrade(f"{d.filename}: {d.status_message or d.status.value}")
        if not docs:
            ctx.degrade("No documents were submitted.")
    active = [d for d in docs if d.status not in _SKIP]

    with run.stage(PipelineStage.classification) as ctx:
        extract_words = pipeline_fn("ocr", "extract_words")
        classify = pipeline_fn("classify", "classify")
        if extract_words is None:
            ctx.degrade("OCR module is unavailable.")
        else:
            _for_each_doc(docs, ctx, "Text reading", lambda d: extract_words(d, workdir))
        if classify is None:
            ctx.degrade("Classifier is unavailable; types stay unknown.")
        else:
            _for_each_doc(docs, ctx, "Classification", classify)
        ctx.payload["types"] = {d.id: d.doc_type.value for d in docs}
        for d in docs:
            if d.status == ProcessingStatus.degraded and d.status_message:
                ctx.degrade(f"{d.filename}: {d.status_message}")

    with run.stage(PipelineStage.ocr_extraction) as ctx:
        extract_fields = pipeline_fn("extract", "extract_fields")
        if extract_fields is None:
            ctx.degrade("Field extraction module is unavailable.")
        else:
            _for_each_doc(docs, ctx, "Field extraction", extract_fields)
        ctx.payload["fields"] = {d.id: len(d.fields) for d in docs}

    with run.stage(PipelineStage.structure) as ctx:
        analyze_structure = pipeline_fn("structure", "analyze_structure")
        if analyze_structure is None:
            ctx.degrade("Structure module is unavailable.")
        else:
            _for_each_doc(docs, ctx, "Structure analysis", analyze_structure)

    active = [d for d in docs if d.status not in _SKIP]
    with run.stage(PipelineStage.visual_forensics) as ctx:
        visual = pipeline_fn("forensics_visual", "analyze_visual")
        pdf = pipeline_fn("forensics_pdf", "analyze_pdf")
        signatures = pipeline_fn("signatures", "analyze_signatures")
        fuse = pipeline_fn("fusion", "fuse_regions")
        forensic: list[Finding] = []
        for label, fn in (("Visual forensics", visual), ("PDF structure forensics", pdf)):
            if fn is None:
                ctx.degrade(f"{label} module is unavailable.")
        for doc in active:
            if visual:
                forensic += _safe_findings(ctx, f"Visual forensics on {doc.filename}", lambda: visual(doc, workdir))
            if pdf:
                src = db.document_source(doc.id)
                source = Path(src) if src else Path()
                forensic += _safe_findings(ctx, f"PDF forensics on {doc.filename}", lambda: pdf(doc, source, workdir))
        if signatures is None:
            ctx.degrade("Signature analysis module is unavailable.")
        else:
            forensic += _safe_findings(ctx, "Signature analysis", lambda: signatures(active, workdir, case.id))
        if fuse is None:
            ctx.degrade("Region fusion is unavailable; findings are shown separately.")
        else:
            doc_ids = {d.id for d in active}
            fused: list[Finding] = [f for f in forensic if f.doc_id not in doc_ids]
            for doc in active:
                own = [f for f in forensic if f.doc_id == doc.id]
                result = _safe_findings(ctx, f"Region fusion on {doc.filename}", lambda: fuse(own, doc))
                fused += result if result or not own else own
            forensic = fused
        for f in forensic:
            f.case_id = case.id
        findings += forensic
        ctx.payload["findings"] = len(forensic)
        ctx.payload["visible_readings_applied"] = apply_visible_readings(active, forensic)
        for doc in active:
            db.save_document(doc)

    with run.stage(PipelineStage.contextual_verification) as ctx:
        count = 0
        for doc in active:
            items = contextual.verify_within_document(doc)
            count += len(items)
            findings += items
        ctx.payload["findings"] = count

    with run.stage(PipelineStage.cross_document) as ctx:
        entities = crossdoc.build_entities(active, case.id)
        items = crossdoc.correlate(active, entities, case.id)
        findings += items
        db.replace_entities(case.id, entities)
        ctx.payload.update({"entities": len(entities), "findings": len(items),
                            "discrepancy_types": sorted({f.discrepancy_type for f in items if f.discrepancy_type})})
        if len(active) < 2:
            ctx.degrade("Fewer than two processable documents, so nothing could be compared.")

    with run.stage(PipelineStage.anomaly_investigation) as ctx:
        stats: dict = {}
        findings = investigator.investigate(findings, active, stats=stats)
        ctx.payload["reasoning"] = {
            "llm_enriched": stats.get("llm_enriched", 0), "deterministic": stats.get("deterministic", 0),
            "llm_rejected": stats.get("llm_rejected", 0), "providers": stats.get("providers", {}),
            "skipped_budget": stats.get("skipped_budget", 0),
        }
        ctx.payload["llm_usage"] = {k: get_client().usage[k] for k in ("calls", "tokens", "cache_hits")}
        if not stats.get("llm_enriched"):
            ctx.payload["message"] = "Deterministic reasoning used; no LLM answer was available or accepted."
        else:
            names = ", ".join(sorted(stats["providers"]))
            ctx.payload["message"] = f"{stats['llm_enriched']} finding(s) got LLM counter-hypotheses via {names}."
        if stats.get("skipped_budget"):
            ctx.degrade(f"{stats['skipped_budget']} finding(s) kept deterministic reasoning to stay within the budget.")

    with run.stage(PipelineStage.evidence) as ctx:
        materialize_evidence(findings, docs, ctx)
        db.replace_findings(case.id, findings)
        db.save_graph(crossdoc.build_graph(case.id, docs, entities, findings))
        for doc in docs:
            if doc.status == ProcessingStatus.processing:
                doc.status = ProcessingStatus.ok
            db.save_document(doc)
        case.risk_level = compute_risk(findings, docs)
        # The system never clears a case on its own, whatever a document's text claims.
        case.requires_human_review = True
        ctx.payload.update({"risk_level": case.risk_level.value,
                            "requires_human_review": case.requires_human_review})
        db.save_case(case)

    with run.stage(PipelineStage.dossier) as ctx:
        built = dossier_mod.build_dossier(case.id, fresh_summary=True)
        pdf_path = dossier_mod.render_pdf(built, workdir / "dossier.pdf")
        ctx.payload.update({"pdf_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                            "reasoning_modes": built.reasoning_modes})
