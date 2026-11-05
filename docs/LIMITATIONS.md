# Limitations and Assumptions

Measured results are in [benchmark_results.md](benchmark_results.md) and [holdout_results.md](holdout_results.md).

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

## Degraded scans: a known weakness

Measured on held-out seeds with rotation of 1 to 2 degrees, blur and heavy JPEG:

| | Original documents | Degraded scans |
|---|---|---|
| Manipulations localized | 30/30 | **11/45 (24.4%)** |
| Manipulation precision | 30/30 | 11/13 (84.6%) |
| Field value accuracy | 1160/1160 | 1178/1185 (99.4%) |

Blur and recompression erase the fine signals forensics relies on. Contextual and cross-document
checks depend on text, which survives much better, so they are the safer signal on poor scans. A
low-quality scan with no findings tells you little: **absence of findings is not evidence of
authenticity**, and least of all on a poor scan.

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
- The small local model used for testing (`qwen2.5:7b`) writes uneven prose, and has listed tampering
  itself as an "innocent explanation". Those items are filtered out, but other weak reasoning can
  remain. Treat AI text as a prompt for review.
- **Hosted providers (Gemini, Groq, OpenRouter) have only been tested against a simulated network**,
  because no API keys were available. Their real behaviour is unverified. Their free-tier model names
  and limits come from provider docs, and change often.
- Replayed answers apply only to identical evidence. A changed document gets a fresh answer or
  deterministic text, never a stale answer.

## Evaluation limits

- **No real documents have ever been processed.** All data is synthetic and generated by this project,
  and the injected manipulations reflect what we thought of. Results on anyone else's documents or
  edits are unknown, and likely to be worse.
- Detector thresholds were tuned on the demo set, so its perfect scores say little.
- Held-out seeds keep the same templates, applicants and tamper types. They test stability against new
  randomness, not generalization.
- Results are sensitive to OCR. On held-out data, single misreads caused every defect listed below.

### What held-out evaluation found

Each round used new seeds, which were discarded once examined. The published table is the last round.

| Round | Seeds | Result on original documents | What we did |
|---|---|---|---|
| Development | 7001 to 7003 | 17/18 manipulations; 1 false flag on a clean case | Fixed signature copies missed when crop bounds differed, and a dropped digit passing as a valid amount |
| 1 | 8001 to 8005 | 30/30 manipulations, 0 false flags; 1159/1160 fields | Examined, moved on |
| 2 | 9001 to 9005 | 30/30 manipulations, **2 false `POTENTIAL_MANIPULATION` and 2 false `INCONSISTENCY` flags** | An OCR line flipped upside down looked like a text-layer mismatch. Turned off per-line rotation, and now require a second engine to disagree too |
| 3 (published) | 9101 to 9105 | 30/30 manipulations, 0 false flags; 1160/1160 fields | Published as is |

Round 2 shows the kind of failure to expect in other data: a confident false flag caused by one OCR
error in a rare case. We fixed the one we found. Others are likely to exist.

## Deployment limits

- `docker-compose.yml` and the Dockerfiles **have not been run**, because the Docker daemon wasn't
  running. The documented path is the local setup in the README, which was tested from a clean clone.
- `requirements.txt` sets minimum versions. `requirements.lock` records the exact versions tested.
- Tested on Apple Silicon macOS with Python 3.12 only. CI for Linux is configured but hasn't run yet,
  because the repository isn't on GitHub yet.
- The UI was checked on desktop, and on tablet for the main screens. It wasn't designed for phones.
- **PyMuPDF is AGPL-3.0.** See `THIRD_PARTY.md` before distributing or hosting a combined application.
