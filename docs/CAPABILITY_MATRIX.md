# Capability Matrix

**Status** is what exists. **How it was verified** says what we actually saw. All verification used
synthetic data, and nothing here has been tested on real documents.

## Mandatory capabilities

| Capability | Requirement | Status | How it was verified |
|---|---|---|---|
| Ingest PNG, JPG, scanned PDF, digital PDF | 5.1 | Implemented | All four formats through the REST API |
| Multiple documents per investigation | 5.1 | Implemented | Six-document cases through the API and UI |
| Document classification | 5.1 | Implemented | 24/24 demo, 120/120 held-out |
| Printed OCR with confidence and location | 5.2 | Implemented | Fields 232/232 located on the demo set |
| Structured field and table extraction | 5.2 | Implemented | Fields 1160/1160, rows 540/540 held-out. Layout must resemble our templates |
| Layout, sections, missing and duplicated fields | 5.3 | Implemented | Unit tests, dossier output |
| Suspicious regions and visual inconsistencies | 5.4 | Implemented | Manipulations 30/30 held-out. **40% on degraded scans** |
| Signature reuse and placement analysis | 5.4 | Partial | Pixel reuse and placement only. Doesn't identify who signed |
| Inconsistencies within a document | 5.5 | Implemented | 30/30 held-out |
| Cross-document correlation, 5+ discrepancy types | 5.6 | Implemented | 9 types, 65/65 held-out |
| Evidence mapping to document, page and region | 5.7 | Implemented | Automated test walks every finding on 4 cases, and UI click-through was checked |
| Investigation dossier, sections 7.1 to 7.6, PDF + JSON | 5.8 | Implemented | Generated and visually reviewed |
| Hash-chained audit trail | 5.9 | Implemented | Tamper detected at the exact entry, and restored, through the API and UI |
| Reviewer interface: Confirm, Dismiss, Escalate | Mandatory | Implemented | Unit and API tests; viewed in the UI |
| Safe failure handling | Checklist | Implemented | Corrupt, empty, mislabelled and unsupported files through the API |

## Advanced capabilities

| Capability | Status | How it was verified |
|---|---|---|
| PDF structural forensics (text vs pixels, incremental updates, overlays) | Implemented | Case D, in the API and UI |
| Region fusion across detectors | Implemented | Unit tests; 3 and 4 signal agreements seen on demo cases |
| Evidence graph | Implemented | UI check, Case C |
| LLM investigator with counter-hypotheses | Implemented | Live on a local model: 28 calls, 0 errors |
| Local LLM through Ollama | Implemented | `qwen2.5:7b`, run live |
| Replay of recorded answers | Implemented | All cases with no keys, no network and no Ollama: 28 replayed, 0 live calls |
| Offline mode | Implemented | Same run as above |
| Provider fallback, key rotation, retry | Implemented | Simulated network tests |
| PII redaction before external calls | Implemented | Unit tests. Not exercised against a real provider |
| Hosted LLMs: Gemini, Groq, OpenRouter | Partial | **No real call made**, as no keys were available. Simulated network only |
| Degraded scans | Partial | Measured: 40% manipulation recall, 85.7% precision |
| Docker deployment | Partial | Files written, **never run**: Docker isn't installed on the build machine |
| CI | Partial | Workflow written, **not yet run**. Its lint and test steps pass locally |
| Tablet and phone layouts | Implemented | Checked for overflow at tablet and phone sizes. Wide report tables scroll on phones |
| Investigation analytics | Implemented | Counts by finding type, check and reviewer decision, checked in the browser |
| Light and dark mode | Implemented | Toggle checked in the browser; the choice persists |
| Login | Implemented | Optional, off by default. Tested through the API only, not clicked through in a browser. All users share the same cases |
| Registry checks | Partial | Runs against a **bundled synthetic test registry** only. Live sources need authorized access |
| Handwriting | Partial | 61/80 exact on distorted handwriting-style text, **never tested on real handwriting**. Needs the optional vision model to fill unread rows |
| Hindi and English documents | Partial | Printed Hindi, common labels, one synthetic test document. Other languages unsupported |
| Signature identity (who signed) | **Unsupported** | Tried and dropped: shape comparison couldn't separate same-person from different-person pairs |
| Live government or bank registries | **Unsupported** | Needs authorized access |
| Per-user permissions | **Unsupported** | Out of scope for this prototype |
