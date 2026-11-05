# Deck Outline (12 slides)

Screenshots are in `docs/screenshots/`, the diagram is `docs/diagram.png`, and the dossier is `docs/sample_dossier.pdf`.

1. **Title.** DocuForensic AI. "OCR reads a document. This examines whether to believe it." Team Hackthecore.
2. **The problem.** A salary slip passes OCR and field validation, yet its net pay was altered. Extraction doesn't establish authenticity, consistency or reliability.
3. **The gap in OCR-only systems.** What they miss: visual edits, conflicts visible only across documents, PDFs whose text differs from their pixels. What they lack: evidence and traceability.
4. **Our solution and flow.** The 10 stages. Every finding is an evidence object: status, document, page, region, evidence, benign explanations, verification steps. (`10_pipeline.png`)
5. **Architecture.** `diagram.png`. Point: forensics and correlation run locally with no keys; AI is optional and bounded.
6. **Forensic fusion.** Weak signals must corroborate. Show the net pay example: typography, background patch and ELA agree on one box, with the fused score. (`01_viewer_overwrite.png`). Add PDF text vs pixels. (`04_pdf_text_vs_pixels.png`)
7. **Cross-document intelligence.** 9 discrepancy types, side by side and in the evidence graph. (`02_conflicts.png`, `03_evidence_graph.png`)
8. **Explainability, and its limits.** Benign alternatives, confirm or refute. The LLM can't create or change findings, and each explanation shows its source. A second OCR engine settles ambiguous digits.
9. **Sample dossier and traceability.** Sections 7.1 to 7.6, and any finding traced back to its source. (`07_dossier.png`, a page from the PDF)
10. **Benchmark.** The README table, including the degraded column. State plainly: synthetic only, same templates, no real documents. Mention that held-out testing caught a real false flag, which we fixed.
11. **Ethics and human oversight.** Three statuses, no verdicts. Human decisions logged in a tamper-evident chain. Synthetic data only. Offline mode, PII redaction. Standards as guidance, without claiming compliance. AI-assisted development disclosed.
12. **Rubric coverage, limitations, roadmap.** Rubric table in brief. Limitations: degraded scans, real documents untested, handwriting and multilingual unsupported, hosted LLMs unverified. Roadmap: evaluation on authorized real samples, robustness on poor scans, handwriting, template-free extraction, signature analysis.

**Speaker notes to prepare.** Every member should be able to answer: why fusion rather than one detector? Why can't an LLM set the status? What causes false positives? How does ELA work, and when does it fail? What does the hash chain prove, and what doesn't it prove? Which parts were AI-assisted?
