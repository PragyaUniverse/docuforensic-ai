# Architecture

![Architecture](diagram.png)

## Overview

DocuForensic AI treats every finding as a first-class evidence object tied to a document, page and
region. Forensic detection and cross-document correlation are deterministic and run locally. An
LLM is optional: it only writes explanations, and it can't create, remove or re-grade a finding.

```mermaid
flowchart LR
    U(["Examiner<br/>React reviewer UI"]) -->|"upload, live SSE progress"| API["FastAPI<br/>size, type and rate limits"]
    API --> ING

    subgraph P1["1. Document processing"]
        direction TB
        ING["Ingest<br/>SHA-256, magic bytes, 200 DPI render"] --> OCR["OCR<br/>PDF text layer, RapidOCR (PP-OCR), Tesseract"]
        OCR --> CLS["Classification and field and table extraction<br/>bboxes always come from word boxes"]
        CLS --> STR["Structure<br/>sections, missing and duplicated fields"]
    end

    subgraph P2["2. Forensics: computer vision and PDF"]
        direction TB
        VIS["Pixels<br/>ELA, noise, copy-move, typography,<br/>overwrite, photo insert"]
        PDF["PDF structure<br/>text layer vs pixels, revisions, overlays, metadata"]
        SIG["Signatures<br/>reuse across documents, placement"]
        FUS["Region fusion<br/>one explainable score per area"]
        VIS --> FUS
        PDF --> FUS
        SIG --> FUS
    end

    subgraph P3["3. Contextual analysis"]
        direction TB
        WIT["Within a document<br/>arithmetic, figures vs words, dates, ID checks"]
        ENT["Entity matching<br/>rapidfuzz, normalization"] --> CRO["Cross-document correlation<br/>9 discrepancy types, salary vs bank"]
    end

    subgraph P4["4. AI reasoning: optional, can't change findings"]
        direction TB
        INV["Investigator<br/>explanations, benign alternatives, verification"] --> RED["PII redaction"]
        RED --> CHN["Provider chain<br/>Gemini, Groq, OpenRouter, Ollama, deterministic"]
    end

    subgraph P5["5. Evidence management"]
        direction TB
        DB[("SQLite and evidence files<br/>pages, heatmaps, crops")]
        GRA["Evidence graph<br/>conflicts as red edges"]
        DOS["Dossier<br/>PDF and JSON, sections 7.1 to 7.6"]
        AUD[("Hash-chained audit trail<br/>every stage and decision")]
    end

    STR --> VIS
    STR --> PDF
    STR --> SIG
    STR --> WIT
    STR --> ENT
    FUS --> INV
    WIT --> INV
    CRO --> INV
    INV --> DB
    DB --> GRA
    DB --> DOS
    DB --> AUD
    GRA --> R(["Human review<br/>Confirm, Dismiss, Escalate"])
    DOS --> R
    R -->|"logged"| AUD
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
