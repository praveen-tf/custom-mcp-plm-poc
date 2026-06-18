"""Generate the least-privilege DB role + column-level GRANTs from ``policy.yaml``.

Usage (from the project root):
    uv run python scripts/generate_role_sql.py > sql/role_setup.sql

The output creates a NOSUPERUSER login role with **column-level SELECT grants only**.
We never emit a table-level ``GRANT SELECT``: per the PostgreSQL docs a table-level grant
overrides column restrictions and would re-expose sensitive columns. Regenerate whenever
``policy.yaml`` changes so the database privileges track the whitelist.
"""

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from access_policy import AccessPolicy  # noqa: E402 (path set up above)

ROLE = "mcp_readonly"


def render(policy: AccessPolicy) -> str:
    schema = policy.schema
    lines = [
        "-- GENERATED from policy.yaml by scripts/generate_role_sql.py — do not edit by hand.",
        f"-- Least-privilege, read-only role for the Postgres MCP server (schema: {schema}).",
        "",
        f"CREATE ROLE {ROLE} LOGIN PASSWORD 'CHANGE_ME' NOSUPERUSER NOCREATEDB NOCREATEROLE;",
        "",
        "-- Start from zero, then grant only what the whitelist needs.",
        f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {ROLE};",
        f"REVOKE ALL ON SCHEMA {schema} FROM {ROLE};",
        f"GRANT USAGE ON SCHEMA {schema} TO {ROLE};",
        "",
        f"ALTER ROLE {ROLE} SET default_transaction_read_only = on;",
        "",
        "-- COLUMN-LEVEL SELECT ONLY. Never add a table-level GRANT SELECT below:",
        "-- it would override these column restrictions and re-expose hidden columns.",
    ]
    for table in policy.tables:
        columns = ", ".join(sorted(policy.allowlist[table]))
        lines.append(f"GRANT SELECT ({columns}) ON {schema}.{table} TO {ROLE};")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render(AccessPolicy.from_file(_PROJECT_ROOT / "policy.yaml")), end="")
