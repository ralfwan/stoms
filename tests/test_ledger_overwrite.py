"""Exports never overwrite the source ledger, extxyz never any ledger, and
read-only opens never write."""

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest
from test_aggregation_export import evaluation, structure

from stoms.atomsledger import (
    AggregationMemberInput,
    AtomsLedger,
    IntegrityError,
    LedgerOverwriteError,
    SQLiteRepository,
)
from stoms.cli import main


def _ledger(path: Path) -> tuple[AtomsLedger, str]:
    """A ledger with one aggregation of two evaluated structures."""
    ledger = AtomsLedger(path)
    ids = [structure(ledger, i) for i in range(2)]
    members = [
        AggregationMemberInput(sid, evaluation(ledger, sid, -1.0 - i))
        for i, sid in enumerate(ids)
    ]
    aggregation = ledger.create_aggregation(name="set", members=members)
    return ledger, aggregation.id


def _intact(path: Path, count: int = 1) -> None:
    assert len(AtomsLedger.open(path).list_aggregations()) == count


@pytest.mark.parametrize("link", [None, "symlink", "hardlink"])
def test_sqlite_exports_never_replace_the_source(
    tmp_path: Path, link: str | None
) -> None:
    path = tmp_path / "data.ledger"
    ledger, aggregation_id = _ledger(path)
    destination = path
    if link == "symlink":
        destination = tmp_path / "alias.ledger"
        destination.symlink_to(path)
    elif link == "hardlink":
        destination = tmp_path / "alias.ledger"
        os.link(path, destination)
    with pytest.raises(LedgerOverwriteError, match="source ledger"):
        ledger.export_database(destination, overwrite=True)
    with pytest.raises(LedgerOverwriteError, match="source ledger"):
        ledger.export_aggregation(aggregation_id, destination, overwrite=True)
    _intact(path)


def test_extxyz_never_replaces_a_ledger(tmp_path: Path) -> None:
    path = tmp_path / "data.ledger"
    ledger, aggregation_id = _ledger(path)
    other = tmp_path / "other.ledger"
    _ledger(other)
    for destination in (path, other):
        with pytest.raises(LedgerOverwriteError):
            ledger.to_extxyz(destination, aggregation_id=aggregation_id)
    _intact(path)
    _intact(other)


def test_extxyz_replaces_an_earlier_export(tmp_path: Path) -> None:
    ledger, aggregation_id = _ledger(tmp_path / "data.ledger")
    destination = tmp_path / "train.extxyz"
    destination.write_text("old export\n")
    assert ledger.to_extxyz(destination, aggregation_id=aggregation_id) == 2
    assert destination.read_text().startswith("1\n")


def test_cli_extxyz_onto_the_ledger_is_refused(tmp_path: Path, capsys) -> None:
    path = tmp_path / "data.ledger"
    _, aggregation_id = _ledger(path)
    command = ["--ledger", str(path), "aggregations", "to-extxyz"]
    assert main([*command, aggregation_id, str(path)]) == 1
    assert "source ledger" in capsys.readouterr().err
    _intact(path)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_read_only_ledgers_refuse_every_write(tmp_path: Path) -> None:
    path = tmp_path / "data.ledger"
    _, aggregation_id = _ledger(path)
    before = _digest(path)
    ledger = AtomsLedger.open(path, read_only=True)
    assert ledger.get_aggregation(aggregation_id).name == "set"
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        structure(ledger, 9)
    assert _digest(path) == before


def test_read_only_needs_an_existing_ledger(tmp_path: Path) -> None:
    missing = tmp_path / "typo.ledger"
    with pytest.raises(IntegrityError):
        AtomsLedger.open(missing, read_only=True)
    assert not missing.exists()
    # Another program's SQLite database is not a ledger, and stays as it is.
    other = tmp_path / "other.sqlite"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE notes (text TEXT)")
    before = _digest(other)
    with pytest.raises(IntegrityError):
        AtomsLedger.open(other, read_only=True)
    assert _digest(other) == before


def test_read_only_reads_a_wal_ledger(tmp_path: Path) -> None:
    path = tmp_path / "wal.ledger"
    _, aggregation_id = _ledger(path)
    SQLiteRepository(path, journal_mode="WAL")  # switch the file to WAL
    ledger = AtomsLedger.open(path, read_only=True)
    assert ledger.get_aggregation(aggregation_id).name == "set"


def test_cli_reads_ledgers_without_changing_other_files(
    tmp_path: Path, capsys
) -> None:
    other = tmp_path / "other.sqlite"
    with sqlite3.connect(other) as connection:
        connection.execute("CREATE TABLE notes (text TEXT)")
    before = _digest(other)
    assert main(["--ledger", str(other), "aggregations", "list"]) == 1
    assert "not" in capsys.readouterr().err
    assert _digest(other) == before
