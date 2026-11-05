# Evidence Traceability Demonstration

Required deliverable 7: showing that any finding can be traced to its original document location, and
back again.

## The chain being demonstrated

```
Original file (SHA-256 recorded on submission)
  → page image (canonical pixels)
    → OCR word (text, confidence, bbox, engine)
      → extracted field (value, confidence, page, bbox, source)
        → finding (status, detector, region, evidence, related fields)
          → evidence graph edge
            → dossier section 7.5 entry
              → audit entries for each step, hash-chained
```

## Procedure

1. Start the app, click **Load demo case**, choose Case C (cross-document), and run it.
2. **Finding to source.** Open a date-of-birth conflict. Click its evidence on each side. The viewer
   opens the right document and page with the exact region highlighted.
3. **Source to finding.** In the extracted data table, click that field. The viewer highlights its
   location, and related findings are listed.
4. **Graph.** Open the evidence graph. The red edge between the two documents is the same finding.
5. **Dossier.** Find the finding in section 7.5, with its document, page, bbox, field ids and evidence.
6. **Original file.** Compare the SHA-256 in section 7.1 against the file:

   ```bash
   shasum -a 256 data/synthetic_cases/case_c_crossdoc/<file>
   ```

7. **Audit.** Open the audit trail, press **Verify integrity** (passes), use the tamper demo (fails at
   the edited entry), then restore (passes).

## Automated check

`tests/e2e/test_traceability.py` walks the chain on all four demo cases. For every finding, it asserts
that the document and page exist and that the region sits within the page. It also asserts that every
referenced field exists and locates its value, and that every cross-document finding is located on at
least two documents.

```bash
.venv/bin/python -m pytest tests/e2e/test_traceability.py
```
