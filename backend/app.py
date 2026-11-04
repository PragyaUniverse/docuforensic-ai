"""FastAPI application. Run with: python -m uvicorn backend.app:app --port 8000"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field as PField
from starlette.datastructures import UploadFile

from audit import chain
from backend import capabilities, db, dossier as dossier_mod, orchestrator
from backend.logging_conf import configure_logging
from config.settings import REPO_ROOT, settings
from llm.client import get_client
from llm.providers import PROVIDERS
from models.schemas import (
    AuditEntry, AuditVerification, Case, CaseStatus, DocFormat, Document, Dossier, Entity,
    EvidenceGraph, Finding, FindingCategory, FindingStatus, ProcessingStatus, ReviewDecision,
    ReviewRecord, utcnow,
)

VERSION = "0.1.0"
log = logging.getLogger("docuforensic.api")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="case-run")
_ALLOWED_SERVED = {".png", ".jpg", ".jpeg", ".pdf"}
MAX_FILES_PER_REQUEST = 30
OVERLAY_LABELS = {
    "ela": "Error level analysis", "noise": "Noise residual", "copy_move": "Copy-move links",
    "font": "Font consistency", "font_consistency": "Font consistency", "overwrite": "Overwrite detection",
    "fusion": "Fused suspicion", "text_vs_pixels": "Text layer vs pixels",
}


def _startup_key_check() -> None:
    """Tiny real call per configured provider, so the Capabilities page reports real results."""
    client = get_client()
    for name, provider in PROVIDERS.items():
        if provider.needs_key and settings.keys_for(name) and not settings.offline:
            client.ping(name)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    for case in db.list_cases():
        if case.status == CaseStatus.running:
            case.status = CaseStatus.failed
            for stage in case.progress:
                if stage.state == "running":
                    stage.state, stage.message = "failed", "The server restarted during this stage."
            db.save_case(case)
            chain.append("case.interrupted", "system", case.id, {"reason": "server restart"})
    threading.Thread(target=_startup_key_check, daemon=True).start()
    yield


app = FastAPI(title="DocuForensic AI", version=VERSION, lifespan=lifespan,
              description="Evidence-driven document forensics. Findings need human review.")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list(), allow_methods=["*"],
                   allow_headers=["*"])

_hits: dict[str, deque[float]] = defaultdict(deque)
_hits_lock = threading.Lock()


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    # Only state-changing requests: a viewer legitimately loads many images.
    if request.method == "POST" and request.url.path.startswith("/api/"):
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _hits_lock:
            window = _hits[client]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= settings.rate_limit_per_minute:
                return JSONResponse({"detail": "Too many requests. Wait a minute and try again."},
                                    status_code=429, headers={"Retry-After": "60"})
            window.append(now)
    return await call_next(request)


@app.exception_handler(Exception)
async def unhandled(_: Request, exc: Exception):
    log.error("unhandled error type=%s", type(exc).__name__)
    return JSONResponse({"detail": "The server hit an internal error. The event was logged."}, status_code=500)


# ---- helpers
def _case(case_id: str) -> Case:
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(404, "Case not found.")
    return case


def _doc(case_id: str, doc_id: str) -> Document:
    doc = db.get_document(doc_id)
    if doc is None or doc.case_id != case_id:
        raise HTTPException(404, "Document not found in this case.")
    return doc


def _data_file(rel: str) -> Path:
    root = Path(settings.data_dir).resolve()
    path = (root / rel).resolve()
    if not path.is_relative_to(root) or path.suffix.lower() not in _ALLOWED_SERVED or not path.is_file():
        raise HTTPException(404, "File not found.")
    return path


def _summary(doc: Document, findings: list[Finding] | None = None) -> dict:
    findings = findings if findings is not None else []
    return {
        "id": doc.id, "filename": doc.filename, "format": doc.format.value, "doc_type": doc.doc_type.value,
        "doc_type_confidence": doc.doc_type_confidence, "status": doc.status.value,
        "status_message": doc.status_message, "page_count": len(doc.pages), "field_count": len(doc.fields),
        "finding_count": sum(1 for f in findings if f.doc_id == doc.id or doc.id in f.related_doc_ids),
    }


def safe_filename(raw: str | None) -> str:
    name = Path((raw or "upload").replace("\\", "/")).name
    name = re.sub(r"[^\w.\- ()]", "_", name).strip(" .")[:120]
    return name or "upload"


def _ingest(path: Path, case_id: str, filename: str) -> Document:
    ingest = orchestrator.pipeline_fn("ingest", "ingest_file")
    workdir = orchestrator.case_workdir(case_id)
    if ingest is None:
        doc = Document(case_id=case_id, filename=filename, sha256="", format=DocFormat.unsupported,
                       status=ProcessingStatus.failed, status_message="The ingest module isn't available.")
    else:
        doc = ingest(path, case_id, workdir, filename)
    db.save_document(doc, source_path=str(path))
    chain.append("document.submitted", "system", case_id, {
        "doc_id": doc.id, "filename": doc.filename, "sha256": doc.sha256, "size_bytes": doc.size_bytes,
        "format": doc.format.value, "status": doc.status.value, "status_message": doc.status_message,
    })
    return doc


def _manifest() -> list[dict]:
    root = Path(settings.demo_cases_dir)
    entries: list[dict] = []
    try:
        entries = json.loads((root / "manifest.json").read_text("utf-8"))
    except (OSError, ValueError):
        entries = []
    unsupported = root / "unsupported"
    if unsupported.is_dir():
        files = sorted(p.name for p in unsupported.iterdir() if p.is_file() and p.name != "expected.json")
        entries.append({
            "key": "unsupported_files", "name": "Safe failure: unusable files",
            "description": "A corrupt PDF, an empty image, a Word file and a mislabelled file. "
                           "Each should get a clear status, without a crash.",
            "dir": "unsupported", "documents": files,
        })
    return entries


# ---- health and capabilities
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION, "offline": settings.offline, "demo_cache": settings.demo_cache}


@app.get("/api/capabilities")
def get_capabilities() -> dict:
    return capabilities.report()


# ---- demo cases
@app.get("/api/demo-cases")
def demo_cases() -> list[dict]:
    return [{k: e.get(k) for k in ("key", "name", "description", "documents")} for e in _manifest()]


@app.post("/api/demo-cases/{key}/load", response_model=Case)
def load_demo(key: str) -> Case:
    entry = next((e for e in _manifest() if e.get("key") == key), None)
    if entry is None:
        raise HTTPException(404, "Unknown demo case.")
    case = db.save_case(Case(name=entry.get("name") or key, is_demo=True, demo_key=key))
    chain.append("case.created", "system", case.id, {"name": case.name, "demo_key": key})
    root = (Path(settings.demo_cases_dir) / entry.get("dir", key)).resolve()
    for filename in entry.get("documents", []):
        _ingest(root / filename, case.id, filename)
    return case


# ---- cases
class NewCase(BaseModel):
    name: str = PField(min_length=1, max_length=120)


@app.post("/api/cases", response_model=Case)
def create_case(body: NewCase) -> Case:
    case = db.save_case(Case(name=body.name.strip() or "Untitled case"))
    chain.append("case.created", "system", case.id, {"name": case.name})
    return case


@app.get("/api/cases", response_model=list[Case])
def list_cases() -> list[Case]:
    return db.list_cases()


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    case = _case(case_id)
    findings = db.list_findings(case_id)
    return {"case": case.model_dump(mode="json"),
            "documents": [_summary(d, findings) for d in db.list_documents(case_id)]}


@app.post("/api/cases/{case_id}/documents")
async def upload_documents(case_id: str, request: Request) -> list[dict]:
    case = _case(case_id)
    if case.status == CaseStatus.running:
        raise HTTPException(409, "This case is being processed. Upload once it finishes.")
    limit = settings.max_upload_mb * 1024 * 1024
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > (limit + 1024 * 1024) * MAX_FILES_PER_REQUEST:
        raise HTTPException(413, f"The upload exceeds the limit of {settings.max_upload_mb} MB per file.")
    try:
        form = await request.form()
    except Exception as exc:
        raise HTTPException(400, "Send documents as multipart form data in the field 'files'.") from exc
    files = [f for key in ("files", "files[]", "file") for f in form.getlist(key) if isinstance(f, UploadFile)]
    if not files:
        raise HTTPException(400, "No files received. Send them in the multipart field 'files'.")
    if len(files) > MAX_FILES_PER_REQUEST:
        raise HTTPException(413, f"At most {MAX_FILES_PER_REQUEST} files per upload.")

    upload_dir = orchestrator.case_workdir(case_id) / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[Path, str]] = []
    for item in files:
        name = safe_filename(item.filename)
        dest = upload_dir / f"{uuid.uuid4().hex[:8]}_{name}"
        size = 0
        with dest.open("wb") as out:
            while chunk := await item.read(1 << 20):
                size += len(chunk)
                if size > limit:
                    out.close()
                    dest.unlink(missing_ok=True)
                    for path, _ in saved:
                        path.unlink(missing_ok=True)
                    raise HTTPException(413, f"{name} is larger than the {settings.max_upload_mb} MB limit.")
                out.write(chunk)
        saved.append((dest, name))
    docs = await asyncio.to_thread(lambda: [_ingest(path, case_id, name) for path, name in saved])
    return [_summary(d) for d in docs]


@app.post("/api/cases/{case_id}/run", status_code=202)
def run_case(case_id: str) -> dict:
    case = _case(case_id)
    if case.status == CaseStatus.running:
        raise HTTPException(409, "This case is already being processed.")
    if not db.list_documents(case_id):
        raise HTTPException(400, "Add at least one document before running the investigation.")
    orchestrator.start_case(case)
    _executor.submit(orchestrator.run_case, case_id)
    return {"case_id": case_id, "status": CaseStatus.running.value}


def _progress_payload(case: Case) -> dict:
    return {"case_id": case.id, "status": case.status.value, "risk_level": case.risk_level.value,
            "requires_human_review": case.requires_human_review,
            "stages": [s.model_dump(mode="json") for s in case.progress]}


@app.get("/api/cases/{case_id}/progress")
async def progress(case_id: str, request: Request) -> StreamingResponse:
    _case(case_id)

    async def events():
        last = None
        deadline = time.monotonic() + 1800
        idle = 0
        while time.monotonic() < deadline:
            if await request.is_disconnected():
                return
            case = await asyncio.to_thread(db.get_case, case_id)
            if case is None:
                yield "event: done\ndata: {}\n\n"
                return
            payload = json.dumps(_progress_payload(case))
            if payload != last:
                last = payload
                idle = 0
                yield f"event: progress\ndata: {payload}\n\n"
            else:
                idle += 1
                if idle % 30 == 0:
                    yield ": keep-alive\n\n"
            if case.status in (CaseStatus.complete, CaseStatus.failed):
                yield f"event: done\ndata: {payload}\n\n"
                return
            if case.status == CaseStatus.created:
                # Nothing is running, so report the state instead of holding a connection open.
                yield f"event: done\ndata: {payload}\n\n"
                return
            await asyncio.sleep(0.4)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---- documents
@app.get("/api/cases/{case_id}/documents")
def list_documents(case_id: str) -> list[dict]:
    _case(case_id)
    findings = db.list_findings(case_id)
    return [_summary(d, findings) for d in db.list_documents(case_id)]


@app.get("/api/cases/{case_id}/documents/{doc_id}", response_model=Document)
def get_document(case_id: str, doc_id: str, words: bool = False) -> Document:
    doc = _doc(case_id, doc_id)
    if not words:
        for page in doc.pages:
            page.words = []
    return doc


def _page(doc: Document, n: int):
    if n < 0 or n >= len(doc.pages):
        raise HTTPException(404, "Page not found.")
    return doc.pages[n]


@app.get("/api/cases/{case_id}/documents/{doc_id}/pages/{n}/image")
def page_image(case_id: str, doc_id: str, n: int) -> FileResponse:
    page = _page(_doc(case_id, doc_id), n)
    return FileResponse(_data_file(page.image_path))


def _overlay_files(case_id: str, doc_id: str, n: int) -> dict[str, Path]:
    directory = orchestrator.case_workdir(case_id) / doc_id / "overlays"
    out: dict[str, Path] = {}
    if directory.is_dir():
        for path in sorted(directory.glob(f"*_p{n}.png")):
            out[path.name[: -len(f"_p{n}.png")]] = path
    return out


@app.get("/api/cases/{case_id}/documents/{doc_id}/pages/{n}/overlays")
def overlays(case_id: str, doc_id: str, n: int) -> list[dict]:
    _page(_doc(case_id, doc_id), n)
    return [{"kind": kind, "label": OVERLAY_LABELS.get(kind, kind.replace("_", " ").capitalize()),
             "url": f"/api/cases/{case_id}/documents/{doc_id}/pages/{n}/overlays/{kind}"}
            for kind in _overlay_files(case_id, doc_id, n)]


@app.get("/api/cases/{case_id}/documents/{doc_id}/pages/{n}/overlays/{kind}")
def overlay(case_id: str, doc_id: str, n: int, kind: str) -> FileResponse:
    _page(_doc(case_id, doc_id), n)
    path = _overlay_files(case_id, doc_id, n).get(kind)
    if path is None:
        raise HTTPException(404, "Overlay not found.")
    return FileResponse(path, media_type="image/png")


# ---- findings and review
@app.get("/api/cases/{case_id}/findings", response_model=list[Finding])
def findings(case_id: str, status: FindingStatus | None = None, category: FindingCategory | None = None,
             doc_id: str | None = Query(default=None)) -> list[Finding]:
    _case(case_id)
    out = db.list_findings(case_id)
    if status:
        out = [f for f in out if f.status == status]
    if category:
        out = [f for f in out if f.category == category]
    if doc_id:
        out = [f for f in out if f.doc_id == doc_id or doc_id in f.related_doc_ids]
    return out


class ReviewBody(BaseModel):
    decision: Literal["confirmed", "dismissed", "escalated"]
    reviewer: str = PField(default="reviewer", max_length=80)
    note: str | None = PField(default=None, max_length=2000)


@app.post("/api/findings/{finding_id}/review", response_model=Finding)
def review(finding_id: str, body: ReviewBody) -> Finding:
    finding = db.get_finding(finding_id)
    if finding is None:
        raise HTTPException(404, "Finding not found.")
    previous = finding.review.decision.value
    finding.review = ReviewRecord(decision=ReviewDecision(body.decision), reviewer=body.reviewer.strip() or "reviewer",
                                  note=body.note, at=utcnow())
    db.save_finding(finding)
    chain.append("finding.review", f"reviewer:{finding.review.reviewer}", finding.case_id, {
        "finding_id": finding.id, "decision": body.decision, "previous": previous, "note": body.note,
        "detector": finding.detector, "status": finding.status.value,
    })
    return finding


# ---- extracted data, entities, graph
@app.get("/api/cases/{case_id}/fields")
def fields(case_id: str) -> list[dict]:
    _case(case_id)
    out = []
    for doc in db.list_documents(case_id):
        for f in doc.fields:
            out.append({**f.model_dump(mode="json"), "doc_filename": doc.filename, "doc_type": doc.doc_type.value})
    return out


@app.get("/api/cases/{case_id}/entities", response_model=list[Entity])
def entities(case_id: str) -> list[Entity]:
    _case(case_id)
    return db.list_entities(case_id)


@app.get("/api/cases/{case_id}/graph", response_model=EvidenceGraph)
def graph(case_id: str) -> EvidenceGraph:
    _case(case_id)
    return db.get_graph(case_id) or EvidenceGraph(case_id=case_id)


# ---- dossier
def _dossier_or_409(case_id: str) -> Dossier:
    case = _case(case_id)
    if case.status == CaseStatus.running:
        raise HTTPException(409, "The investigation is still running.")
    if case.status == CaseStatus.created:
        raise HTTPException(409, "Run the investigation before generating a dossier.")
    return dossier_mod.build_dossier(case_id)


@app.get("/api/cases/{case_id}/dossier", response_model=Dossier)
def get_dossier(case_id: str) -> Dossier:
    return _dossier_or_409(case_id)


@app.get("/api/cases/{case_id}/dossier.pdf")
def get_dossier_pdf(case_id: str) -> FileResponse:
    built = _dossier_or_409(case_id)
    out = dossier_mod.render_pdf(built, orchestrator.case_workdir(case_id) / "dossier.pdf")
    return FileResponse(out, media_type="application/pdf", filename=f"dossier_{case_id}.pdf")


# ---- audit
@app.get("/api/cases/{case_id}/audit", response_model=list[AuditEntry])
def audit(case_id: str) -> list[AuditEntry]:
    _case(case_id)
    return chain.entries(case_id)


@app.get("/api/cases/{case_id}/audit/verify", response_model=AuditVerification)
def audit_verify(case_id: str) -> AuditVerification:
    _case(case_id)
    return chain.verify()


def _require_tamper_demo() -> None:
    if not settings.audit_tamper_demo:
        raise HTTPException(403, "The tamper demonstration is disabled.")


@app.post("/api/audit/tamper-demo")
def tamper_demo() -> dict:
    _require_tamper_demo()
    seq = chain.tamper_demo()
    if seq is None:
        raise HTTPException(409, "The audit log has no entries to edit yet.")
    log.info("tamper demo active seq=%s", seq)
    return {"tampered_seq": seq}


@app.post("/api/audit/tamper-demo/restore")
def tamper_restore() -> dict:
    # Restoring stays possible even if the demo was disabled while an edit was active.
    seq = chain.restore_tamper_demo()
    verification = chain.verify()
    if seq is not None:
        chain.append("audit.tamper_demo_restored", "system", None, {"restored_seq": seq})
    return {"restored_seq": seq, "ok": verification.ok}


# ---- files
@app.get("/api/files/{path:path}")
def files_route(path: str) -> FileResponse:
    return FileResponse(_data_file(path))


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


# Serves a built frontend, when there is one, so the demo can run on one port.
_dist = REPO_ROOT / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")

__all__ = ["app", "shutil"]
