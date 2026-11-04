# Shared Contracts

Everything in this file is binding for all agents. The canonical schemas are the Pydantic
models in [`models/schemas.py`](../models/schemas.py). If you need a contract change, make the
smallest additive change and list it in your final report.

Problem statement: `docs/PROBLEM_STATEMENT.md`. Run all Python as `.venv/bin/python -m ...`,
because the repo path may contain spaces (console-script shebangs break). Python 3.12.

## 1. Global rules

1. **Never output a verdict.** The word "fraud" must not appear in any finding, UI label, dossier
   or log. Finding statuses are only `OBSERVATION`, `INCONSISTENCY`, `POTENTIAL_MANIPULATION`.
   The case result is `risk_level` + `requires_human_review`.
2. **Bboxes are canonical page pixels**, top-left origin, on the page image written by ingest.
   PDFs render at `settings.render_dpi` (200): `px = pt * 200 / 72`. Images keep native pixels
   after EXIF orientation is applied. Bboxes come from word boxes, never from an LLM.
3. **OCR is not ground truth.** Every field keeps `confidence`, `page`, `bbox`, `source`.
4. **Every detector really runs on the input.** No mock results in production paths. If a detector
   can't run, the document or stage is `degraded` with a message saying so. Never fabricate.
5. **Config comes only from `config/settings.py`.** No `os.environ` elsewhere. Never log a key.
6. **Only synthetic data.** Fake people, fake IDs, every sample watermarked `SYNTHETIC`.
7. **Failures never crash the case.** Catch per document and per detector; record and continue.
8. **No external network calls** outside `llm/`. When `settings.offline` is true, `llm/` calls
   nothing except a local Ollama. PII is redacted before any external call.

## 2. Module interfaces (Python)

`workdir` is `settings.data_dir / "cases" / case_id`. All `uri`/`image_path` values are relative
to `settings.data_dir`.

```python
# pipeline/ingest.py      (Agent B)
def ingest_file(path: Path, case_id: str, workdir: Path, filename: str | None = None) -> Document
# Hashes, sniffs real type by magic bytes, renders pages to workdir/<doc_id>/page_<n>.png.
# Never raises for bad input: returns Document(status=unsupported|failed, status_message=...).

# pipeline/ocr.py         (Agent B)
def extract_words(doc: Document, workdir: Path) -> Document
# Fills page.words. Digital PDF: text layer via PyMuPDF. Otherwise RapidOCR, Tesseract fallback.
# Sets page.text_source, page.mean_ocr_confidence; status=degraded when confidence is low.

# pipeline/classify.py    (Agent B)
def classify(doc: Document) -> Document        # Sets doc_type, doc_type_confidence, method.

# pipeline/extract.py     (Agent B)
def extract_fields(doc: Document) -> Document  # Fills fields + tables by label-to-value layout.

# pipeline/structure.py   (Agent B)
def analyze_structure(doc: Document) -> Document  # sections, missing_fields, duplicated_fields.

# pipeline/forensics_visual.py (Agent B)
def analyze_visual(doc: Document, workdir: Path) -> list[Finding]
# ELA, noise residual, copy-move, font/stroke consistency, overwrite, photo/signature checks.
# Writes heatmaps to workdir/<doc_id>/overlays/<kind>_p<n>.png and crops to .../evidence/.

# pipeline/forensics_pdf.py (Agent B)
def analyze_pdf(doc: Document, source_path: Path, workdir: Path) -> list[Finding]
# Text layer vs rendered pixels, incremental updates, producer mismatch, overlays, metadata.
# Also EXIF for images. Returns [] with no error for formats it doesn't apply to.

# pipeline/signatures.py  (Agent B)
def analyze_signatures(docs: list[Document], workdir: Path, case_id: str) -> list[Finding]
# Case-level: the same signature pixels reused across documents (perceptual hash), and placement.

# pipeline/fusion.py      (Agent B)
def fuse_regions(findings: list[Finding], doc: Document) -> list[Finding]
# Merges overlapping visual/structural evidence into one scored region per area; sets fused_score.

# backend/contextual.py   (Agent C)
def verify_within_document(doc: Document) -> list[Finding]

# backend/crossdoc.py     (Agent C)
def build_entities(docs: list[Document], case_id: str) -> list[Entity]
def correlate(docs: list[Document], entities: list[Entity], case_id: str) -> list[Finding]
def build_graph(case_id: str, docs, entities, findings) -> EvidenceGraph

# llm/client.py           (Agent C)
class LLMClient:
    def complete_json(self, task: str, prompt: str, schema: type[BaseModel],
                      strength: Literal["fast", "strong"] = "fast") -> LLMResult
# Chain with retry, key rotation, disk cache, rate limit, counters. Never raises to callers:
# returns LLMResult(ok=False, mode="deterministic", ...) so callers use a deterministic path.

# llm/investigator.py     (Agent C)
def investigate(findings: list[Finding], docs: list[Document]) -> list[Finding]
# Adds explanation, benign_alternatives, recommended_verification, related_finding_ids.
# Sets finding.reasoning honestly. Every finding has useful deterministic text with no LLM.

# audit/chain.py          (Agent C)
def append(action, actor, case_id=None, payload=None) -> AuditEntry
def verify(case_id=None) -> AuditVerification

# backend/dossier.py      (Agent C)
def build_dossier(case_id) -> Dossier
def render_pdf(dossier: Dossier, out: Path) -> Path   # ReportLab

# backend/orchestrator.py (Agent C)
def run_case(case_id) -> None   # Runs all 10 stages, audits each, publishes progress.
```

Execution order in `run_case`: ingest → extract_words → classify → extract_fields →
analyze_structure → analyze_visual + analyze_pdf + analyze_signatures → fuse_regions →
verify_within_document → build_entities + correlate → investigate → build_graph →
build_dossier. Each stage appends an audit entry.

Agent C must code against these signatures before Agent B finishes. If a B module isn't importable
yet, the stage reports `degraded` rather than faking output.

## 3. REST API (all under `/api`, JSON unless noted)

| Method & path | Purpose |
|---|---|
| `GET /health` | `{status, version, offline, demo_cache}` |
| `GET /capabilities` | `{mode, providers:[{provider,key_present,status,model}], tools:[{name,available,detail}], matrix:[{capability,status,notes}], limitations:[str], llm_usage:{calls,tokens,by_provider}}`. `mode` is `offline`, `demo_cache`, `live` or `deterministic`. |
| `GET /demo-cases` | `[{key,name,description,documents}]` |
| `POST /demo-cases/{key}/load` | Creates a `Case` with that case's documents, not yet run. Returns `Case`. |
| `POST /cases` | Body `{name}`. Returns `Case`. |
| `GET /cases` | `[Case]` newest first |
| `GET /cases/{id}` | `{case: Case, documents: [DocumentSummary]}` |
| `POST /cases/{id}/documents` | Multipart `files[]`. Returns `[DocumentSummary]`. A bad file gives a document with `status=unsupported/failed`, not an HTTP 500. Oversize gives 413. |
| `POST /cases/{id}/run` | 202 `{case_id,status}`; background processing |
| `GET /cases/{id}/progress` | **SSE** stream. Event `progress`, data `{case_id,status,stages:[StageProgress]}`; event `done` at the end |
| `GET /cases/{id}/documents/{doc_id}` | Full `Document` (with words omitted unless `?words=true`) |
| `GET /cases/{id}/documents/{doc_id}/pages/{n}/image` | PNG |
| `GET /cases/{id}/documents/{doc_id}/pages/{n}/overlays` | `[{kind,label,url}]` |
| `GET /cases/{id}/documents/{doc_id}/pages/{n}/overlays/{kind}` | PNG (RGBA heatmap, same size as the page) |
| `GET /cases/{id}/findings` | `[Finding]`; optional `?status=&category=&doc_id=` |
| `POST /findings/{id}/review` | Body `{decision:"confirmed"\|"dismissed"\|"escalated", reviewer, note}`. Returns `Finding`, audited. |
| `GET /cases/{id}/fields` | `[Field & {doc_filename, doc_type}]` |
| `GET /cases/{id}/entities` | `[Entity]` |
| `GET /cases/{id}/graph` | `EvidenceGraph` |
| `GET /cases/{id}/dossier` | `Dossier` JSON |
| `GET /cases/{id}/dossier.pdf` | PDF download |
| `GET /cases/{id}/audit` | `[AuditEntry]` |
| `GET /cases/{id}/audit/verify` | `AuditVerification` for the whole chain |
| `POST /audit/tamper-demo` | Only if `settings.audit_tamper_demo`. Edits one stored entry's payload without rehashing and returns `{tampered_seq}`. |
| `POST /audit/tamper-demo/restore` | Restores it so the demo is repeatable. |
| `GET /files/{path}` | Evidence crops and heatmaps under `data_dir`; path traversal rejected |

`DocumentSummary` = `{id, filename, format, doc_type, doc_type_confidence, status, status_message,
page_count, field_count, finding_count}`. Errors use `{detail: str}`. CORS comes from
`settings.cors_list()`. The API runs at `http://localhost:8000`, the Vite dev server at `:5173`.

## 4. Canonical field names

| Doc type | Fields |
|---|---|
| all | `person_name`, `date_of_birth`, `address`, `document_date` where printed |
| `application_form` | `application_id`, `person_name`, `date_of_birth`, `gender`, `address`, `phone`, `email`, `id_number`, `pan_number`, `employer_name`, `designation`, `declared_monthly_income`, `loan_amount`, `bank_account_number`, `application_date` |
| `id_proof` | `id_type`, `id_number`, `pan_number`, `person_name`, `date_of_birth`, `gender`, `address` |
| `salary_slip` | `person_name`, `employee_id`, `employer_name`, `designation`, `pay_period`, `pan_number`, `bank_account_number`, `basic_pay`, `hra`, `other_allowances`, `gross_pay`, `total_deductions`, `net_pay`, `date_of_joining` |
| `bank_statement` | `person_name`, `address`, `bank_name`, `bank_account_number`, `ifsc`, `statement_period`, `opening_balance`, `closing_balance`. Table `transactions` with headers `date, description, debit, credit, balance` |
| `address_proof` | `person_name`, `address`, `issuer_name`, `consumer_number`, `bill_date`, `amount_due` |
| `declaration` | `person_name`, `date_of_birth`, `address`, `employer_name`, `declared_monthly_income`, `declaration_date`, `place` |

Normalization (`value_norm`): dates ISO `YYYY-MM-DD`; money plain decimal `85400.00`; names
casefolded with collapsed spaces; addresses uppercased with common abbreviations expanded; IDs
with no spaces.

## 5. Detector ids and discrepancy types

Visual and structural: `visual.ela`, `visual.noise`, `visual.copy_move`, `visual.font_consistency`,
`visual.overwrite`, `visual.photo_insert`, `visual.alignment`, `visual.signature_reuse`,
`visual.signature_placement`, `pdf.text_vs_pixels`, `pdf.incremental_update`,
`pdf.producer_mismatch`, `pdf.overlay_object`, `metadata.exif`, `metadata.pdf_dates`.

Within-document: `context.arithmetic_salary`, `context.arithmetic_balance`,
`context.date_order`, `context.id_checksum`, `context.missing_field`, `context.duplicate_field`.

Cross-document (`discrepancy_type` values; rubric wants 5+ distinct): `dob_mismatch`,
`name_variant`, `address_variant`, `employer_mismatch`, `salary_vs_bank_credit`,
`declared_vs_actual_income`, `id_number_mismatch`, `account_number_mismatch`,
`employment_date_conflict`.

Status guidance: a measured fact is `OBSERVATION`. Two values disagreeing is `INCONSISTENCY`.
`POTENTIAL_MANIPULATION` requires a forensic signal suggesting alteration, is a hypothesis, and
must list benign alternatives. Case risk: `high` if any fused `POTENTIAL_MANIPULATION` is ≥ 0.6
or there are 3+ `INCONSISTENCY` of medium severity or above; `medium` for any medium-or-above
`INCONSISTENCY` or weak manipulation signal; otherwise `low`. `undetermined` if no document
could be processed.

## 6. Demo dataset layout (Agent A owns; B, C and E consume)

```
data/synthetic_cases/
  manifest.json                     # [{key,name,description,documents:[filename,...]}]
  case_a_clean/   case_b_visual/   case_c_crossdoc/   case_d_pdf/
    <doc files>.png|.jpg|.pdf
    ground_truth.json
  noise_variants/<case>/<doc>__<rot|blur|jpeg>.<ext>  plus ground_truth.json
  unsupported/  sample.docx-like file, truncated.pdf (corrupt), empty.png
```

`ground_truth.json`:

```json
{
  "case": "case_b_visual",
  "applicant": {"person_name": "...", "date_of_birth": "YYYY-MM-DD"},
  "documents": [{"filename": "salary_slip.png", "doc_type": "salary_slip", "format": "png",
    "fields": {"net_pay": {"value": "85400.00", "page": 0, "bbox": [x0,y0,x1,y1]}}}],
  "manipulations": [{"id": "m1", "type": "overwrite", "filename": "salary_slip.png", "page": 0,
    "bbox": [x0,y0,x1,y1], "expected_detectors": ["visual.overwrite","visual.font_consistency"],
    "description": "..."}],
  "discrepancies": [{"id": "d1", "discrepancy_type": "dob_mismatch",
    "documents": ["application_form.png","id_proof.png"], "description": "..."}]
}
```

Bboxes use canonical pixels, the same as section 1 (A4 at 200 DPI is 1654 x 2339 px).

## 7. File ownership (parallel agents share one checkout)

| Agent | May write |
|---|---|
| A | `scripts/generate_dataset.py`, `data/synthetic_cases/**`, `docs/models_and_methods.md` |
| B | `pipeline/**`, `tests/pipeline/**` |
| C | `backend/**`, `llm/**`, `audit/**`, `scripts/check_keys.py`, `scripts/verify_audit_chain.py`, `tests/backend/**`, `tests/llm/**`, `tests/audit/**`, `data/llm_cache/**` |
| D | `frontend/**` |
| E | `tests/e2e/**`, `tests/conftest.py`, `scripts/run_benchmark.py`, `.github/**`, `README.md`, `THIRD_PARTY.md`, `LICENSE`, `Makefile`, `docker-compose.yml`, `Dockerfile*`, `.env.example`, remaining `docs/*` |
| Lead | `models/**`, `config/**`, `docs/CONTRACTS.md`, `requirements.txt` (others append to it and report) |

Commit only your own paths, often: `git add <your paths> && git commit -m "..."`, retrying if the
index is locked. Never `git add -A`, never rewrite history, never touch another agent's files. If
another agent's module has a bug, work around it and report it.
