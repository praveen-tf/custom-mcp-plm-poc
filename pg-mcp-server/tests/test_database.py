"""Tests for the Database layer that don't require a live PostgreSQL.

End-to-end behavior (read-only enforcement, timeouts, sensitive-column unreachability)
is covered by the integration test, which needs a disposable database.
"""

from database import Database


def test_database_constructs_without_connecting():
    db = Database(
        "postgresql://u:p@localhost:5432/db",
        schema="centric_8_plm",
        statement_timeout_ms=5000,
        max_rows=200,
    )
    assert db._max_rows == 200
    # The pool is created but not opened, so no connection is attempted here.
    assert db._pool is not None
