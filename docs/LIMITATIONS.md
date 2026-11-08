# Limitations and Assumptions

Measured results are in [benchmark_results.md](benchmark_results.md) and [holdout_results.md](holdout_results.md).

## What this system is not

- **It does not decide whether a document is genuine.** It reports observations, inconsistencies and
  hypotheses for a human to review. A clean result does not mean a document is authentic.
- It does not verify anything against a real external source. Registry checks run only against a
  bundled synthetic test file, and every such finding says so.
- It is a hackathon prototype. Login is optional and has no per-user permissions. There is no data retention policy,
  and it has not been security audited. See `docs/SECURITY.md`.

## Assumptions

- Documents in a case belong to one applicant or transaction.
- Documents are English-language Indian financial and identity documents laid out like our synthetic
  samples. Field extraction relies on printed labels near values.
- All development and evaluation data is synthetic.

## Unsupported scenarios

| Scenario | Behaviour |
|---|---|
| Handwritten text | Partly supported. See "Handwriting" below. |
| Languages other than English and printed Hindi | Not supported. Hindi was tested on one synthetic salary slip, with common field labels only. |
| Who signed a document | Not supported. We tried comparing signature shapes, and same-person pairs (0.8 to 7.5) overlapped different-person pairs (3.4 and up), so offering it would mislead. Reuse of the same signature pixels is still detected. |
| Formats other than PNG, JPG and PDF (e.g. DOCX, HEIC, TIFF) | Reported as `unsupported`. |
| Password-protected PDFs | Not processed; reported with a message. |
| Documents above the page or size limits | Truncated or rejected with a message (`MAX_PAGES_PER_DOC`, `MAX_UPLOAD_MB`). |
| Video, audio | Out of scope. |

## Degraded scans: a known weakness

Measured on held-out seeds with rotation of 1 to 2 degrees, blur and heavy JPEG:

| | Original documents | Degraded scans |
|---|---|---|
| Manipulations localized | 30/30 | **18/45 (40.0%)** |
| Manipulation precision | 30/30 | 18/21 (85.7%) |
| Field value accuracy | 1160/1160 | 1175/1185 (99.2%) |

Blur and recompression erase the fine signals forensics relies on. Contextual and cross-document
checks depend on text, which survives much better, so they are the safer signal on poor scans. A
low-quality scan with no findings tells you little: **absence of findings is not evidence of
authenticity**, and least of all on a poor scan.

Signature reuse now survives blur and small rotations, which is most of the gain. Overwritten values and
pasted photos are still mostly missed on poor scans.

## Handwriting

Handwriting is spotted from the shape of the writing: on our test pages, none of 71 printed pages triggered
it, and all 10 handwriting-style pages did. Values are read by regular OCR, and a local vision model
(`granite3.2-vision`) fills rows OCR couldn't read.

- **Measured:** 61 of 80 values exact, against 59 of 80 for OCR alone. So about one value in four is wrong.
- **The test data isn't real handwriting.** It's a handwriting font, deliberately distorted.
- Letting the AI overwrite OCR made results worse (53 of 80), so it doesn't. When the two disagree, OCR's value
  stands and the reviewer sees both.
- Every value on a handwritten page is capped at low confidence and marked for checking.
- Without the vision model, nothing is invented: unread rows stay empty.

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

## Doc, the chat guide

- Doc recognises common questions by their wording, so an unusual phrasing can get a less useful answer or a polite "not sure".
- AI answers are checked for verdict language, flat yes or no replies and numbers that aren't in the results, but they can still be
  wrong or badly reasoned. They're labelled, and they should be read as a prompt to check.
- Doc doesn't remember conversations once the page reloads, and the conversation isn't saved in the History tab.

## New review tools

- **Seen before** only compares applications stored on this system, and only the details the checks read: phone, email,
  bank account, PAN, ID number, the applicant photo and signatures. Photo matching was tuned on synthetic placeholder
  portraits, where the repeated photo scored 0.995 to 1.000 and different portraits at most 0.863. Real photos, re-photographed
  prints and heavy compression haven't been tested. A repeated detail can be innocent (a family phone, a joint account), so a
  match under a different name is an inconsistency to check, never a verdict. Same-name matches are only observations.
- **Verify this report** proves a PDF is byte for byte one the system issued and recorded. A report re-saved or printed to PDF
  by another program shows as changed even if nothing visible changed. The JSON export isn't covered.
- **Verification letters** are drafts built from each finding's evidence. They aren't reviewed by a lawyer, and the reviewer
  sends them. Addresses aren't looked up: the letter names the issuer as printed on the document.
- **Doc in Hindi** translates his fixed answer patterns and finding titles exactly. The checks' own explanation text stays in
  English with a note, because machine translation with the local model produced wrong words and stray scripts. The Hindi
  hasn't been reviewed by a native speaker.
- **Redacted dossiers** black out personal values and their boxes wherever the checks located them, plus photos and
  signatures. Anything the checks didn't read, such as a name inside a transaction description, may remain. Check before sharing.
- **The false-alarm tracker** counts this system's own reviewer decisions. With few decisions it says little, and it isn't an
  accuracy measure.

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
| 3 | 9101 to 9105 | 30/30 manipulations, 0 false flags; 1160/1160 fields | Then added blur-tolerant signature matching |
| 4 | 9201 to 9205 | 30/30 manipulations, **1 false signature-reuse flag** | Two different signatures scored 0.944 after softening. Real degraded copies score 0.987 or more, so softened matches now need 0.97 |
| 5 (published) | 9301 to 9305 | 30/30 manipulations, 0 false flags; 1160/1160 fields | Published as is |

Rounds 2 and 4 show the kind of failure to expect in other data: a confident false flag caused by one OCR
error in a rare case. We fixed the one we found. Others are likely to exist.

## Deployment limits

- The `Dockerfile` was built and run locally on Apple Silicon (arm64), where a demo analysis, the PDF
  report and deep links worked, using about 420 MB of memory. It **hasn't been deployed to a host yet**,
  or built for amd64, which is what Hugging Face Spaces uses. See [DEPLOY.md](DEPLOY.md).
- On a hosted site, files don't persist across restarts on free tiers, and the local Ollama model isn't
  available. Live AI there needs a hosted provider key.
- `requirements.txt` sets minimum versions. `requirements.lock` records the exact versions tested.
- Developed on Apple Silicon macOS with Python 3.12. CI runs the tests on Linux on GitHub, and passed on its first run;
  other operating systems haven't been tried.
- The UI was checked on desktop, tablet and phone sizes, in light and dark mode. On phones, wide report tables scroll sideways.
- **PyMuPDF is AGPL-3.0.** See `THIRD_PARTY.md` before distributing or hosting a combined application.
