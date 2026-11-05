# Held-Out Evaluation

Generated 2026-11-05T09:32:59+00:00 at commit `d2976c3`, on seeds 9101, 9102, 9103, 9104, 9105. These seeds were not used for tuning before this run.

> **What this does and doesn't show.** Each seed has new signatures, photos, paper grain and transactions, but the same templates, applicants and tamper types. It tests stability against new randomness on known kinds of document. It is **not an estimate of performance on real documents**, whose layouts and edits we have not tested.

## Original documents

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 100.0% | 30/30 |
| Manipulation precision | 100.0% | 30/30 |
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
| Manipulation recall (localized) | 24.4% | 11/45 |
| Manipulation precision | 84.6% | 11/13 |
| Cross-document discrepancy recall | n/a | 0/0 |
| Within-document conflict recall | n/a | 0/0 |
| Inconsistency precision | 97.8% | 45/46 |
| Field value accuracy | 99.4% | 1178/1185 |
| Table row accuracy | n/a | 0/0 |
| Classification accuracy | 100.0% | 105/105 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Every miss and unmatched flag on original documents

None.
