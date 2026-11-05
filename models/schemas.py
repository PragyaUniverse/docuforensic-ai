"""Canonical domain schemas. The single source of truth shared by every module.

Rules (see docs/CONTRACTS.md):
- All bboxes are in canonical page pixels: top-left origin, for the page image
  produced by ingest (PDFs rendered at settings.render_dpi, default 200).
- Nothing here may express a verdict. There is no "fraud" status anywhere.
- Change this file only through the lead; frontend/src/api/types.ts mirrors it.
"""
from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel
from pydantic import Field as PydanticField


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class FindingStatus(str, Enum):
    OBSERVATION = "OBSERVATION"  # a measurable fact
    INCONSISTENCY = "INCONSISTENCY"  # a conflict between fields or documents
    POTENTIAL_MANIPULATION = "POTENTIAL_MANIPULATION"  # hypothesis needing review


class FindingCategory(str, Enum):
    visual = "visual"
    structural = "structural"
    contextual = "contextual"
    cross_document = "cross_document"
    metadata = "metadata"


class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"


class RiskLevel(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    undetermined = "undetermined"  # e.g. every document degraded


class ReviewDecision(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    dismissed = "dismissed"
    escalated = "escalated"


class DocType(str, Enum):
    application_form = "application_form"
    id_proof = "id_proof"
    salary_slip = "salary_slip"
    bank_statement = "bank_statement"
    address_proof = "address_proof"
    declaration = "declaration"
    unknown = "unknown"


class DocFormat(str, Enum):
    png = "png"
    jpg = "jpg"
    scanned_pdf = "scanned_pdf"
    digital_pdf = "digital_pdf"
    unsupported = "unsupported"


class ProcessingStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    ok = "ok"
    degraded = "degraded"  # processed, but with a stated limitation
    unsupported = "unsupported"  # format not handled; never a crash
    failed = "failed"  # corrupted or errored; message says why


class TextSource(str, Enum):
    text_layer = "text_layer"
    ocr_rapid = "ocr_rapid"
    ocr_tesseract = "ocr_tesseract"
    llm = "llm"  # value interpretation only; bboxes never come from an LLM


class ValueType(str, Enum):
    string = "string"
    name = "name"
    date = "date"
    money = "money"
    number = "number"
    id_number = "id_number"
    address = "address"
    account_number = "account_number"


class BBox(BaseModel):
    """Canonical page pixels, top-left origin."""

    x0: float
    y0: float
    x1: float
    y1: float

    def iou(self, other: BBox) -> float:
        ix0, iy0 = max(self.x0, other.x0), max(self.y0, other.y0)
        ix1, iy1 = min(self.x1, other.x1), min(self.y1, other.y1)
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        union = self.area + other.area - inter
        return inter / union if union > 0 else 0.0

    @property
    def area(self) -> float:
        return max(0.0, self.x1 - self.x0) * max(0.0, self.y1 - self.y0)


class Word(BaseModel):
    text: str
    confidence: float  # 0..1; text-layer words use 1.0 but are still not ground truth
    bbox: BBox
    page: int  # 0-based
    source: TextSource


class Page(BaseModel):
    index: int  # 0-based
    width: int  # canonical pixels
    height: int
    image_path: str  # relative to settings.data_dir
    text_source: TextSource | None = None
    mean_ocr_confidence: float | None = None
    words: list[Word] = PydanticField(default_factory=list)


class Field(BaseModel):
    """One extracted key/value. Never treated as ground truth."""

    id: str = PydanticField(default_factory=lambda: new_id("fld"))
    doc_id: str
    name: str  # canonical name from docs/CONTRACTS.md section 4, e.g. "net_pay"
    label_raw: str | None = None  # label as printed on the document
    value_raw: str
    value_norm: str | None = None  # ISO date, plain decimal, casefolded name, ...
    value_type: ValueType = ValueType.string
    confidence: float
    page: int
    bbox: BBox  # always derived from word boxes, never from an LLM
    source: TextSource
    section: str | None = None


class TableCell(BaseModel):
    text: str
    confidence: float
    bbox: BBox | None = None


class Table(BaseModel):
    id: str = PydanticField(default_factory=lambda: new_id("tbl"))
    doc_id: str
    name: str  # e.g. "transactions", "earnings", "deductions"
    page: int
    bbox: BBox | None = None
    headers: list[str] = PydanticField(default_factory=list)
    rows: list[list[TableCell]] = PydanticField(default_factory=list)


class Section(BaseModel):
    """Layout hierarchy node, used for Document Understanding."""

    name: str
    page: int
    bbox: BBox
    field_ids: list[str] = PydanticField(default_factory=list)
    children: list[Section] = PydanticField(default_factory=list)


class Document(BaseModel):
    id: str = PydanticField(default_factory=lambda: new_id("doc"))
    case_id: str
    filename: str
    sha256: str
    mime: str | None = None
    size_bytes: int = 0
    format: DocFormat = DocFormat.unsupported
    doc_type: DocType = DocType.unknown
    doc_type_confidence: float = 0.0
    classification_method: str | None = None  # "keywords", "llm", ...
    status: ProcessingStatus = ProcessingStatus.pending
    status_message: str | None = None
    pages: list[Page] = PydanticField(default_factory=list)
    fields: list[Field] = PydanticField(default_factory=list)
    tables: list[Table] = PydanticField(default_factory=list)
    sections: list[Section] = PydanticField(default_factory=list)
    missing_fields: list[str] = PydanticField(default_factory=list)
    duplicated_fields: list[str] = PydanticField(default_factory=list)
    metadata: dict[str, Any] = PydanticField(default_factory=dict)  # PDF/EXIF metadata
    created_at: datetime = PydanticField(default_factory=utcnow)


class EvidenceKind(str, Enum):
    crop = "crop"
    heatmap = "heatmap"
    raw_value = "raw_value"
    metadata = "metadata"
    comparison = "comparison"
    field_ref = "field_ref"


class EvidenceItem(BaseModel):
    kind: EvidenceKind
    label: str
    uri: str | None = None  # relative to settings.data_dir; API serves it
    doc_id: str | None = None
    page: int | None = None
    bbox: BBox | None = None
    field_id: str | None = None
    data: dict[str, Any] = PydanticField(default_factory=dict)  # measured numbers, raw values


class ReviewRecord(BaseModel):
    decision: ReviewDecision = ReviewDecision.pending
    reviewer: str | None = None
    note: str | None = None
    at: datetime | None = None


class ReasoningProvenance(BaseModel):
    """How explanation text was produced. Shown in the UI and the dossier."""

    mode: str  # "deterministic" | "live_llm" | "demo_cache"
    provider: str | None = None  # "gemini", "groq", "openrouter", "ollama"
    model: str | None = None
    prompt_hash: str | None = None


class Finding(BaseModel):
    id: str = PydanticField(default_factory=lambda: new_id("fnd"))
    case_id: str
    status: FindingStatus
    category: FindingCategory
    severity: Severity
    confidence: float  # 0..1, calibrated within this detector only
    title: str  # short, human readable, never uses the word "fraud"
    doc_id: str | None = None  # primary document (None only if truly case-level)
    page: int | None = None
    bbox: BBox | None = None
    related_doc_ids: list[str] = PydanticField(default_factory=list)
    related_field_ids: list[str] = PydanticField(default_factory=list)
    related_finding_ids: list[str] = PydanticField(default_factory=list)
    evidence: list[EvidenceItem] = PydanticField(default_factory=list)
    explanation: str
    benign_alternatives: list[str] = PydanticField(default_factory=list)
    recommended_verification: list[str] = PydanticField(default_factory=list)
    detector: str  # stable id, e.g. "visual.ela", "cross.dob_mismatch"
    discrepancy_type: str | None = None  # cross_document findings; see CONTRACTS section 5
    fused_score: float | None = None  # region fusion result, 0..1
    reasoning: ReasoningProvenance = PydanticField(
        default_factory=lambda: ReasoningProvenance(mode="deterministic")
    )
    review: ReviewRecord = PydanticField(default_factory=ReviewRecord)
    created_at: datetime = PydanticField(default_factory=utcnow)


class EntityType(str, Enum):
    person = "person"
    date_of_birth = "date_of_birth"
    address = "address"
    employer = "employer"
    id_number = "id_number"
    account_number = "account_number"
    amount = "amount"


class EntityMention(BaseModel):
    doc_id: str
    field_id: str
    value_raw: str
    page: int
    bbox: BBox
    confidence: float


class Entity(BaseModel):
    id: str = PydanticField(default_factory=lambda: new_id("ent"))
    case_id: str
    type: EntityType
    canonical_value: str
    mentions: list[EntityMention] = PydanticField(default_factory=list)
    conflict: bool = False  # mentions disagree


class GraphNode(BaseModel):
    id: str
    kind: str  # "document" | "entity" | "finding"
    label: str
    ref_id: str  # doc id, entity id or finding id
    meta: dict[str, Any] = PydanticField(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    kind: str  # "mentions" | "agrees" | "conflicts" | "supports"
    conflict: bool = False  # rendered red
    label: str | None = None
    finding_id: str | None = None


class EvidenceGraph(BaseModel):
    case_id: str
    nodes: list[GraphNode] = PydanticField(default_factory=list)
    edges: list[GraphEdge] = PydanticField(default_factory=list)


class PipelineStage(str, Enum):
    submission = "submission"
    classification = "classification"
    ocr_extraction = "ocr_extraction"
    structure = "structure"
    visual_forensics = "visual_forensics"
    contextual_verification = "contextual_verification"
    cross_document = "cross_document"
    anomaly_investigation = "anomaly_investigation"
    evidence = "evidence"
    dossier = "dossier"


class StageProgress(BaseModel):
    stage: PipelineStage
    state: str = "pending"  # pending | running | done | degraded | failed
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    message: str | None = None


class CaseStatus(str, Enum):
    created = "created"
    running = "running"
    complete = "complete"
    failed = "failed"


class Case(BaseModel):
    id: str = PydanticField(default_factory=lambda: new_id("case"))
    name: str
    status: CaseStatus = CaseStatus.created
    risk_level: RiskLevel = RiskLevel.undetermined
    requires_human_review: bool = True  # always true unless nothing was found
    is_demo: bool = False
    demo_key: str | None = None
    progress: list[StageProgress] = PydanticField(default_factory=list)
    created_at: datetime = PydanticField(default_factory=utcnow)


class AuditEntry(BaseModel):
    seq: int
    ts: datetime
    case_id: str | None = None
    actor: str  # "system", "pipeline.ocr", "reviewer:<name>"
    action: str
    payload: dict[str, Any] = PydanticField(default_factory=dict)
    prev_hash: str
    entry_hash: str  # sha256(canonical_json(seq, ts, case_id, actor, action, payload, prev_hash))


class AuditVerification(BaseModel):
    ok: bool
    entries_checked: int
    first_bad_seq: int | None = None
    reason: str | None = None
    head_hash: str | None = None


class DossierDocumentOverview(BaseModel):
    doc_id: str
    filename: str
    sha256: str
    doc_type: DocType
    doc_type_confidence: float
    format: DocFormat
    pages: int
    status: ProcessingStatus
    status_message: str | None = None


class Dossier(BaseModel):
    """Sections 1 to 6 map one-to-one onto problem statement 7.1 to 7.6."""

    case_id: str
    case_name: str
    generated_at: datetime = PydanticField(default_factory=utcnow)
    risk_level: RiskLevel
    requires_human_review: bool = True
    disclaimer: str
    # 7.1
    overview: list[DossierDocumentOverview]
    # 7.2
    extracted: dict[str, list[Field]]  # doc_id -> fields
    structure: dict[str, list[Section]]  # doc_id -> layout
    tables: dict[str, list[Table]] = PydanticField(default_factory=dict)
    # 7.3
    contextual_findings: list[Finding]
    cross_document_findings: list[Finding]
    missing_or_duplicated: dict[str, dict[str, list[str]]]  # doc_id -> {missing, duplicated}
    # 7.4
    visual_findings: list[Finding]
    # 7.5
    traceability: list[dict[str, Any]]  # finding -> doc, page, bbox, field ids, evidence uris
    # 7.6
    summary: str
    potential_explanations: list[str]
    areas_for_verification: list[str]
    limitations: list[str]
    reasoning_modes: list[str]  # e.g. ["deterministic"], honest about what produced the text
    audit_head_hash: str | None = None
