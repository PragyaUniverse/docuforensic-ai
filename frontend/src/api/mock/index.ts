// Development fixtures, used ONLY when VITE_USE_MOCK=1. The app shows a MOCK DATA banner in this mode.
// All people, IDs and documents here are invented.
import type { Api } from "../client";
import type {
  AuditEntry,
  BBox,
  Case,
  CaseField,
  Document,
  DocumentSummary,
  Field,
  Finding,
  PipelineStage,
  StageProgress,
} from "../types";

const W = 1654;
const H = 2339;
const now = () => new Date().toISOString();

type Line = { label: string; value: string; y: number; name: string; conf: number; id: string; tamper?: boolean };

const svgPage = (title: string, sub: string, lines: Line[], extra = "") => {
  const rows = lines
    .map(
      (l) => `<text x="150" y="${l.y}" font-size="34" fill="#333" font-family="Arial">${l.label}</text>
      ${l.tamper ? `<rect x="696" y="${l.y - 36}" width="330" height="48" fill="#fbfaf4"/>` : ""}
      <text x="700" y="${l.y}" font-size="${l.tamper ? 37 : 34}" fill="#111" font-family="${l.tamper ? "Georgia" : "Arial"}">${l.value}</text>`,
    )
    .join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#fdfdf8"/>
  <text x="150" y="220" font-size="58" font-weight="700" fill="#14213d" font-family="Arial">${title}</text>
  <text x="150" y="280" font-size="28" fill="#555" font-family="Arial">${sub}</text>
  <rect x="150" y="310" width="1354" height="4" fill="#14213d"/>
  ${rows}${extra}
  <text x="827" y="1500" font-size="140" fill="#000" fill-opacity="0.05" text-anchor="middle" font-family="Arial" transform="rotate(-28 827 1500)">SYNTHETIC</text>
  </svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
};

const heat = (boxes: BBox[]) => {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <defs><radialGradient id="g"><stop offset="0" stop-color="#ff3b1f" stop-opacity=".95"/><stop offset=".6" stop-color="#ffb01f" stop-opacity=".5"/><stop offset="1" stop-color="#ffb01f" stop-opacity="0"/></radialGradient></defs>
  ${boxes.map((b) => `<ellipse cx="${(b.x0 + b.x1) / 2}" cy="${(b.y0 + b.y1) / 2}" rx="${(b.x1 - b.x0) * 0.8}" ry="${(b.y1 - b.y0) * 1.4}" fill="url(#g)"/>`).join("")}
  </svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
};

const CASE_ID = "case_mock000001";
const box = (y: number, x0 = 696, x1 = 1120): BBox => ({ x0, y0: y - 38, x1, y1: y + 12 });

const mk = (doc: string, l: Line): Field => ({
  id: l.id,
  doc_id: doc,
  name: l.name,
  label_raw: l.label,
  value_raw: l.value,
  value_norm: null,
  value_type: "string",
  confidence: l.conf,
  page: 0,
  bbox: box(l.y, 696, l.value.length > 28 ? 1500 : 1120),
  source: "ocr_rapid",
  section: "body",
});

const slipLines: Line[] = [
  { id: "fld_s1", name: "person_name", label: "Employee name", value: "Meera R. Iyer", y: 420, conf: 0.98 },
  { id: "fld_s2", name: "employer_name", label: "Employer", value: "Northwind Instruments Pvt Ltd", y: 490, conf: 0.97 },
  { id: "fld_s3", name: "pay_period", label: "Pay period", value: "September 2026", y: 560, conf: 0.96 },
  { id: "fld_s4", name: "pan_number", label: "PAN", value: "ABCPI1234K", y: 630, conf: 0.51 },
  { id: "fld_s5", name: "basic_pay", label: "Basic pay", value: "Rs. 42,000.00", y: 780, conf: 0.97 },
  { id: "fld_s6", name: "hra", label: "HRA", value: "Rs. 16,800.00", y: 850, conf: 0.96 },
  { id: "fld_s7", name: "gross_pay", label: "Gross pay", value: "Rs. 64,200.00", y: 920, conf: 0.97 },
  { id: "fld_s8", name: "total_deductions", label: "Total deductions", value: "Rs. 8,800.00", y: 990, conf: 0.95 },
  { id: "fld_s9", name: "net_pay", label: "Net pay", value: "Rs. 85,400.00", y: 1060, conf: 0.93, tamper: true },
];
const bankLines: Line[] = [
  { id: "fld_b1", name: "person_name", label: "Account holder", value: "Meera R Iyer", y: 420, conf: 0.97 },
  { id: "fld_b2", name: "address", label: "Address", value: "14 Lake View Road, Pune 411001", y: 490, conf: 0.94 },
  { id: "fld_b3", name: "bank_account_number", label: "Account no.", value: "0001 2233 4455", y: 560, conf: 0.98 },
  { id: "fld_b4", name: "salary_credit", label: "Salary credit, Oct 01", value: "Rs. 55,400.00", y: 840, conf: 0.96 },
];
const formLines: Line[] = [
  { id: "fld_a1", name: "person_name", label: "Applicant name", value: "Meera R. Iyer", y: 420, conf: 0.98 },
  { id: "fld_a2", name: "date_of_birth", label: "Date of birth", value: "14/03/1991", y: 490, conf: 0.97 },
  { id: "fld_a3", name: "address", label: "Address", value: "14 Lakeview Rd, Pune 411001", y: 560, conf: 0.95 },
  { id: "fld_a4", name: "employer_name", label: "Employer", value: "Northwind Instruments Pvt Ltd", y: 630, conf: 0.97 },
  { id: "fld_a5", name: "declared_monthly_income", label: "Declared monthly income", value: "Rs. 85,400.00", y: 700, conf: 0.97 },
];
const idLines: Line[] = [
  { id: "fld_i1", name: "person_name", label: "Name", value: "Meera R Iyer", y: 420, conf: 0.96 },
  { id: "fld_i2", name: "date_of_birth", label: "DOB", value: "14/08/1991", y: 490, conf: 0.94 },
  { id: "fld_i3", name: "id_number", label: "ID number", value: "2345 6789 0123", y: 560, conf: 0.97 },
];

const SIG = `<path d="M180 1880 q60 -90 110 -10 t100 -20 t90 10" stroke="#123" stroke-width="5" fill="none"/>`;

const specs = [
  { id: "doc_form", filename: "application_form.png", type: "application_form", format: "png", title: "Loan Application Form", sub: "Application A-20419", lines: formLines, extra: SIG },
  { id: "doc_slip", filename: "salary_slip.png", type: "salary_slip", format: "png", title: "Salary Slip", sub: "Northwind Instruments Pvt Ltd", lines: slipLines, extra: SIG },
  { id: "doc_bank", filename: "bank_statement.pdf", type: "bank_statement", format: "digital_pdf", title: "Account Statement", sub: "Harbor Bank", lines: bankLines, extra: "" },
  { id: "doc_id", filename: "id_proof.jpg", type: "id_proof", format: "jpg", title: "Identity Card", sub: "Fictional issuer", lines: idLines, extra: "" },
] as const;

const images: Record<string, string> = {};
const docs: Document[] = specs.map((s) => {
  images[s.id] = svgPage(s.title, s.sub, [...s.lines], s.extra);
  return {
    id: s.id,
    case_id: CASE_ID,
    filename: s.filename,
    sha256: "9f2c81ab44d0e7a1c5b3f6d2908e77f1a3c4d5e6f708192a3b4c5d6e7f809112",
    mime: null,
    size_bytes: 482113,
    format: s.format,
    doc_type: s.type,
    doc_type_confidence: 0.94,
    classification_method: "keywords",
    status: "ok",
    status_message: null,
    pages: [
      { index: 0, width: W, height: H, image_path: "", text_source: s.format === "digital_pdf" ? "text_layer" : "ocr_rapid", mean_ocr_confidence: 0.95, words: [] },
    ],
    fields: s.lines.map((l) => mk(s.id, l)),
    tables:
      s.id === "doc_bank"
        ? [
            {
              id: "tbl_tx",
              doc_id: s.id,
              name: "transactions",
              page: 0,
              bbox: null,
              headers: ["date", "description", "debit", "credit", "balance"],
              rows: [
                ["2026-10-01", "SALARY NORTHWIND", "", "55,400.00", "71,020.00"],
                ["2026-10-05", "RENT", "18,000.00", "", "53,020.00"],
              ].map((r) => r.map((c, j) => ({ text: c, confidence: 0.96, bbox: box(840, 150 + j * 270, 400 + j * 270) }))),
            },
          ]
        : [],
    sections: [
      { name: "header", page: 0, bbox: { x0: 150, y0: 160, x1: 1504, y1: 320 }, field_ids: [], children: [] },
      { name: "body", page: 0, bbox: { x0: 150, y0: 370, x1: 1504, y1: 1120 }, field_ids: s.lines.map((l) => l.id), children: [] },
    ],
    missing_fields: s.id === "doc_form" ? ["phone"] : [],
    duplicated_fields: [],
    metadata: {},
    created_at: now(),
  } as Document;
});
const unsupported: Document = {
  ...docs[0],
  id: "doc_bad",
  filename: "notes.docx",
  format: "unsupported",
  doc_type: "unknown",
  doc_type_confidence: 0,
  status: "unsupported",
  status_message: "Unsupported file type (Word document). Accepted: PNG, JPG, PDF. This file was recorded and not analysed.",
  pages: [],
  fields: [],
  tables: [],
  sections: [],
  missing_fields: [],
};
docs.push(unsupported);
const byId = (id: string) => docs.find((d) => d.id === id)!;
const fieldOf = (id: string) => docs.flatMap((d) => d.fields).find((f) => f.id === id)!;

const base = {
  case_id: CASE_ID,
  related_doc_ids: [] as string[],
  related_field_ids: [] as string[],
  related_finding_ids: [] as string[],
  discrepancy_type: null,
  fused_score: null,
  reasoning: { mode: "deterministic", provider: null, model: null, prompt_hash: null },
  review: { decision: "pending" as const, reviewer: null, note: null, at: null },
  created_at: now(),
};

const fieldEv = (id: string) => {
  const f = fieldOf(id);
  return { kind: "field_ref" as const, label: f.label_raw ?? f.name, uri: null, doc_id: f.doc_id, page: f.page, bbox: f.bbox, field_id: f.id, data: { value: f.value_raw } };
};

let findings: Finding[] = [
  {
    ...base,
    id: "fnd_over",
    status: "POTENTIAL_MANIPULATION",
    category: "visual",
    severity: "high",
    confidence: 0.82,
    fused_score: 0.86,
    title: "Net pay value sits on a patched background in a different typeface",
    doc_id: "doc_slip",
    page: 0,
    bbox: box(1060, 690, 1040),
    related_doc_ids: ["doc_bank"],
    related_finding_ids: ["fnd_sal"],
    evidence: [
      { kind: "crop", label: "Source region", uri: null, doc_id: "doc_slip", page: 0, bbox: box(1060, 690, 1040), field_id: null, data: {} },
      { kind: "raw_value", label: "Measured values", uri: null, doc_id: null, page: null, bbox: null, field_id: null, data: { ela_zscore: 6.4, stroke_width_ratio: 1.31, background_delta_e: 3.2 } },
    ],
    explanation: "The net pay digits have a stroke width 1.31 times the rest of the column, and the background behind them differs from the surrounding page. Both signals overlap the same region.",
    benign_alternatives: ["Payroll software may render totals in a separate style.", "A rescan can introduce local compression differences."],
    recommended_verification: ["Request the payroll register for this period from the employer.", "Compare against an earlier salary slip from the same employer."],
    detector: "visual.overwrite",
  },
  {
    ...base,
    id: "fnd_sig",
    status: "POTENTIAL_MANIPULATION",
    category: "visual",
    severity: "medium",
    confidence: 0.74,
    title: "Identical signature pixels on two documents",
    doc_id: "doc_form",
    page: 0,
    bbox: { x0: 170, y0: 1800, x1: 500, y1: 1900 },
    evidence: [
      { kind: "crop", label: "Signature on application form", uri: null, doc_id: "doc_form", page: 0, bbox: { x0: 170, y0: 1800, x1: 500, y1: 1900 }, field_id: null, data: { phash_distance: 1 } },
      { kind: "crop", label: "Signature on salary slip", uri: null, doc_id: "doc_slip", page: 0, bbox: { x0: 170, y0: 1800, x1: 500, y1: 1900 }, field_id: null, data: {} },
    ],
    explanation: "A handwritten signature varies each time it is written. These two regions differ by a perceptual hash distance of 1, which suggests one may be a copy of the other.",
    benign_alternatives: ["An institution may apply a stored digital signature."],
    recommended_verification: ["Obtain a fresh wet signature."],
    detector: "visual.signature_reuse",
  },
  {
    ...base,
    id: "fnd_sal",
    status: "INCONSISTENCY",
    category: "cross_document",
    severity: "high",
    confidence: 0.93,
    title: "Salary slip net pay differs from the bank salary credit",
    doc_id: "doc_slip",
    page: 0,
    bbox: fieldOf("fld_s9").bbox,
    related_doc_ids: ["doc_bank"],
    related_field_ids: ["fld_s9", "fld_b4"],
    related_finding_ids: ["fnd_over"],
    discrepancy_type: "salary_vs_bank_credit",
    evidence: [fieldEv("fld_s9"), fieldEv("fld_b4")],
    explanation: "The slip states net pay of Rs. 85,400.00 while the account received Rs. 55,400.00 for the same period, a difference of Rs. 30,000.00.",
    benign_alternatives: ["Part of the salary may be paid into a second account.", "A credit may have been split across dates."],
    recommended_verification: ["Request statements for all declared accounts."],
    detector: "cross.salary_vs_bank",
  },
  {
    ...base,
    id: "fnd_dob",
    status: "INCONSISTENCY",
    category: "cross_document",
    severity: "high",
    confidence: 0.9,
    title: "Date of birth differs between application and ID",
    doc_id: "doc_form",
    page: 0,
    bbox: fieldOf("fld_a2").bbox,
    related_doc_ids: ["doc_id"],
    related_field_ids: ["fld_a2", "fld_i2"],
    discrepancy_type: "dob_mismatch",
    evidence: [fieldEv("fld_a2"), fieldEv("fld_i2")],
    explanation: "The application gives 14/03/1991 and the ID gives 14/08/1991. The month differs, which could also be an OCR misread of a similar digit.",
    benign_alternatives: ["OCR can confuse 3 and 8 on a low-quality scan."],
    recommended_verification: ["Inspect the original ID."],
    detector: "cross.dob_mismatch",
  },
  {
    ...base,
    id: "fnd_addr",
    status: "INCONSISTENCY",
    category: "cross_document",
    severity: "medium",
    confidence: 0.71,
    title: "Address written differently across documents",
    doc_id: "doc_form",
    page: 0,
    bbox: fieldOf("fld_a3").bbox,
    related_doc_ids: ["doc_bank"],
    related_field_ids: ["fld_a3", "fld_b2"],
    discrepancy_type: "address_variant",
    evidence: [fieldEv("fld_a3"), fieldEv("fld_b2")],
    explanation: "The two addresses match closely but not exactly.",
    benign_alternatives: ["Abbreviations are common."],
    recommended_verification: ["Confirm with a recent utility bill."],
    detector: "cross.address_variant",
  },
  {
    ...base,
    id: "fnd_arith",
    status: "INCONSISTENCY",
    category: "contextual",
    severity: "high",
    confidence: 0.97,
    title: "Net pay does not equal gross pay minus deductions",
    doc_id: "doc_slip",
    page: 0,
    bbox: fieldOf("fld_s9").bbox,
    related_field_ids: ["fld_s7", "fld_s8", "fld_s9"],
    evidence: [fieldEv("fld_s7"), fieldEv("fld_s8"), fieldEv("fld_s9")],
    explanation: "64,200.00 minus 8,800.00 is 55,400.00, but the slip states 85,400.00.",
    benign_alternatives: ["An unlisted allowance could explain part of the gap."],
    recommended_verification: ["Ask for a full payroll breakdown."],
    detector: "context.arithmetic_salary",
  },
  {
    ...base,
    id: "fnd_exif",
    status: "OBSERVATION",
    category: "metadata",
    severity: "info",
    confidence: 1,
    title: "Image metadata lists an editing application",
    doc_id: "doc_id",
    page: 0,
    bbox: null,
    evidence: [{ kind: "metadata", label: "EXIF", uri: null, doc_id: "doc_id", page: null, bbox: null, field_id: null, data: { Software: "ImageEditor 2.1", ModifyDate: "2026:10:02 11:14:03" } }],
    explanation: "The metadata records an editing application. Many legitimate workflows resave images, so this alone means little.",
    benign_alternatives: ["Scanner software often writes this tag."],
    recommended_verification: ["Ask for the original capture."],
    detector: "metadata.exif",
  },
  {
    ...base,
    id: "fnd_ela",
    status: "OBSERVATION",
    category: "visual",
    severity: "low",
    confidence: 0.61,
    title: "Compression error is elevated in one region",
    doc_id: "doc_slip",
    page: 0,
    bbox: box(1060, 690, 1040),
    evidence: [{ kind: "raw_value", label: "Measured values", uri: null, doc_id: null, page: null, bbox: null, field_id: null, data: { ela_zscore: 6.4 } }],
    explanation: "Error level analysis shows higher residual here than the page median.",
    benign_alternatives: ["High-contrast text naturally raises this measure."],
    recommended_verification: [],
    detector: "visual.ela",
  },
];

const STAGES: PipelineStage[] = ["submission", "classification", "ocr_extraction", "structure", "visual_forensics", "contextual_verification", "cross_document", "anomaly_investigation", "evidence", "dossier"];
const DUR = [84, 120, 2310, 310, 3120, 96, 240, 420, 180, 610];
const done = (): StageProgress[] =>
  STAGES.map((stage, i) => ({
    stage,
    state: stage === "anomaly_investigation" ? "degraded" : "done",
    started_at: now(),
    finished_at: now(),
    duration_ms: DUR[i],
    message: stage === "anomaly_investigation" ? "No LLM available. Explanations came from deterministic rules." : null,
  }));

let theCase: Case = {
  id: CASE_ID,
  name: "Case B + C: Meera R. Iyer (mock)",
  status: "complete",
  risk_level: "high",
  requires_human_review: true,
  is_demo: true,
  demo_key: "case_b_visual",
  progress: done(),
  created_at: now(),
};

const summary = (d: Document): DocumentSummary => ({
  id: d.id,
  filename: d.filename,
  format: d.format,
  doc_type: d.doc_type,
  doc_type_confidence: d.doc_type_confidence,
  status: d.status,
  status_message: d.status_message,
  page_count: d.pages.length,
  field_count: d.fields.length,
  finding_count: findings.filter((f) => f.doc_id === d.id).length,
});

const genesis = "0".repeat(64);
const hex = (n: number) => (n * 2654435761 >>> 0).toString(16).padStart(8, "0").repeat(8);
const audit: AuditEntry[] = ["case.created", "document.ingested", "document.ingested", "stage.classification", "stage.ocr_extraction", "stage.visual_forensics", "finding.recorded", "stage.cross_document", "finding.recorded", "stage.dossier"].map((action, i) => ({
  seq: i + 1,
  ts: now(),
  case_id: CASE_ID,
  actor: i < 3 ? "system" : `pipeline.${action.split(".")[1] ?? "core"}`,
  action,
  payload: { detail: action, n: i },
  prev_hash: i === 0 ? genesis : hex(i),
  entry_hash: hex(i + 1),
}));
let tampered: number | null = null;

const later = <T,>(v: T, ms = 120): Promise<T> => new Promise((r) => setTimeout(() => r(v), ms));

export const mockApi: Api = {
  health: () => later({ status: "ok", version: "mock", offline: false, demo_cache: false }),
  capabilities: () =>
    later({
      mode: "deterministic",
      providers: [
        { provider: "gemini", key_present: false, status: "no key", model: null },
        { provider: "groq", key_present: false, status: "no key", model: null },
        { provider: "openrouter", key_present: false, status: "no key", model: null },
        { provider: "ollama", key_present: false, status: "working", model: "qwen2.5:7b" },
      ],
      tools: [
        { name: "RapidOCR", available: true, detail: "rapidocr-onnxruntime" },
        { name: "Tesseract", available: true, detail: "5.x" },
        { name: "PyMuPDF", available: true, detail: null },
      ],
      matrix: [
        { capability: "Printed OCR", status: "Implemented", notes: "RapidOCR with Tesseract fallback" },
        { capability: "Handwriting recognition", status: "Unsupported", notes: "Not attempted" },
        { capability: "Copy-move localization", status: "Partial", notes: "ORB keypoints only" },
        { capability: "Multilingual documents", status: "Planned", notes: "English only today" },
      ],
      limitations: ["Mock limitation text."],
      llm_usage: { calls: 0, tokens: 0, by_provider: {} },
    }),
  demoCases: () =>
    later([
      { key: "case_a_clean", name: "Clean application", description: "All documents agree. Shows the system does not cry wolf.", documents: ["a", "b", "c", "d"] },
      { key: "case_b_visual", name: "Visual tampering", description: "An overwritten salary figure, a pasted photo, a reused signature.", documents: ["a", "b", "c"] },
      { key: "case_c_crossdoc", name: "Cross-document conflicts", description: "DOB, salary credit, address and employer discrepancies.", documents: ["a", "b", "c", "d"] },
      { key: "case_d_pdf", name: "PDF structure", description: "A digital PDF whose text layer disagrees with its rendered pixels.", documents: ["a"] },
    ]),
  loadDemoCase: () => later(theCase),
  createCase: (name) => later({ ...theCase, name }),
  listCases: () => later([theCase]),
  getCase: () => later({ case: theCase, documents: docs.map(summary) }),
  uploadDocuments: () => later(docs.map(summary), 500),
  runCase: () => {
    theCase = { ...theCase, status: "running", progress: [] };
    return later(undefined);
  },
  subscribeProgress: (caseId, h) => {
    let i = 0;
    const final = done();
    const stages: StageProgress[] = [];
    const t = window.setInterval(() => {
      if (i < STAGES.length) {
        stages[i] = final[i];
        const running = i + 1 < STAGES.length ? [{ stage: STAGES[i + 1], state: "running", started_at: now(), finished_at: null, duration_ms: null, message: null }] : [];
        h.onProgress({ case_id: caseId, status: "running", stages: [...stages, ...running] });
        i++;
      } else {
        window.clearInterval(t);
        theCase = { ...theCase, status: "complete", progress: final };
        h.onProgress({ case_id: caseId, status: "complete", stages: final });
        h.onDone();
      }
    }, 450);
    return () => window.clearInterval(t);
  },
  getDocument: (_c, id) => later(byId(id)),
  pageImageUrl: (_c, id) => images[id] ?? "",
  listOverlays: (_c, id) =>
    later(
      id === "doc_slip"
        ? [
            { kind: "ela", label: "ELA", url: heat([box(1060, 690, 1040)]) },
            { kind: "noise", label: "Noise residual", url: heat([box(1060, 690, 1040), box(630, 700, 900)]) },
          ]
        : [],
    ),
  resolveUrl: (u) => u,
  fileUrl: (u) => u,
  findings: () => later(findings),
  reviewFinding: (id, decision, reviewer, note) => {
    findings = findings.map((f) => (f.id === id ? { ...f, review: { decision, reviewer, note, at: now() } } : f));
    return later(findings.find((f) => f.id === id)!);
  },
  fields: () => later(docs.flatMap((d) => d.fields.map((f): CaseField => ({ ...f, doc_filename: d.filename, doc_type: d.doc_type })))),
  entities: () =>
    later([
      { id: "ent_dob", case_id: CASE_ID, type: "date_of_birth", canonical_value: "14/03/1991 vs 14/08/1991", conflict: true, mentions: ["fld_a2", "fld_i2"].map((id) => { const f = fieldOf(id); return { doc_id: f.doc_id, field_id: f.id, value_raw: f.value_raw, page: 0, bbox: f.bbox, confidence: f.confidence }; }) },
      { id: "ent_name", case_id: CASE_ID, type: "person", canonical_value: "Meera R. Iyer", conflict: false, mentions: ["fld_a1", "fld_s1", "fld_b1", "fld_i1"].map((id) => { const f = fieldOf(id); return { doc_id: f.doc_id, field_id: f.id, value_raw: f.value_raw, page: 0, bbox: f.bbox, confidence: f.confidence }; }) },
      { id: "ent_addr", case_id: CASE_ID, type: "address", canonical_value: "14 Lake View Road, Pune 411001", conflict: true, mentions: ["fld_a3", "fld_b2"].map((id) => { const f = fieldOf(id); return { doc_id: f.doc_id, field_id: f.id, value_raw: f.value_raw, page: 0, bbox: f.bbox, confidence: f.confidence }; }) },
    ]),
  graph: () =>
    later({
      case_id: CASE_ID,
      nodes: [
        ...docs.filter((d) => d.pages.length).map((d) => ({ id: `n_${d.id}`, kind: "document", label: d.filename, ref_id: d.id, meta: {} })),
        { id: "n_ent_name", kind: "entity", label: "Meera R. Iyer", ref_id: "ent_name", meta: {} },
        { id: "n_ent_dob", kind: "entity", label: "14/03/1991 vs 14/08/1991", ref_id: "ent_dob", meta: {} },
        { id: "n_ent_addr", kind: "entity", label: "14 Lake View Road", ref_id: "ent_addr", meta: {} },
        ...findings.filter((f) => f.category === "cross_document").map((f) => ({ id: `n_${f.id}`, kind: "finding", label: f.title, ref_id: f.id, meta: {} })),
      ],
      edges: [
        { id: "e1", source: "n_doc_form", target: "n_ent_name", kind: "agrees", conflict: false, label: null, finding_id: null },
        { id: "e2", source: "n_doc_slip", target: "n_ent_name", kind: "agrees", conflict: false, label: null, finding_id: null },
        { id: "e3", source: "n_doc_bank", target: "n_ent_name", kind: "agrees", conflict: false, label: null, finding_id: null },
        { id: "e4", source: "n_doc_id", target: "n_ent_name", kind: "agrees", conflict: false, label: null, finding_id: null },
        { id: "e5", source: "n_doc_form", target: "n_ent_dob", kind: "conflicts", conflict: true, label: "DOB differs", finding_id: "fnd_dob" },
        { id: "e6", source: "n_doc_id", target: "n_ent_dob", kind: "conflicts", conflict: true, label: "DOB differs", finding_id: "fnd_dob" },
        { id: "e7", source: "n_doc_form", target: "n_ent_addr", kind: "conflicts", conflict: true, label: "variant", finding_id: "fnd_addr" },
        { id: "e8", source: "n_doc_bank", target: "n_ent_addr", kind: "conflicts", conflict: true, label: "variant", finding_id: "fnd_addr" },
        { id: "e9", source: "n_ent_dob", target: "n_fnd_dob", kind: "supports", conflict: false, label: null, finding_id: "fnd_dob" },
        { id: "e10", source: "n_ent_addr", target: "n_fnd_addr", kind: "supports", conflict: false, label: null, finding_id: "fnd_addr" },
        { id: "e11", source: "n_doc_slip", target: "n_fnd_sal", kind: "conflicts", conflict: true, label: "30,000 gap", finding_id: "fnd_sal" },
      ],
    }),
  dossier: () =>
    later({
      case_id: CASE_ID,
      case_name: theCase.name,
      generated_at: now(),
      risk_level: "high",
      requires_human_review: true,
      disclaimer: "Machine-generated triage for human review. It is not a finding of wrongdoing.",
      overview: docs.map((d) => ({ doc_id: d.id, filename: d.filename, sha256: d.sha256, doc_type: d.doc_type, doc_type_confidence: d.doc_type_confidence, format: d.format, pages: d.pages.length, status: d.status, status_message: d.status_message })),
      extracted: Object.fromEntries(docs.map((d) => [d.id, d.fields])),
      structure: Object.fromEntries(docs.map((d) => [d.id, d.sections])),
      tables: Object.fromEntries(docs.map((d) => [d.id, d.tables])),
      contextual_findings: findings.filter((f) => f.category === "contextual"),
      cross_document_findings: findings.filter((f) => f.category === "cross_document"),
      missing_or_duplicated: { doc_form: { missing: ["phone"], duplicated: [] } },
      visual_findings: findings.filter((f) => f.category === "visual" || f.category === "metadata"),
      traceability: findings.map((f) => ({ finding: f.id, doc: f.doc_id, page: f.page, bbox: f.bbox, status: f.status })),
      summary: "Mock summary. Several values disagree across documents and one region shows overlapping forensic signals.",
      potential_explanations: ["Benign clerical variation", "Second salary account"],
      areas_for_verification: ["Payroll register", "Original ID"],
      limitations: ["Synthetic data only."],
      reasoning_modes: ["deterministic"],
      audit_head_hash: hex(10),
    }),
  dossierPdfUrl: () => "#",
  audit: () => later(audit),
  verifyAudit: () =>
    later(
      tampered === null
        ? { ok: true, entries_checked: audit.length, first_bad_seq: null, reason: null, head_hash: hex(10) }
        : { ok: false, entries_checked: tampered, first_bad_seq: tampered, reason: `Entry #${tampered}: stored hash does not match its recomputed hash.`, head_hash: null },
      300,
    ),
  tamperAudit: () => {
    tampered = 6;
    return later({ tampered_seq: 6 });
  },
  restoreAudit: () => {
    tampered = null;
    return later(undefined);
  },
};
