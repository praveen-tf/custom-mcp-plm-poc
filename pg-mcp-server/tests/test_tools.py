"""Tests for the MCP tool functions (without a live database)."""

import asyncio

import pytest

import main


def test_list_accessible_tables_returns_only_whitelist():
    catalog = main.list_accessible_tables()
    assert catalog["schema"] == "centric_8_plm"
    styles_cols = {entry["column"] for entry in catalog["tables"]["styles"]}
    assert "code" in styles_cols
    assert "password_hash" not in styles_cols
    assert "_airbyte_raw_id" not in styles_cols


def test_describe_table_unknown_raises_value_error():
    with pytest.raises(ValueError):
        main.describe_table("not_a_table")


def test_query_rejects_non_select():
    with pytest.raises(ValueError):
        asyncio.run(main.query("DELETE FROM styles"))


def test_query_rejects_disallowed_column():
    with pytest.raises(ValueError):
        asyncio.run(main.query("SELECT mgf_godiva_margin FROM styles"))


def test_query_runs_validated_select(monkeypatch):
    captured = {}

    async def fake_execute(query, params=None):
        captured["query"] = query
        return [{"code": "AW-1"}]

    monkeypatch.setattr(main.database, "execute", fake_execute)
    rows = asyncio.run(main.query("SELECT code FROM styles WHERE collection = 'x'"))
    assert rows == [{"code": "AW-1"}]
    assert "LIMIT" in captured["query"].upper()  # row cap enforced
