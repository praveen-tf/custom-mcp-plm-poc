"""Pull a SMALL real sample (whitelisted columns only) and the live column types from
the source Postgres, to inform synthetic data generation.

This is the only step that touches real data, and it stays local: it writes JSON under
``scripts/sample_data/`` so you can eyeball real value shapes and so
``generate_synthetic_sql.py`` can reproduce exact column types. The sample files are
git-ignored and must NOT be shipped to the test VM — only the synthetic SQL goes there.

Requires read-only access to the source DB. Run from the project root:
    PGMCP_SOURCE_DSN='postgresql://reader:***@host:5432/mg_dwh?sslmode=require' \
        uv run python scripts/pull_sample.py --rows 25

Outputs:
    scripts/sample_data/schema_types.json   {table: {column: data_type}}
    scripts/sample_data/sample_<table>.json  up to --rows real rows (whitelisted cols)
"""

import argparse
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import psycopg  # noqa: E402 (path set up above)
import yaml  # noqa: E402
from psycopg import sql  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from models import PolicyDocument  # noqa: E402

_TYPES_SQL = """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s AND column_name = ANY(%s)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull a small whitelisted-column sample + types from source.")
    parser.add_argument("--policy", default=str(_PROJECT_ROOT / "policy.yaml"), help="Path to policy.yaml")
    parser.add_argument("--rows", type=int, default=25, help="Max sample rows per table")
    parser.add_argument(
        "--dsn",
        default=os.environ.get("PGMCP_SOURCE_DSN") or os.environ.get("PGMCP_DATABASE_URL"),
        help="Source connection string (defaults to $PGMCP_SOURCE_DSN, then $PGMCP_DATABASE_URL)",
    )
    args = parser.parse_args()
    if not args.dsn:
        parser.error("no DSN: pass --dsn or set PGMCP_SOURCE_DSN / PGMCP_DATABASE_URL")

    doc = PolicyDocument.model_validate(yaml.safe_load(Path(args.policy).read_text(encoding="utf-8")))
    out_dir = _PROJECT_ROOT / "scripts" / "sample_data"
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_types: dict[str, dict[str, str]] = {}
    with psycopg.connect(args.dsn) as conn:
        conn.read_only = True  # never write to the source
        for table, table_policy in doc.tables.items():
            columns = table_policy.columns

            with conn.cursor() as cur:
                cur.execute(_TYPES_SQL, (doc.db_schema, table, columns))
                schema_types[table] = {name: data_type for name, data_type in cur.fetchall()}

            query = sql.SQL("SELECT {cols} FROM {tbl} LIMIT %s").format(
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
                tbl=sql.Identifier(doc.db_schema, table),
            )
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(query, (args.rows,))
                rows = cur.fetchall()

            (out_dir / f"sample_{table}.json").write_text(json.dumps(rows, indent=2, default=str))
            print(f"{table}: {len(rows)} sample rows, {len(schema_types[table])} column types", file=sys.stderr)

    (out_dir / "schema_types.json").write_text(json.dumps(schema_types, indent=2))
    print(f"Wrote {out_dir}/schema_types.json and per-table samples.", file=sys.stderr)


if __name__ == "__main__":
    main()
