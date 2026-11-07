// Mirrors models/schemas.py and docs/CONTRACTS.md section 3. Keep in step with those files.

export type FindingStatus = "OBSERVATION" | "INCONSISTENCY" | "POTENTIAL_MANIPULATION";
export type FindingCategory = "visual" | "structural" | "contextual" | "cross_document" | "metadata";
export type Severity = "info" | "low" | "medium" | "high";
export type RiskLevel = "low" | "medium" | "high" | "undetermined";
export type ReviewDecision = "pending" | "confirmed" | "dismissed" | "escalated";
export type DocType =
  | "application_form"
  | "id_proof"
  | "salary_slip"
  | "bank_statement"
  | "address_proof"
  | "declaration"
  | "unknown";
export type DocFormat = "png" | "jpg" | "scanned_pdf" | "digital_pdf" | "unsupported";
export type ProcessingStatus = "pending" | "processing" | "ok" | "degraded" | "unsupported" | "failed";
export type TextSource = "text_layer" | "ocr_rapid" | "ocr_tesseract" | "llm";
export type ValueType =
  | "string"
  | "name"
  | "date"
  | "money"
  | "number"
  | "id_number"
  | "address"
  | "account_number";

export interface BBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Word {
  text: string;
  confidence: number;
  bbox: BBox;
  page: number;
  source: TextSource;
}

export interface Page {
  index: number;
  width: number;
  height: number;
  image_path: string;
  text_source: TextSource | null;
  mean_ocr_confidence: number | null;
  words: Word[];
}

export interface Field {
  id: string;
  doc_id: string;
  name: string;
  label_raw: string | null;
  value_raw: string;
  value_norm: string | null;
  value_type: ValueType;
  confidence: number;
  page: number;
  bbox: BBox;
  source: TextSource;
  section: string | null;
}

export interface CaseField extends Field {
  doc_filename: string;
  doc_type: DocType;
}

export interface TableCell {
  text: string;
  confidence: number;
  bbox: BBox | null;
}

export interface Table {
  id: string;
  doc_id: string;
  name: string;
  page: number;
  bbox: BBox | null;
  headers: string[];
  rows: TableCell[][];
}

export interface Section {
  name: string;
  page: number;
  bbox: BBox;
  field_ids: string[];
  children: Section[];
}

export interface Document {
  id: string;
  case_id: string;
  filename: string;
  sha256: string;
  mime: string | null;
  size_bytes: number;
  format: DocFormat;
  doc_type: DocType;
  doc_type_confidence: number;
  classification_method: string | null;
  status: ProcessingStatus;
  status_message: string | null;
  pages: Page[];
  fields: Field[];
  tables: Table[];
  sections: Section[];
  missing_fields: string[];
  duplicated_fields: string[];
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  filename: string;
  format: DocFormat;
  doc_type: DocType;
  doc_type_confidence: number;
  status: ProcessingStatus;
  status_message: string | null;
  page_count: number;
  field_count: number;
  finding_count: number;
}

export type EvidenceKind = "crop" | "heatmap" | "raw_value" | "metadata" | "comparison" | "field_ref";

export interface EvidenceItem {
  kind: EvidenceKind;
  label: string;
  uri: string | null;
  doc_id: string | null;
  page: number | null;
  bbox: BBox | null;
  field_id: string | null;
  data: Record<string, unknown>;
}

export interface ReviewRecord {
  decision: ReviewDecision;
  reviewer: string | null;
  note: string | null;
  at: string | null;
}

export interface ReasoningProvenance {
  mode: string; // "deterministic" | "live_llm" | "demo_cache"
  provider: string | null;
  model: string | null;
  prompt_hash: string | null;
}

export interface Finding {
  id: string;
  case_id: string;
  status: FindingStatus;
  category: FindingCategory;
  severity: Severity;
  confidence: number;
  title: string;
  doc_id: string | null;
  page: number | null;
  bbox: BBox | null;
  related_doc_ids: string[];
  related_field_ids: string[];
  related_finding_ids: string[];
  evidence: EvidenceItem[];
  explanation: string;
  benign_alternatives: string[];
  recommended_verification: string[];
  detector: string;
  discrepancy_type: string | null;
  fused_score: number | null;
  reasoning: ReasoningProvenance;
  review: ReviewRecord;
  created_at: string;
}

export type EntityType =
  | "person"
  | "date_of_birth"
  | "address"
  | "employer"
  | "id_number"
  | "account_number"
  | "amount";

export interface EntityMention {
  doc_id: string;
  field_id: string;
  value_raw: string;
  page: number;
  bbox: BBox;
  confidence: number;
}

export interface Entity {
  id: string;
  case_id: string;
  type: EntityType;
  canonical_value: string;
  mentions: EntityMention[];
  conflict: boolean;
}

export interface GraphNode {
  id: string;
  kind: string; // "document" | "entity" | "finding"
  label: string;
  ref_id: string;
  meta: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string; // "mentions" | "agrees" | "conflicts" | "supports"
  conflict: boolean;
  label: string | null;
  finding_id: string | null;
}

export interface EvidenceGraph {
  case_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export type PipelineStage =
  | "submission"
  | "classification"
  | "ocr_extraction"
  | "structure"
  | "visual_forensics"
  | "contextual_verification"
  | "cross_document"
  | "anomaly_investigation"
  | "evidence"
  | "dossier";

export interface StageProgress {
  stage: PipelineStage;
  state: string; // pending | running | done | degraded | failed
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  message: string | null;
}

export type CaseStatus = "created" | "running" | "complete" | "failed";

export interface Case {
  id: string;
  name: string;
  status: CaseStatus;
  risk_level: RiskLevel;
  requires_human_review: boolean;
  is_demo: boolean;
  demo_key: string | null;
  progress: StageProgress[];
  created_at: string;
}

export interface CaseDetail {
  case: Case;
  documents: DocumentSummary[];
}

export interface ProgressEvent {
  case_id: string;
  status: CaseStatus;
  stages: StageProgress[];
}

export interface AuditEntry {
  seq: number;
  ts: string;
  case_id: string | null;
  actor: string;
  action: string;
  payload: Record<string, unknown>;
  prev_hash: string;
  entry_hash: string;
}

export interface AuditVerification {
  ok: boolean;
  entries_checked: number;
  first_bad_seq: number | null;
  reason: string | null;
  head_hash: string | null;
}

export interface DossierDocumentOverview {
  doc_id: string;
  filename: string;
  sha256: string;
  doc_type: DocType;
  doc_type_confidence: number;
  format: DocFormat;
  pages: number;
  status: ProcessingStatus;
  status_message: string | null;
}

export interface Dossier {
  case_id: string;
  case_name: string;
  generated_at: string;
  risk_level: RiskLevel;
  requires_human_review: boolean;
  disclaimer: string;
  overview: DossierDocumentOverview[];
  extracted: Record<string, Field[]>;
  structure: Record<string, Section[]>;
  tables: Record<string, Table[]>;
  contextual_findings: Finding[];
  cross_document_findings: Finding[];
  missing_or_duplicated: Record<string, { missing?: string[]; duplicated?: string[] }>;
  visual_findings: Finding[];
  traceability: Array<Record<string, unknown>>;
  summary: string;
  potential_explanations: string[];
  areas_for_verification: string[];
  limitations: string[];
  reasoning_modes: string[];
  audit_head_hash: string | null;
}

export interface DemoCase {
  key: string;
  name: string;
  description: string;
  documents: string[];
  /** Other demo cases this one is compared with. Loading it loads them too. */
  needs?: string[] | null;
}

export interface Overlay {
  kind: string;
  label: string;
  url: string;
}

export type CapabilityMode = "offline" | "demo_cache" | "live" | "deterministic";

export interface ProviderStatus {
  provider: string;
  key_present: boolean;
  status: string;
  model: string | null;
}

export interface ToolStatus {
  name: string;
  available: boolean;
  detail: string | null;
}

export interface MatrixRow {
  capability: string;
  status: string; // Implemented | Partial | Planned | Unsupported
  notes: string | null;
}

export interface Capabilities {
  mode: CapabilityMode;
  providers: ProviderStatus[];
  tools: ToolStatus[];
  matrix: MatrixRow[];
  limitations: string[];
  llm_usage: {
    calls: number;
    tokens: number;
    by_provider: Record<string, unknown>;
  };
}

export interface Health {
  status: string;
  version: string;
  offline: boolean;
  demo_cache: boolean;
}
