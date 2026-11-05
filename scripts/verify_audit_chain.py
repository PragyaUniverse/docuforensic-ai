#!/usr/bin/env python
"""Verifies the audit hash chain in the configured database. Exit code 1 if it's broken."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit import chain


def main() -> int:
    result = chain.verify()
    if result.ok:
        print(f"OK: {result.entries_checked} entries verified. Head {result.head_hash}")
        return 0
    print(f"BROKEN at seq {result.first_bad_seq}: {result.reason} ({result.entries_checked} entries were valid before it)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
