"""Tests for the open-query AST validator — the security-critical gate."""

import pytest

from query_validator import (
    QueryNotAllowed,
    enforce_limit,
    placeholder_names,
    validate_select,
    validate_template_sql,
)

SCHEMA = "centric_8_plm"
ALLOWED = {
    "styles": {"id", "code", "collection", "fob_calc"},
    "seasons": {"id", "code"},
}


def test_valid_select_passes():
    validate_select("SELECT code, fob_calc FROM styles WHERE collection = 'x'", SCHEMA, ALLOWED)


def test_schema_qualified_table_passes():
    validate_select("SELECT code FROM centric_8_plm.styles", SCHEMA, ALLOWED)


def test_join_of_two_whitelisted_tables_passes():
    validate_select(
        "SELECT s.code FROM styles s JOIN seasons se ON s.code = se.code", SCHEMA, ALLOWED
    )


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO styles (id) VALUES ('x')",
        "UPDATE styles SET code = 'x'",
        "DELETE FROM styles",
        "DROP TABLE styles",
        "TRUNCATE styles",
    ],
)
def test_non_select_rejected(sql):
    with pytest.raises(QueryNotAllowed):
        validate_select(sql, SCHEMA, ALLOWED)


def test_multiple_statements_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT code FROM styles; DROP TABLE styles", SCHEMA, ALLOWED)


def test_select_star_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT * FROM styles", SCHEMA, ALLOWED)


def test_disallowed_table_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT id FROM secrets", SCHEMA, ALLOWED)


def test_disallowed_column_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT password_hash FROM styles", SCHEMA, ALLOWED)


def test_disallowed_schema_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT code FROM other_schema.styles", SCHEMA, ALLOWED)


def test_unparseable_sql_rejected():
    with pytest.raises(QueryNotAllowed):
        validate_select("SELECT FROM WHERE", SCHEMA, ALLOWED)


def test_enforce_limit_appends_when_missing():
    out = enforce_limit("SELECT code FROM styles", 200)
    assert out.strip().endswith("LIMIT 200")


def test_enforce_limit_keeps_existing_limit():
    sql = "SELECT code FROM styles LIMIT 5"
    assert enforce_limit(sql, 200) == sql


def test_placeholder_names_extracted():
    assert placeholder_names("SELECT 1 WHERE a = %(x)s AND b = %(y)s") == {"x", "y"}


def test_validate_template_sql_accepts_placeholders():
    validate_template_sql(
        "SELECT code FROM styles WHERE collection = %(collection)s", SCHEMA, ALLOWED
    )


def test_validate_template_sql_rejects_bad_column():
    with pytest.raises(QueryNotAllowed):
        validate_template_sql("SELECT ssn FROM styles WHERE id = %(id)s", SCHEMA, ALLOWED)
