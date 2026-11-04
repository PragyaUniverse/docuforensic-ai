"""Hash-chained, append-only audit trail stored in SQLite.

Each entry's hash covers its content and the previous hash, so editing any stored entry breaks
verification at that entry. A separate head record catches truncation of the tail. This is
tamper-evident against edits to the log, not tamper-proof against someone who can rewrite the
whole chain and the head; see docs/LIMITATIONS.md.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from config.settings import settings
from models.schemas import AuditEntry, AuditVerification

GENESIS = "0" * 64
_lock = threading.RLock()


def _connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS audit_log (
            seq INTEGER PRIMARY KEY, ts TEXT NOT NULL, case_id TEXT, actor TEXT NOT NULL,
            action TEXT NOT NULL, payload TEXT NOT NULL, prev_hash TEXT NOT NULL,
            entry_hash TEXT NOT NULL)"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS audit_case ON audit_log(case_id)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_head (id INTEGER PRIMARY KEY CHECK (id = 1), "
        "seq INTEGER NOT NULL, entry_hash TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS audit_tamper_backup (seq INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
    )
    return conn


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(seq: int, ts: str, case_id: str | None, actor: str, action: str,
                 payload_json: str, prev_hash: str) -> str:
    blob = canonical_json([seq, ts, case_id, actor, action, payload_json, prev_hash])
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _row_to_entry(row: sqlite3.Row) -> AuditEntry:
    return AuditEntry(
        seq=row["seq"], ts=datetime.fromisoformat(row["ts"]), case_id=row["case_id"],
        actor=row["actor"], action=row["action"], payload=json.loads(row["payload"]),
        prev_hash=row["prev_hash"], entry_hash=row["entry_hash"],
    )


def append(action: str, actor: str = "system", case_id: str | None = None,
           payload: dict[str, Any] | None = None) -> AuditEntry:
    payload_json = canonical_json(payload or {})
    ts = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            last = conn.execute(
                "SELECT seq, entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").fetchone()
            seq = (last["seq"] + 1) if last else 1
            prev = last["entry_hash"] if last else GENESIS
            entry_hash = compute_hash(seq, ts, case_id, actor, action, payload_json, prev)
            conn.execute(
                "INSERT INTO audit_log VALUES (?,?,?,?,?,?,?,?)",
                (seq, ts, case_id, actor, action, payload_json, prev, entry_hash),
            )
            conn.execute(
                "INSERT INTO audit_head (id, seq, entry_hash) VALUES (1, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET seq=excluded.seq, entry_hash=excluded.entry_hash",
                (seq, entry_hash),
            )
            conn.commit()
        finally:
            conn.close()
    return AuditEntry(seq=seq, ts=datetime.fromisoformat(ts), case_id=case_id, actor=actor,
                      action=action, payload=payload or {}, prev_hash=prev, entry_hash=entry_hash)


def entries(case_id: str | None = None, limit: int | None = None) -> list[AuditEntry]:
    conn = _connect()
    try:
        sql = "SELECT * FROM audit_log"
        args: list[Any] = []
        if case_id:
            sql += " WHERE case_id = ?"
            args.append(case_id)
        sql += " ORDER BY seq"
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        return [_row_to_entry(r) for r in conn.execute(sql, args).fetchall()]
    finally:
        conn.close()


def verify(case_id: str | None = None) -> AuditVerification:
    """Walks the whole chain. It is global, so case_id only exists for interface symmetry."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY seq").fetchall()
        head = conn.execute("SELECT seq, entry_hash FROM audit_head WHERE id = 1").fetchone()
    finally:
        conn.close()

    prev = GENESIS
    expected_seq = 1
    for checked, row in enumerate(rows):
        bad = None
        if row["seq"] != expected_seq:
            bad = f"sequence gap: expected {expected_seq}, found {row['seq']} (entries removed)"
        elif row["prev_hash"] != prev:
            bad = "previous-hash link is broken"
        else:
            actual = compute_hash(row["seq"], row["ts"], row["case_id"], row["actor"],
                                  row["action"], row["payload"], row["prev_hash"])
            if actual != row["entry_hash"]:
                bad = "stored entry does not match its hash (content was edited)"
        if bad:
            return AuditVerification(ok=False, entries_checked=checked, first_bad_seq=row["seq"],
                                     reason=bad, head_hash=head["entry_hash"] if head else None)
        prev = row["entry_hash"]
        expected_seq += 1

    if head and (head["seq"] != len(rows) or head["entry_hash"] != prev):
        return AuditVerification(ok=False, entries_checked=len(rows), first_bad_seq=len(rows) + 1,
                                 reason="chain is shorter than the recorded head (tail removed)",
                                 head_hash=head["entry_hash"])
    if not head and rows:
        return AuditVerification(ok=False, entries_checked=len(rows), first_bad_seq=None,
                                 reason="head record is missing", head_hash=None)
    return AuditVerification(ok=True, entries_checked=len(rows), head_hash=prev if rows else None)


def head_hash() -> str | None:
    conn = _connect()
    try:
        row = conn.execute("SELECT entry_hash FROM audit_head WHERE id = 1").fetchone()
        return row["entry_hash"] if row else None
    finally:
        conn.close()


# ---- Demo helpers: edit a stored entry without rehashing, and put it back exactly.
def tamper_demo(case_id: str | None = None) -> int | None:
    """Edits one entry's payload without rehashing. Returns its seq, or None for an empty log."""
    with _lock:
        conn = _connect()
        try:
            existing = conn.execute("SELECT seq FROM audit_tamper_backup LIMIT 1").fetchone()
            if existing:
                return existing["seq"]
            sql = "SELECT seq, payload FROM audit_log WHERE action NOT LIKE 'audit.%'"
            args: list[Any] = []
            if case_id:
                sql += " AND case_id = ?"
                args.append(case_id)
            row = conn.execute(sql + " ORDER BY seq DESC LIMIT 1", args).fetchone()
            if row is None:
                return None
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO audit_tamper_backup VALUES (?, ?)", (row["seq"], row["payload"]))
            edited = json.loads(row["payload"])
            edited["edited_outside_the_system"] = True
            conn.execute("UPDATE audit_log SET payload = ? WHERE seq = ?",
                         (canonical_json(edited), row["seq"]))
            conn.commit()
            return row["seq"]
        finally:
            conn.close()


def restore_tamper_demo() -> int | None:
    with _lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT seq, payload FROM audit_tamper_backup LIMIT 1").fetchone()
            if row is None:
                return None
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE audit_log SET payload = ? WHERE seq = ?", (row["payload"], row["seq"]))
            conn.execute("DELETE FROM audit_tamper_backup")
            conn.commit()
            return row["seq"]
        finally:
            conn.close()
