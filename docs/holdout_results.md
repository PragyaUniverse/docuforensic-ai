# Held-Out Evaluation

Generated 2026-11-05T11:08:12+00:00 at commit `3606ff9`, on seeds 9201, 9202, 9203, 9204, 9205. These seeds were not used for tuning before this run.

> **What this does and doesn't show.** Each seed has new signatures, photos, paper grain and transactions, but the same templates, applicants and tamper types. It tests stability against new randomness on known kinds of document. It is **not an estimate of performance on real documents**, whose layouts and edits we have not tested.

## Original documents

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 100.0% | 30/30 |
| Manipulation precision | 96.8% | 30/31 |
| Cross-document discrepancy recall | 100.0% | 65/65 |
| Within-document conflict recall | 100.0% | 30/30 |
| Inconsistency precision | 100.0% | 95/95 |
| Field value accuracy | 100.0% | 1160/1160 |
| Table row accuracy | 100.0% | 540/540 |
| Classification accuracy | 100.0% | 120/120 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Degraded scans (rotation, blur, heavy JPEG)

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 42.2% | 19/45 |
| Manipulation precision | 100.0% | 19/19 |
| Cross-document discrepancy recall | n/a | 0/0 |
| Within-document conflict recall | n/a | 0/0 |
| Inconsistency precision | 100.0% | 44/44 |
| Field value accuracy | 99.4% | 1178/1185 |
| Table row accuracy | n/a | 0/0 |
| Classification accuracy | 100.0% | 105/105 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Every miss and unmatched flag on original documents

- Seed 9204, case_d_pdf: unmatched POTENTIAL_MANIPULATION from visual.signature_reuse
