#!/usr/bin/env python
"""Records real LLM answers for the demo cases into the DEMO_CACHE directory.

Every recorded entry comes from a live provider call made here. Nothing is written by hand, and
the provider and model are stored with each answer. Replay later with DEMO_CACHE=true.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import db, orchestrator
from backend.app import _ingest, _manifest
from config.settings import settings
from llm.client import get_client
from models.schemas import Case


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="Demo case key; default is every case")
    args = parser.parse_args()
    client = get_client()
    if settings.offline or not client.any_live_provider():
        print("No live LLM provider is reachable, so nothing can be recorded. Nothing was written.")
        return 1
    client.record_demo = True
    before = len(list(Path(settings.llm_cache_dir).glob("*.json"))) if Path(settings.llm_cache_dir).exists() else 0
    for entry in _manifest():
        if args.case and entry["key"] not in args.case:
            continue
        case = db.save_case(Case(name=f"warm cache: {entry['name']}", is_demo=True, demo_key=entry["key"]))
        root = Path(settings.demo_cases_dir) / entry.get("dir", entry["key"])
        for filename in entry.get("documents", []):
            _ingest(root / filename, case.id, filename)
        orchestrator.start_case(case)
        orchestrator.run_case(case.id)
        done = db.get_case(case.id)
        modes: dict[str, int] = {}
        for f in db.list_findings(case.id):
            modes[f.reasoning.mode] = modes.get(f.reasoning.mode, 0) + 1
        print(json.dumps({"case": entry["key"], "status": done.status.value, "risk": done.risk_level.value, "modes": modes}))
    after = len(list(Path(settings.llm_cache_dir).glob("*.json")))
    print(f"Demo cache now holds {after} answers ({after - before} new). Usage: {client.usage['calls']} calls, {client.usage['tokens']} tokens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
