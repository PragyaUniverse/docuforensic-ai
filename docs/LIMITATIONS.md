# Limitations and Assumptions

> **Draft.** Measured false-positive numbers are added from `docs/benchmark_results.md` once the
> benchmark has run. The expected behaviours below are engineering expectations, not measurements.

## What this system is not

- **It does not decide whether a document is genuine.** It reports observations, inconsistencies and
  hypotheses for a human to review. A clean result does not mean a document is authentic.
- It does not verify anything against an external source: no issuer, bank, employer or government
  database is contacted.
- It is a hackathon prototype. It has no authentication, multi-user support or data retention policy,
  and it has not been security audited. See `docs/SECURITY.md`.

## Assumptions

- Documents in a case belong to one applicant or transaction.
- Documents are English-language Indian financial and identity documents laid out like our synthetic
  samples. Field extraction relies on printed labels near values.
- All development and evaluation data is synthetic.

## Unsupported scenarios

| Scenario | Behaviour |
|---|---|
| Handwritten text | Not supported. No handwriting recognition model is integrated; handwritten fields will be missed or misread. |
| Languages other than English | Not supported. |
| Formats other than PNG, JPG and PDF (e.g. DOCX, HEIC, TIFF) | Reported as `unsupported`. |
| Password-protected PDFs | Not processed; reported with a message. |
| Documents above the page or size limits | Truncated or rejected with a message (`MAX_PAGES_PER_DOC`, `MAX_UPLOAD_MB`). |
| Video, audio | Out of scope. |

## Forensic limits and expected false positives

| Detector family | Expected false positives | Expected misses |
|---|---|---|
| ELA | Recompressed or multi-generation JPEGs, text edges and logos, screenshots | PNG or losslessly edited images; heavily recompressed tampering |
| Noise residual | Scanner bands, mixed content, stamps | Edits matched to the surrounding noise |
| Copy-move | Repeated logos, watermarks, table rules, repeated characters | Heavily transformed copies |
| Font and stroke consistency | Legitimate bold or multi-font templates, low-resolution scans | An edit in the same font at the same size |
| Overwrite | Highlighter, stamps, form-field shading, fold marks | Clean digital edits on a uniform background |
| Signature reuse | One person's stamped e-signature used legitimately | Re-signed or re-drawn signatures. This is not handwriting verification. |
| PDF text vs pixels | OCR errors on low-quality renders, unusual fonts | Edits applied consistently to text and image |
| PDF structure and metadata | Normal re-saves, e-signing, PDF/A conversion, and producer changes from legitimate tools | Files flattened or re-printed to PDF, which removes this evidence |
| EXIF | Normal editing software and messaging apps, which strip or rewrite EXIF | Absent or forged metadata |

## Contextual limits

- Extraction errors can create false discrepancies. An OCR misread looks like a conflict, which is why
  every field keeps its confidence and location for checking.
- Name and address variants are matched by fuzzy thresholds. Legitimate differences such as initials,
  a move or a marriage can flag, and a similar-looking change can pass.
- Salary-to-bank reconciliation assumes credits are identifiable from statement descriptions.
- ID checksums validate format only, and say nothing about whether an ID exists or belongs to anyone.

## AI reasoning limits

- LLM explanations may be wrong even when plausible, so they are labelled by source. They can't change
  a finding's status, severity, confidence or location.
- With no keys, and no local model, explanations come from deterministic templates and say so.
- As of this draft, **hosted providers (Gemini, Groq, OpenRouter) have only been tested against a fake
  network**, because no API keys were available. Their real behaviour is unverified.

## Evaluation limits

- The benchmark uses a small synthetic set made by this project, and thresholds were tuned on that
  same data. Its numbers are not generalization estimates. There is no held-out set and no real-world
  evaluation.
- Our injected manipulations reflect what we thought of, so detectors may look better on them than on
  manipulations from anyone else.

## Deployment limits

- `docker-compose.yml` and the Dockerfiles **have not been run**, because the Docker daemon wasn't
  running during this review. The documented path is the local setup in the README.
- Python dependencies have minimum versions, not pins, so a future install may behave differently.
- **PyMuPDF is AGPL-3.0.** See `THIRD_PARTY.md` before distributing or hosting a combined application.
