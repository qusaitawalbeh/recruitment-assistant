import sqlite3
import pytest
from src import database


def test_connection_closes_after_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with database.connection() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")


def test_transaction_rolls_back_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with pytest.raises(RuntimeError):
        with database.connection() as connection:
            connection.execute("INSERT INTO jobs(id,title,description,requirements,created_at) VALUES(?,?,?,?,?)",
                               ("j1", "Title", "Description", "[]", "now"))
            raise RuntimeError("abort transaction")
    assert database.list_jobs() == []
