# Held-Out Evaluation

Generated 2026-11-05T09:16:43+00:00 at commit `adad780`, on seeds 9001, 9002, 9003, 9004, 9005. These seeds were not used for tuning before this run.

> **What this does and doesn't show.** Each seed has new signatures, photos, paper grain and transactions, but the same templates, applicants and tamper types. It tests stability against new randomness on known kinds of document. It is **not an estimate of performance on real documents**, whose layouts and edits we have not tested.

## Original documents

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 100.0% | 30/30 |
| Manipulation precision | 93.8% | 30/32 |
| Cross-document discrepancy recall | 100.0% | 65/65 |
| Within-document conflict recall | 100.0% | 30/30 |
| Inconsistency precision | 97.9% | 95/97 |
| Field value accuracy | 99.8% | 1158/1160 |
| Table row accuracy | 99.6% | 538/540 |
| Classification accuracy | 100.0% | 120/120 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Degraded scans (rotation, blur, heavy JPEG)

| Metric | Result | Count |
|---|---|---|
| Manipulation recall (localized) | 22.2% | 10/45 |
| Manipulation precision | 100.0% | 10/10 |
| Cross-document discrepancy recall | n/a | 0/0 |
| Within-document conflict recall | n/a | 0/0 |
| Inconsistency precision | 100.0% | 43/43 |
| Field value accuracy | 99.3% | 1177/1185 |
| Table row accuracy | n/a | 0/0 |
| Classification accuracy | 100.0% | 105/105 |
| False flags on clean cases | 0 | |
| Pipeline errors | 0 | |

## Every miss and unmatched flag on original documents

- Seed 9001, case_c_crossdoc: unmatched POTENTIAL_MANIPULATION from pdf.text_vs_pixels
- Seed 9001, case_c_crossdoc: unmatched INCONSISTENCY from context.arithmetic_balance
- Seed 9002, case_c_crossdoc: unmatched POTENTIAL_MANIPULATION from pdf.text_vs_pixels
- Seed 9002, case_c_crossdoc: unmatched INCONSISTENCY from context.arithmetic_balance
