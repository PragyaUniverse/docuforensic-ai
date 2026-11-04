# Architecture

> **Draft.** This describes the design in `docs/CONTRACTS.md`. It was written while modules were still
> landing, so see `docs/CAPABILITY_MATRIX.md` for what has been verified. `diagram.png` is rendered
> from the Mermaid below once the design is final.

## Overview

DocuForensic AI treats every finding as a first-class evidence object tied to a document, page and
region. Forensic detection and cross-document correlation are deterministic and run locally. An
LLM is optional: it only writes explanations, and it can't create, remove or re-grade a finding.

```mermaid
flowchart TB
    subgraph IN["Submission"]
        UI["React reviewer UI"] -->|"multipart upload, SSE progress"| API["FastAPI: limits, type checks, rate limit"]
    end

    subgraph DOC["Document processing (local)"]
        ING["Ingest: SHA-256, magic-byte sniffing, 200 DPI page render"]
        OCR["OCR: PyMuPDF text layer, RapidOCR (PP-OCR models), Tesseract fallback"]
        CLS["Classification"]
        EXT["Field and table extraction: label-to-value layout, word boxes as bboxes"]
        STR["Structure: sections, missing and duplicated fields"]
        ING --> OCR --> CLS --> EXT --> STR
    end

    subgraph CV["Computer vision and PDF forensics (local)"]
        VIS["Pixel: ELA, noise residual, copy-move, font and stroke, overwrite, photo insert"]
        PDF["PDF structure: text layer vs pixels, incremental updates, producer, overlays, metadata"]
        SIG["Signature reuse by perceptual hash, placement"]
        FUS["Region fusion: one score per area"]
        VIS --> FUS
        PDF --> FUS
        SIG --> FUS
    end

    subgraph CTX["Contextual analysis (local)"]
        WITHIN["Within-document: arithmetic, date order, ID checksum"]
        ENT["Entity matching: rapidfuzz, normalization"]
        CROSS["Cross-document correlation: discrepancy types, salary vs bank credits"]
        ENT --> CROSS
    end

    subgraph AI["AI reasoning (optional, swappable)"]
        INV["Investigator: explanations, benign alternatives, verification steps"]
        RED["PII redaction before external calls"]
        CHAIN["Provider chain: Gemini, Groq, OpenRouter, Ollama, then deterministic"]
        CACHE[("Answer cache by input hash")]
        INV --> RED --> CHAIN
        INV <--> CACHE
    end

    subgraph EV["Evidence management"]
        STORE[("SQLite + evidence files: pages, heatmaps, crops")]
        GRAPH["Evidence graph: conflicts as red edges"]
        AUD[("Hash-chained audit trail")]
        DOS["Dossier: JSON + PDF, sections 7.1 to 7.6"]
    end

    REV["Human review: Confirm, Dismiss, Escalate"]

    API --> ING
    STR --> VIS
    STR --> PDF
    STR --> SIG
    STR --> WITHIN
    STR --> ENT
    FUS --> INV
    WITHIN --> INV
    CROSS --> INV
    INV --> STORE
    STORE --> GRAPH
    STORE --> DOS
    GRAPH --> UI
    DOS --> UI
    STORE --> UI
    UI --> REV
    REV --> AUD
    DOC -. "every stage logged" .-> AUD
    CV -.-> AUD
    CTX -.-> AUD
    AI -. "provider that answered" .-> AUD
```

## Data flow

1. **Submission.** Files are hashed and stored. Type comes from magic bytes, not the extension. A bad
   file becomes a document with an `unsupported` or `failed` status and a message, and never stops
   the case.
2. **Classification, OCR and extraction.** All bboxes are canonical page pixels and come from word
   boxes, never from an LLM. Every field keeps its confidence and source. OCR is never ground truth.
3. **Structure.** Fields are grouped into sections, and missing or duplicated fields are recorded.
4. **Visual forensics.** Detectors run on the page images and PDF internals. Overlapping signals are
   fused into a single scored region.
5. **Contextual verification and correlation.** Field relationships are checked within each document,
   then entities are matched and compared across documents.
6. **Investigation.** Each finding gets an explanation, benign alternatives and verification steps,
   from the LLM when one is available and from deterministic text otherwise. Each finding records
   which of the two produced its text.
7. **Evidence and dossier.** Findings link to their regions, the evidence graph links documents,
   entities and findings, and the dossier follows the required sections.
8. **Human review.** A reviewer decides on each finding. The system itself reports a risk level and
   "requires human review", never a verdict.

## Design decisions

| Decision | Reason |
|---|---|
| Three finding statuses, no verdict | The problem statement requires separating observations, inconsistencies and potential manipulation. |
| The LLM can't alter statuses, severities, confidences or regions | Document text is untrusted and reaches the LLM. See `docs/SECURITY.md`. |
| Detection doesn't depend on any API | The demo and the core product must work with zero keys and no quota. |
| RapidOCR rather than PaddleOCR itself | The same PP-OCR models through ONNX Runtime, without the Paddle framework. See `docs/ENVIRONMENT.md`. |
| ReportLab for the dossier | No system libraries needed, which keeps a clean-clone setup simple. |
| Hash-chained audit log | Tampering with a stored entry is detectable. Aligned with the principles of ISO/IEC 27037 and NIST SP 800-86, with no claim of formal compliance. |
| Canonical pixel coordinates everywhere | One coordinate system links findings, fields, overlays and ground truth. |
