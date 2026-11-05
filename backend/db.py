"""SQLite persistence. Domain objects are stored as validated JSON documents."""
from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterable

from config.settings import settings
from models.schemas import Case, Document, Dossier, Entity, EvidenceGraph, Finding

_lock = threading.RLock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, created_at TEXT, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, seq INTEGER,
    source_path TEXT, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS documents_case ON documents(case_id);
CREATE TABLE IF NOT EXISTS findings (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS findings_case ON findings(case_id);
CREATE TABLE IF NOT EXISTS entities (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, json TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entities_case ON entities(case_id);
CREATE TABLE IF NOT EXISTS graphs (case_id TEXT PRIMARY KEY, json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS dossiers (case_id TEXT PRIMARY KEY, json TEXT NOT NULL);
"""


def connect() -> sqlite3.Connection:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_SCHEMA)
    return conn


def _write(sql: str, args: tuple = ()) -> None:
    with _lock:
        conn = connect()
        try:
            conn.execute(sql, args)
            conn.commit()
        finally:
            conn.close()


def _read(sql: str, args: tuple = ()) -> list[sqlite3.Row]:
    conn = connect()
    try:
        return conn.execute(sql, args).fetchall()
    finally:
        conn.close()


# ---- cases
def save_case(case: Case) -> Case:
    _write("INSERT OR REPLACE INTO cases VALUES (?,?,?)",
           (case.id, case.created_at.isoformat(), case.model_dump_json()))
    return case


def get_case(case_id: str) -> Case | None:
    rows = _read("SELECT json FROM cases WHERE id = ?", (case_id,))
    return Case.model_validate_json(rows[0]["json"]) if rows else None


def list_cases() -> list[Case]:
    rows = _read("SELECT json FROM cases ORDER BY created_at DESC")
    return [Case.model_validate_json(r["json"]) for r in rows]


# ---- documents
def save_document(doc: Document, source_path: str | None = None) -> Document:
    with _lock:
        conn = connect()
        try:
            existing = conn.execute("SELECT seq, source_path FROM documents WHERE id = ?",
                                    (doc.id,)).fetchone()
            if existing:
                seq, src = existing["seq"], source_path or existing["source_path"]
            else:
                seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM documents WHERE case_id = ?",
                                   (doc.case_id,)).fetchone()[0]
                src = source_path
            conn.execute("INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?)",
                         (doc.id, doc.case_id, seq, src, doc.model_dump_json()))
            conn.commit()
        finally:
            conn.close()
    return doc


def get_document(doc_id: str) -> Document | None:
    rows = _read("SELECT json FROM documents WHERE id = ?", (doc_id,))
    return Document.model_validate_json(rows[0]["json"]) if rows else None


def list_documents(case_id: str) -> list[Document]:
    rows = _read("SELECT json FROM documents WHERE case_id = ? ORDER BY seq", (case_id,))
    return [Document.model_validate_json(r["json"]) for r in rows]


def document_source(doc_id: str) -> str | None:
    rows = _read("SELECT source_path FROM documents WHERE id = ?", (doc_id,))
    return rows[0]["source_path"] if rows else None


def delete_document(doc_id: str) -> None:
    _write("DELETE FROM documents WHERE id = ?", (doc_id,))


# ---- findings
def replace_findings(case_id: str, findings: Iterable[Finding]) -> None:
    with _lock:
        conn = connect()
        try:
            conn.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
            conn.executemany("INSERT OR REPLACE INTO findings VALUES (?,?,?)",
                             [(f.id, case_id, f.model_dump_json()) for f in findings])
            conn.commit()
        finally:
            conn.close()


def save_finding(finding: Finding) -> Finding:
    _write("INSERT OR REPLACE INTO findings VALUES (?,?,?)",
           (finding.id, finding.case_id, finding.model_dump_json()))
    return finding


def get_finding(finding_id: str) -> Finding | None:
    rows = _read("SELECT json FROM findings WHERE id = ?", (finding_id,))
    return Finding.model_validate_json(rows[0]["json"]) if rows else None


def list_findings(case_id: str) -> list[Finding]:
    rows = _read("SELECT json FROM findings WHERE case_id = ?", (case_id,))
    return [Finding.model_validate_json(r["json"]) for r in rows]


# ---- entities, graph, dossier
def replace_entities(case_id: str, entities: Iterable[Entity]) -> None:
    with _lock:
        conn = connect()
        try:
            conn.execute("DELETE FROM entities WHERE case_id = ?", (case_id,))
            conn.executemany("INSERT OR REPLACE INTO entities VALUES (?,?,?)",
                             [(e.id, case_id, e.model_dump_json()) for e in entities])
            conn.commit()
        finally:
            conn.close()


def list_entities(case_id: str) -> list[Entity]:
    rows = _read("SELECT json FROM entities WHERE case_id = ?", (case_id,))
    return [Entity.model_validate_json(r["json"]) for r in rows]


def save_graph(graph: EvidenceGraph) -> None:
    _write("INSERT OR REPLACE INTO graphs VALUES (?,?)", (graph.case_id, graph.model_dump_json()))


def get_graph(case_id: str) -> EvidenceGraph | None:
    rows = _read("SELECT json FROM graphs WHERE case_id = ?", (case_id,))
    return EvidenceGraph.model_validate_json(rows[0]["json"]) if rows else None


def save_dossier(dossier: Dossier) -> None:
    _write("INSERT OR REPLACE INTO dossiers VALUES (?,?)", (dossier.case_id, dossier.model_dump_json()))


def get_dossier(case_id: str) -> Dossier | None:
    rows = _read("SELECT json FROM dossiers WHERE case_id = ?", (case_id,))
    return Dossier.model_validate_json(rows[0]["json"]) if rows else None
