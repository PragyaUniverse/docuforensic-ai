# Problem Statement Digest (DataOps Innovation Hackathon, PS-2)

**AI-Powered Document Forensics and Contextual Intelligence System.** Our digest of the official
PDF, kept so every requirement can be traced to implementation.

## Required flow

Document Submission → Document Classification → OCR & Information Extraction → Structural
Understanding → Visual Forensic Analysis → Contextual Verification → Cross-Document Correlation →
Anomaly Investigation → Evidence Generation → Investigation Dossier.

The system must display processing progress, extracted information, anomalies, confidence levels
and supporting evidence, and must clearly distinguish observed visual characteristics, detected
inconsistencies and potential manipulation.

## Functional requirements

- **5.1 Ingestion and classification:** scanned, image and digital documents; multiple documents
  per investigation; document types and structures; identifiers and source references.
- **5.2 OCR and extraction:** printed (and handwritten where applicable); fields, sections, tables;
  structured output; field-level confidence and references to the original location.
- **5.3 Structure:** relationships between fields and sections; layouts and hierarchies; missing,
  duplicated or misplaced information; preserved link to the original location.
- **5.4 Visual forensics:** alterations and overwritten fields; font, spacing, alignment and
  structure inconsistencies; image insertions and replacements; signature analysis and placement;
  highlighted regions.
- **5.5 Contextual verification:** inconsistencies between fields; comparison across documents;
  conflicting, mismatched, missing, duplicated or contextually inconsistent information.
- **5.6 Cross-document correlation:** relationships across one application; discrepancies visible
  only when documents are analysed together; traceability.
- **5.7 Evidence mapping:** each anomaly tied to its document; highlighted regions; visual and
  textual evidence; why it needs investigation; confirmed observations vs potential anomalies.
- **5.8 Dossier** and **5.9 Audit trail:** submissions, processing, anomalies with evidence,
  history, traceability from originals to extracted data to findings.

## Mandatory prototype

Ingestion and OCR extraction; structured extraction from multiple documents; suspicious regions and
visual inconsistencies; inconsistencies within and across documents; evidence mapping to original
locations; structured dossier; interface for reviewing extracted information and findings.

Bonus: advanced classification and layout; handwriting and multilingual; advanced image forensics
and localization; intelligent relationship discovery; advanced reasoning and anomaly correlation;
automated summaries and interactive evidence exploration; history, analytics and advanced audit
workflows. Capabilities must be documented as implemented, partial, planned or unsupported.
"A recorded demonstration alone is not sufficient to establish that a particular capability is
functional."

## Dossier sections (required)

- **7.1 Document Overview:** identification, type, source, processing status.
- **7.2 Extracted Information:** fields and values, field-level confidence, structure, references.
- **7.3 Contextual Analysis:** field-level inconsistencies, missing or duplicated information,
  conflicts across documents, cross-document discrepancies.
- **7.4 Visual Forensic Findings:** suspicious regions, potential alterations, font, alignment and
  structural inconsistencies, image manipulation and signature observations.
- **7.5 Evidence and Traceability:** original references, highlighted regions, visual evidence,
  associated extracted information, confidence and observation status.
- **7.6 Investigation Summary:** anomalies, evidence, potential explanations, areas requiring
  verification, investigation limitations.

## Required deliverables

Working prototype; architecture diagram (OCR, document processing, AI models, CV, contextual
analysis, data flow, evidence management); sample dossier; source repository (setup, dependencies,
licensing assumptions, execution); demonstration dataset (genuine and manipulated); technical
documentation; evidence traceability demonstration; limitations and assumptions (including
unsupported scenarios and potential false positives).

## Judges' live checklist

1. Upload multiple documents, show ingestion.
2. Classification and OCR extraction.
3. Conversion to a structured representation.
4. Identification and highlighting of suspicious regions.
5. Inconsistencies within individual documents.
6. Cross-document comparison and conflicts.
7. Relationships between different findings.
8. Evidence supporting anomalies.
9. Final dossier generation.
10. Trace findings back to original locations.
11. Potential anomalies vs confirmed observations.
12. Safe failure handling and honest statement of unsupported capabilities.

## Rubric (100)

OCR & Extraction 15 · Document Understanding 15 · Visual Forensics 15 · **Contextual Intelligence
20** · Evidence & Traceability 10 · AI Reasoning & Explainability 10 · Technical Implementation 10
· Innovation 5.

## Rules that constrain the build

Only authorized data; no real customer information; OCR is not ground truth; never auto-label an
anomaly as confirmed fraud; human oversight on consequential decisions; state limitations
honestly; no misrepresenting capabilities or fabricated demos; AI-assisted work disclosed and
explainable by the team; acknowledge all third-party resources; reference ISO/IEC 27037, 27041,
27042 and NIST SP 800-86 only as guidance, without claiming formal compliance; no confidential
data sent to unauthorized external AI services.
