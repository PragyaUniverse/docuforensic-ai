import type {
  AuditEntry,
  AuditVerification,
  Capabilities,
  Case,
  CaseDetail,
  CaseField,
  DemoCase,
  Document,
  DocumentSummary,
  Dossier,
  Entity,
  EvidenceGraph,
  Finding,
  Health,
  Overlay,
  ProgressEvent,
  ReviewDecision,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

export interface ProgressHandlers {
  onProgress: (e: ProgressEvent) => void;
  onDone: () => void;
  onConnectionLost: () => void;
}

export interface Api {
  health(): Promise<Health>;
  capabilities(): Promise<Capabilities>;
  demoCases(): Promise<DemoCase[]>;
  loadDemoCase(key: string): Promise<Case>;
  createCase(name: string): Promise<Case>;
  listCases(): Promise<Case[]>;
  getCase(id: string): Promise<CaseDetail>;
  uploadDocuments(caseId: string, files: File[]): Promise<DocumentSummary[]>;
  runCase(caseId: string): Promise<void>;
  subscribeProgress(caseId: string, h: ProgressHandlers): () => void;
  getDocument(caseId: string, docId: string): Promise<Document>;
  pageImageUrl(caseId: string, docId: string, page: number): string;
  listOverlays(caseId: string, docId: string, page: number): Promise<Overlay[]>;
  resolveUrl(url: string): string;
  fileUrl(uri: string): string;
  findings(caseId: string): Promise<Finding[]>;
  reviewFinding(id: string, decision: ReviewDecision, reviewer: string, note: string): Promise<Finding>;
  fields(caseId: string): Promise<CaseField[]>;
  entities(caseId: string): Promise<Entity[]>;
  graph(caseId: string): Promise<EvidenceGraph>;
  dossier(caseId: string): Promise<Dossier>;
  dossierPdfUrl(caseId: string): string;
  audit(caseId: string): Promise<AuditEntry[]>;
  verifyAudit(caseId: string): Promise<AuditVerification>;
  tamperAudit(): Promise<{ tampered_seq: number }>;
  restoreAudit(): Promise<void>;
}

export const MOCK_MODE = import.meta.env.VITE_USE_MOCK === "1";
