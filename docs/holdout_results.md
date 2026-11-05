# Held-Out Evaluation

Generated 2026-11-05T08:45:16+00:00 at commit `9433b6f`, on seeds 8001, 8002, 8003, 8004, 8005. These seeds were not used for tuning before this run.

> **What this does and doesn't show.** Each seed has new signatures, photos, paper grain and transactions, but the same templates, applicants and tamper types. It tests stability against new randomness on known kinds of document. It is **not an estimate of performance on real documents**, whose layouts and edits we have not tested.

## Original documents

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 100.0% | 30/30 |
| Manipulation precision | 100.0% | 30/30 |
| Cross-document discrepancy recall | 100.0% | 65/65 |
| Within-document conflict recall | 100.0% | 20/20 |
| Inconsistency precision | 100.0% | 85/85 |
| Field value accuracy | 99.9% | 1159/1160 |
| Table row accuracy | 100.0% | 540/540 |
| Classification accuracy | 100.0% | 120/120 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Degraded scans (rotation, blur, heavy JPEG)

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 22.2% | 10/45 |
| Manipulation precision | 90.9% | 10/11 |
| Cross-document discrepancy recall | n/a | 0/0 |
| Within-document conflict recall | n/a | 0/0 |
| Inconsistency precision | 91.4% | 32/35 |
| Field value accuracy | 99.2% | 1175/1185 |
| Table row accuracy | n/a | 0/0 |
| Classification accuracy | 100.0% | 105/105 |
| False flags on clean cases | 1 | |
| Pipeline errors | 0 | |

## Every miss and unmatched flag on original documents

None.
