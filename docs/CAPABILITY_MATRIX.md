# Capability Matrix

**Status** is what the code is meant to do. **Verified** says whether we've seen it work.

> **Draft.** Most rows say "Not yet" because modules were still landing when this was written. Each
> row is updated only after a real run. Target status means the row is being built, and isn't a claim.

## Mandatory capabilities

| Capability | Requirement | Target status | Verified |
|---|---|---|---|
| Ingest PNG, JPG, scanned PDF, digital PDF | 5.1 | Implemented | Not yet end to end |
| Multiple documents per investigation | 5.1 | Implemented | Not yet |
| Document classification | 5.1 | Implemented | Not yet |
| Printed OCR with confidence and location | 5.2 | Implemented | Engines smoke-tested only |
| Structured field and table extraction | 5.2 | Implemented | Not yet |
| Layout, sections, missing and duplicated fields | 5.3 | Implemented | Not yet |
| Suspicious regions and visual inconsistencies | 5.4 | Implemented | Not yet |
| Signature reuse and placement analysis | 5.4 | Partial (reuse and placement only, not handwriting verification) | Not yet |
| Inconsistencies within a document | 5.5 | Implemented | Not yet |
| Cross-document correlation, 5+ discrepancy types | 5.6 | Implemented | Not yet |
| Evidence mapping to document, page and region | 5.7 | Implemented | Not yet |
| Investigation dossier, sections 7.1 to 7.6, PDF + JSON | 5.8 | Implemented | Not yet |
| Hash-chained audit trail | 5.9 | Implemented | Not yet through the API |
| Reviewer interface: Confirm, Dismiss, Escalate | Mandatory | Implemented | Not yet |
| Safe failure handling | Checklist | Implemented | Tests written; not yet run against the API |

## Advanced capabilities

| Capability | Status | Verified / notes |
|---|---|---|
| PDF structural forensics (text vs pixels, incremental updates, overlays) | Implemented (target) | Not yet |
| Region fusion across detectors | Implemented (target) | Not yet |
| Evidence graph | Implemented (target) | Not yet |
| LLM investigator with counter-hypotheses | Implemented (target) | Not yet |
| Local LLM through Ollama | Implemented (target) | Not yet |
| Hosted LLMs: Gemini, Groq, OpenRouter | Partial | Client tested against a fake network only. **No real call made**: no keys available. |
| Provider fallback, key rotation, retry | Implemented | Failure paths tested against a fake network |
| PII redaction before external calls | Partial | Works on the wire; known bug with trailing punctuation, see `docs/SECURITY.md` |
| Offline mode | Implemented | Client-level test: no external call is made |
| Investigation analytics | Planned | Not started |
| Handwritten text recognition | **Unsupported** | Not being built |
| Multilingual documents | **Unsupported** | Not being built |
| Signature identity verification | **Unsupported** | Not attempted |
| Verification against external registries | **Unsupported** | Not attempted |
| Authentication, multi-user | **Unsupported** | Out of scope for this prototype |
| Docker deployment | Partial | Files written, **never run** (Docker daemon was off) |
