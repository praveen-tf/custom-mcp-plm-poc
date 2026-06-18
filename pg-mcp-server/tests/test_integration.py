"""End-to-end integration test against a real PostgreSQL.

Skipped unless ``PGMCP_TEST_DATABASE_URL`` points at a database whose ``centric_8_plm``
schema matches ``policy.yaml`` (e.g. a read-only clone of the live DB). It exercises the
full stack: introspect -> validate policy -> run the open-query path, and confirms a
non-whitelisted column is rejected before any SQL runs.
"""

import asyncio
import os

import pytest

from access_policy import AccessPolicy
from conftest import POLICY_PATH
from database import Database
from query_validator import QueryNotAllowed, enforce_limit, validate_select

_TEST_DB = os.environ.get("PGMCP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not _TEST_DB, reason="set PGMCP_TEST_DATABASE_URL to run")


def test_end_to_end_query_and_whitelist_enforcement():
    policy = AccessPolicy.from_file(POLICY_PATH)
    database = Database(_TEST_DB, schema=policy.schema, statement_timeout_ms=5000, max_rows=10)

    async def run() -> None:
        await database.open()
        try:
            policy.validate_against_db(await database.introspect(policy.schema))

            sql = "SELECT code FROM styles"
            validate_select(sql, policy.schema, policy.allowlist)
            rows = await database.execute(enforce_limit(sql, 10))
            assert isinstance(rows, list)
            assert len(rows) <= 10

            with pytest.raises(QueryNotAllowed):
                validate_select(
                    "SELECT mgf_godiva_margin FROM styles", policy.schema, policy.allowlist
                )
        finally:
            await database.close()

    asyncio.run(run())
