import sqlite3

import pytest

from audit import chain
from config.settings import settings


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "data_dir", tmp_path)


def fill(n=4):
    return [chain.append(f"test.{i}", "system", "c1", {"n": i}) for i in range(n)]


def edit(sql, *args):
    conn = sqlite3.connect(settings.db_path)
    conn.execute(sql, args)
    conn.commit()
    conn.close()


def test_empty_chain_verifies():
    result = chain.verify()
    assert result.ok and result.entries_checked == 0


def test_entries_link_and_verify():
    items = fill()
    assert items[1].prev_hash == items[0].entry_hash and items[0].prev_hash == chain.GENESIS
    result = chain.verify()
    assert result.ok and result.entries_checked == 4 and result.head_hash == items[-1].entry_hash


def test_edited_payload_is_caught_at_that_entry():
    fill()
    edit("UPDATE audit_log SET payload='{\"n\":99}' WHERE seq=2")
    result = chain.verify()
    assert not result.ok and result.first_bad_seq == 2 and "edited" in result.reason


def test_rehashed_entry_still_breaks_the_next_link():
    fill()
    row = chain.entries()[1]
    forged = chain.compute_hash(row.seq, row.ts.isoformat(), row.case_id, row.actor, row.action, '{"n":99}', row.prev_hash)
    edit("UPDATE audit_log SET payload='{\"n\":99}', entry_hash=? WHERE seq=2", forged)
    result = chain.verify()
    assert not result.ok and result.first_bad_seq == 3


@pytest.mark.parametrize("seq,why", [(4, "tail"), (2, "gap")])
def test_deleted_entries_are_caught(seq, why):
    fill()
    edit("DELETE FROM audit_log WHERE seq=?", seq)
    result = chain.verify()
    assert not result.ok and result.reason


def test_tamper_demo_breaks_then_restores_exactly_and_repeatedly():
    fill()
    original = [e.model_dump() for e in chain.entries()]
    for _ in range(2):
        seq = chain.tamper_demo()
        assert chain.tamper_active_seq() == seq
        assert chain.tamper_demo() == seq, "a second press doesn't overwrite the backup"
        assert chain.verify().first_bad_seq == seq
        assert chain.restore_tamper_demo() == seq
        assert chain.tamper_active_seq() is None
        assert chain.verify().ok
    assert [e.model_dump() for e in chain.entries()] == original


def test_restore_without_tamper_is_harmless_and_appends_keep_chaining():
    fill(2)
    assert chain.restore_tamper_demo() is None
    seq = chain.tamper_demo()
    chain.append("later", "system")
    assert chain.verify().first_bad_seq == seq
    chain.restore_tamper_demo()
    assert chain.verify().ok


def test_empty_log_has_nothing_to_tamper():
    assert chain.tamper_demo() is None


def test_filter_by_case():
    chain.append("a", "system", "c1")
    chain.append("b", "system", "c2")
    assert [e.action for e in chain.entries("c2")] == ["b"]
