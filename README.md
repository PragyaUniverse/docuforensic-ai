# DocuForensic AI

> **Status: under active development for the DataOps Innovation Hackathon 2026 (Team Hackthecore).**
> Sections marked TODO are filled in only from real runs.

**OCR reads a forged salary slip perfectly. DocuForensic AI is built to question it.** It is an
evidence-driven document investigation engine: it examines scanned and digital documents for signs of
alteration, correlates information across the documents in an application, and produces a traceable
dossier in which every finding links back to a region of an original document. It reports
observations, inconsistencies and hypotheses for a human reviewer, and never a verdict. Detection runs
locally, with no API keys required.

## Screenshots

TODO: screenshots or a GIF from the running application.

## Quick start

TODO: confirm these commands from a clean clone before submission. Not yet tested.

```bash
git clone <repo-url> && cd <repo>
```

```bash
make setup
```

```bash
make api
```

```bash
make ui
```

Then open http://localhost:5173 and click **Load demo case**.

Requires Python 3.12, Node 20 and Tesseract (`brew install tesseract`, or
`apt-get install tesseract-ocr`). API keys are optional. To use them, copy `.env.example` to `.env`
and run `make keys`.

## Architecture

TODO: embed `docs/diagram.png` once rendered. The Mermaid source and design notes are in
[docs/architecture.md](docs/architecture.md).

## Features against the rubric

TODO: complete from verified behaviour. See [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md).

| Criterion | Points | Approach | Verified |
|---|---|---|---|
| OCR & Extraction | 15 | Text layer, RapidOCR (PP-OCR models), Tesseract; field-level confidence and location | TODO |
| Document Understanding | 15 | Classification, sections, missing and duplicated fields | TODO |
| Visual Forensics | 15 | Pixel and PDF-structure detectors fused per region | TODO |
| Contextual Intelligence | 20 | Entity matching, arithmetic reconciliation, cross-document discrepancy types | TODO |
| Evidence & Traceability | 10 | Finding to document, page and region, both ways; hash-chained audit | TODO |
| AI Reasoning & Explainability | 10 | Benign alternatives and verification steps, with the source of each explanation labelled | TODO |
| Technical Implementation | 10 | Typed contracts, tests, CI, safe failure handling | TODO |
| Innovation | 5 | Text layer vs pixels checks, evidence graph, counter-hypotheses, tamper-evident audit | TODO |

## Benchmark

TODO: results from `make benchmark`, published in
[docs/benchmark_results.md](docs/benchmark_results.md) with the full false-positive list. The demo set
is synthetic and thresholds were tuned on it, so the numbers won't be generalization estimates.

## Capability matrix

See [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md). Handwriting recognition and multilingual
documents are not supported.

## Ethics and safety

- **Synthetic data only.** All samples use fictional people and fake IDs and are watermarked SYNTHETIC.
- **No verdicts.** The system never labels anything as fraud. Each finding is an `OBSERVATION`, an
  `INCONSISTENCY` or a `POTENTIAL_MANIPULATION`. The overall result is a risk level and "requires human
  review".
- **Human oversight.** Reviewers confirm, dismiss or escalate each finding, and each decision is logged.
- **OCR is not ground truth.** Every value keeps its confidence and its source location.
- **Privacy.** An offline mode makes no external calls, and personal data is redacted before any
  external LLM call.
- **Honest modes.** Each explanation records whether it came from a live LLM, a replayed cache of real
  runs, or deterministic text.
- **Standards.** Aligned with the principles of ISO/IEC 27037, 27041 and 27042 and NIST SP 800-86. No
  claim of formal compliance.

See [docs/SECURITY.md](docs/SECURITY.md).

## AI-assisted development

Significant parts of this project's code, tests and documentation were written with an AI coding
assistant (Claude Code, Anthropic), directed and reviewed by the team. The application itself can also
use LLMs for investigation explanations. See [THIRD_PARTY.md](THIRD_PARTY.md).

## Limitations

See [docs/LIMITATIONS.md](docs/LIMITATIONS.md), including expected false positives and unsupported
scenarios.

## Third-party components and license

This project's own code is under the [MIT License](LICENSE). Third-party components, models and their
licenses are listed in [THIRD_PARTY.md](THIRD_PARTY.md). **PyMuPDF is AGPL-3.0**; please read the note
there before distributing or hosting the combined application.

## More documentation

[Contracts and API](docs/CONTRACTS.md) · [Models and methods](docs/models_and_methods.md) ·
[Traceability demo](docs/TRACEABILITY_DEMO.md) · [Environment](docs/ENVIRONMENT.md) · API docs at
`http://localhost:8000/docs` when running · Docker: `docker compose up --build` (not yet tested)
