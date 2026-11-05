"""Held-out evaluation: new random seeds that no threshold was tuned on.

Each seed regenerates the dataset with new signatures, photos, paper grain and transactions, then
runs the normal benchmark on it. Templates, applicants and tamper types stay the same, so this tests
stability against new randomness on known kinds of document. It says nothing about real documents.

Usage:
    .venv/bin/python -m scripts.run_holdout --seeds 8001 8002 8003 8004 8005
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run(args: list[str]) -> None:
    subprocess.run([sys.executable, *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True)


def _totals(summaries: list[dict]) -> dict:
    def add(path: str) -> int:
        total = 0
        for s in summaries:
            node = s
            for key in path.split("."):
                node = node[key]
            total += node
        return total

    return {
        "manipulations_injected": add("manipulation.ground_truth_total"),
        "manipulations_localized": sum(
            round((s["manipulation"]["recall_localized"] or 0) * s["manipulation"]["ground_truth_total"])
            for s in summaries
        ),
        "potential_manipulation_predictions": add("manipulation.predictions_potential_manipulation"),
        "potential_manipulation_matched": add("manipulation.predictions_matched"),
        "discrepancies": add("discrepancy.ground_truth_total"),
        "discrepancies_found": add("discrepancy.found"),
        "within_document": add("within_document.total"),
        "within_document_found": add("within_document.found"),
        "inconsistencies": add("inconsistency.total"),
        "inconsistencies_matched": add("inconsistency.matched"),
        "fields": add("fields.total"),
        "fields_correct": add("fields.value_correct"),
        "table_rows": add("tables.total"),
        "table_rows_correct": add("tables.correct"),
        "documents": add("classification.total"),
        "documents_classified": add("classification.correct"),
        "clean_case_flags": add("clean_cases.potential_manipulation_findings")
        + add("clean_cases.inconsistency_findings"),
        "pipeline_errors": add("pipeline_errors"),
    }


def _row(label: str, hit: int, total: int) -> str:
    pct = f"{hit / total * 100:.1f}%" if total else "n/a"
    return f"| {label} | {pct} | {hit}/{total} |"


def _table(t: dict) -> list[str]:
    return [
        "| Metric | Result | Count |",
        "|---|---|---|",
        _row("Manipulation recall (localized)", t["manipulations_localized"], t["manipulations_injected"]),
        _row("Manipulation precision", t["potential_manipulation_matched"], t["potential_manipulation_predictions"]),
        _row("Cross-document discrepancy recall", t["discrepancies_found"], t["discrepancies"]),
        _row("Within-document conflict recall", t["within_document_found"], t["within_document"]),
        _row("Inconsistency precision", t["inconsistencies_matched"], t["inconsistencies"]),
        _row("Field value accuracy", t["fields_correct"], t["fields"]),
        _row("Table row accuracy", t["table_rows_correct"], t["table_rows"]),
        _row("Classification accuracy", t["documents_classified"], t["documents"]),
        f"| False flags on clean cases | {t['clean_case_flags']} | |",
        f"| Pipeline errors | {t['pipeline_errors']} | |",
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "docs")
    args = parser.parse_args()

    clean, noisy, misses = [], [], []
    with tempfile.TemporaryDirectory(prefix="docuforensic-holdout-") as tmp:
        for seed in args.seeds:
            print(f"[holdout] seed {seed}", flush=True)
            data, out = Path(tmp) / f"data_{seed}", Path(tmp) / f"result_{seed}"
            _run(["scripts/generate_dataset.py", "--seed", str(seed), "--out", str(data)])
            _run(["-m", "scripts.run_benchmark", "--dataset", str(data), "--out", str(out)])
            result = json.loads((out / "benchmark_results.json").read_text())
            clean.append(result["summary_clean_scans"])
            noisy.append(result["summary_noise"])
            for case in result["cases"]:
                if "__" in case["case"]:
                    continue
                for m in case["manipulations"]:
                    if not m["localized_potential_manipulation"]:
                        misses.append(f"Seed {seed}, {case['case']}: missed {m['id']} ({m['type']})")
                for d in case["discrepancies"]:
                    if not d["found"]:
                        misses.append(f"Seed {seed}, {case['case']}: missed {d['discrepancy_type']}")
                for u in case["unmatched_findings"]:
                    if u["status"] != "OBSERVATION":
                        misses.append(f"Seed {seed}, {case['case']}: unmatched {u['status']} from {u['detector']}")

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
    t_clean, t_noisy = _totals(clean), _totals(noisy)
    lines = [
        "# Held-Out Evaluation",
        "",
        f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} at commit `{commit}`, on seeds "
        f"{', '.join(map(str, args.seeds))}. These seeds were not used for tuning before this run.",
        "",
        "> **What this does and doesn't show.** Each seed has new signatures, photos, paper grain and "
        "transactions, but the same templates, applicants and tamper types. It tests stability against "
        "new randomness on known kinds of document. It is **not an estimate of performance on real "
        "documents**, whose layouts and edits we have not tested.",
        "",
        "## Original documents",
        "",
        *_table(t_clean),
        "",
        "## Degraded scans (rotation, blur, heavy JPEG)",
        "",
        *_table(t_noisy),
        "",
        "## Every miss and unmatched flag on original documents",
        "",
        *([f"- {m}" for m in misses] or ["None."]),
        "",
    ]
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "holdout_results.md").write_text("\n".join(lines))
    (args.out / "holdout_results.json").write_text(
        json.dumps({"seeds": args.seeds, "commit": commit, "original": t_clean, "degraded": t_noisy, "misses": misses}, indent=2)
    )
    print(json.dumps({"original": t_clean, "degraded": t_noisy, "misses": misses}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
