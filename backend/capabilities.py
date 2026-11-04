"""Real capability report: everything here is checked at call time, nothing is assumed."""
from __future__ import annotations

import importlib.util
import shutil
from typing import Any

from audit import chain
from config.settings import settings
from llm.client import get_client

_MODULES = {
    name: f"pipeline.{name}"
    for name in ("ingest", "ocr", "classify", "extract", "structure", "forensics_visual", "forensics_pdf",
                 "signatures", "fusion")
}


def _module_ok(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _lib(name: str, spec: str) -> dict[str, Any]:
    ok = importlib.util.find_spec(spec) is not None
    return {"name": name, "available": ok, "detail": "installed" if ok else "not installed"}


def tools() -> list[dict[str, Any]]:
    tesseract = shutil.which("tesseract")
    out = [
        _lib("RapidOCR (PP-OCR models on ONNX Runtime)", "rapidocr_onnxruntime"),
        {"name": "Tesseract", "available": bool(tesseract),
         "detail": "binary found" if tesseract else "binary not on PATH; RapidOCR is used alone"},
        _lib("PyMuPDF", "pymupdf"), _lib("pikepdf", "pikepdf"), _lib("OpenCV", "cv2"),
        _lib("scikit-image", "skimage"), _lib("imagehash", "imagehash"), _lib("rapidfuzz", "rapidfuzz"),
        _lib("ReportLab", "reportlab"),
    ]
    for name, module in _MODULES.items():
        ok = _module_ok(module)
        out.append({"name": f"pipeline: {name}", "available": ok, "detail": "module present" if ok else "module missing"})
    return out


def _status(module_names: list[str], when_present: str = "Implemented") -> str:
    return when_present if all(_module_ok(_MODULES[m]) for m in module_names) else "Planned"


def matrix() -> list[dict[str, str]]:
    return [
        {"capability": "Ingest PNG, JPG, scanned PDF and digital PDF", "status": _status(["ingest"]),
         "notes": "Type comes from file content. Bad files get a clear status, not a crash."},
        {"capability": "Printed text OCR with confidence and location", "status": _status(["ocr"]),
         "notes": "RapidOCR with Tesseract as fallback. Readings are not treated as verified."},
        {"capability": "Handwriting recognition", "status": "Unsupported",
         "notes": "Handwritten values are often unread or misread; low confidence is flagged where measurable."},
        {"capability": "Languages other than English", "status": "Unsupported", "notes": "Models and field labels are English only."},
        {"capability": "Document classification", "status": _status(["classify"], "Partial"),
         "notes": "Keyword and layout based, for six document types. Other types come back as unknown."},
        {"capability": "Field, table and layout extraction", "status": _status(["extract", "structure"], "Partial"),
         "notes": "Label-to-value layout rules; unfamiliar templates extract fewer fields."},
        {"capability": "Pixel forensics (ELA, noise, copy-move, font, overwrite)", "status": _status(["forensics_visual"], "Partial"),
         "notes": "Heuristic signals with known false positives on re-saved or noisy scans."},
        {"capability": "PDF structure forensics", "status": _status(["forensics_pdf"]),
         "notes": "Text layer vs pixels, incremental updates, producer, overlays, metadata."},
        {"capability": "Signature reuse and placement", "status": _status(["signatures"], "Partial"),
         "notes": "Perceptual-hash reuse and placement only. No writer verification."},
        {"capability": "Within-document verification", "status": "Implemented",
         "notes": "Salary and balance arithmetic, date logic, ID format and check digit, missing and duplicate fields."},
        {"capability": "Cross-document correlation", "status": "Implemented",
         "notes": "Nine discrepancy types with both sides linked. Assumes one applicant per case."},
        {"capability": "Evidence mapping and graph", "status": "Implemented", "notes": "Finding to document, page, region and field."},
        {"capability": "Investigation dossier (PDF and JSON)", "status": "Implemented", "notes": "Sections 7.1 to 7.6."},
        {"capability": "Hash-chained audit trail", "status": "Implemented",
         "notes": "Tamper-evident against edits to entries. Not protected from someone able to rewrite the whole database."},
        {"capability": "Human review actions", "status": "Implemented", "notes": "Confirm, dismiss or escalate; each decision is audited."},
        {"capability": "Local LLM reasoning (Ollama)", "status": "Implemented",
         "notes": "Optional. Adds counter-hypotheses only and can't change findings."},
        {"capability": "Remote LLM reasoning (Gemini, Groq, OpenRouter)", "status": "Partial",
         "notes": "Adapters tested with mocked HTTP only; unverified until a key is provided."},
        {"capability": "Issuer or registry verification", "status": "Unsupported", "notes": "No external source is contacted."},
    ]


LIMITATIONS = [
    "Findings are prompts for human review, not conclusions about a person or a document.",
    "Forensic detectors are heuristic and can flag re-saved, compressed or noisy scans.",
    "An absence of findings isn't proof of authenticity: a careful edit can leave no signal.",
    "Accuracy figures come from a synthetic dataset, and real documents may perform differently.",
    "Handwriting and non-English documents are not supported.",
    "Field extraction relies on printed labels, so unfamiliar templates yield fewer fields.",
    "Cross-document checks assume every document in a case concerns one applicant.",
]


def mode() -> str:
    if settings.offline:
        return "offline"
    if settings.demo_cache:
        return "demo_cache"
    return "live" if get_client().any_live_provider() else "deterministic"


def report() -> dict[str, Any]:
    client = get_client()
    return {
        "mode": mode(),
        "offline": settings.offline,
        "demo_cache": settings.demo_cache,
        "providers": client.provider_status(),
        "tools": tools(),
        "matrix": matrix(),
        "limitations": LIMITATIONS,
        "llm_usage": {
            "calls": client.usage["calls"], "tokens": client.usage["tokens"],
            "cache_hits": client.usage["cache_hits"], "by_provider": client.usage["by_provider"],
        },
        "audit": {
            "tamper_demo_enabled": settings.audit_tamper_demo,
            "tamper_demo_active_seq": chain.tamper_active_seq(),
        },
    }
