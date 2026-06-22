"""Generate synthetic, referentially-consistent dummy data for the whitelisted PLM
tables as a single portable SQL file.

No real data is used. This emits ``CREATE SCHEMA``/``CREATE TABLE`` for the whitelisted
columns only (read straight from ``policy.yaml``) plus ``INSERT``s of fake rows that
imitate the *shape* of the Centric 8 PLM data — style codes like ``AW-71505-012-319``,
season names like ``2026 FALL/HOLIDAY``, cost fields, boolean flags, HTML descriptions.
The generated reference values are wired together (a style's ``collection`` always names
a real ``collections`` row, etc.) so the query templates return rows.

Load the output on the target VM, then point pg-mcp-server at it:
    uv run python scripts/generate_synthetic_sql.py > scripts/synthetic_load.sql
    psql -U postgres -d mg_dwh -f scripts/synthetic_load.sql

Optionally pass ``--types scripts/sample_data/schema_types.json`` (from ``pull_sample.py``)
so each column's SQL type exactly matches the live source; without it, types are inferred
from the column name (text, except counts/costs/flags).
"""

import argparse
import json
import random
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

import yaml  # noqa: E402 (path set up above)

from models import PolicyDocument  # noqa: E402

# ── Realistic value pools (fashion / apparel PLM vocabulary) ──────────────────
SEASONS = ["2026 SPRING/SUMMER", "2026 FALL/HOLIDAY", "2027 SPRING/SUMMER", "2027 FALL/HOLIDAY"]
CATEGORY1_NAMES = ["WOMENS", "MENS", "KIDS", "ACCESSORIES", "FOOTWEAR", "OUTERWEAR", "DENIM", "HOME"]
CATEGORY2_NAMES = ["TOPS", "BOTTOMS", "DRESSES", "KNITWEAR", "JACKETS", "TEES", "SHORTS", "SKIRTS"]
COLLECTION_NAMES = [
    "ALICE'S ADVENTURES IN WONDERLAND", "THROUGH THE LOOKING GLASS", "PETER PAN",
    "THE WIZARD OF OZ", "TREASURE ISLAND", "MOBY DICK", "THE GREAT GATSBY",
    "LITTLE WOMEN", "ROBINSON CRUSOE", "THE JUNGLE BOOK", "GULLIVER'S TRAVELS",
    "A MIDSUMMER NIGHT'S DREAM", "THE TEMPEST", "DON QUIXOTE", "FRANKENSTEIN", "DRACULA",
]
PRODUCT_TYPES = ["TEES", "HOODIES", "JACKETS", "DRESSES", "TROUSERS", "KNITWEAR", "BAGS", "HOT DRINKS"]
SHAPES = ["REGULAR", "SLIM", "RELAXED", "OVERSIZED", "TAILORED"]
THEMES = ["VINTAGE", "MODERN", "CLASSIC", "STREET", "BOHO"]
DEV_TYPES = ["CORE", "FASHION", "CARRYOVER", "NEWNESS"]
CREW_TYPES = ["DESIGN", "MERCH", "DEVELOPMENT", "SOURCING"]
PEOPLE = ["jordan.lee", "sam.patel", "riley.chen", "alex.morgan", "casey.kim", "dana.ortiz"]
COLORS = ["BLACK", "WHITE", "NAVY", "ECRU", "OLIVE", "BURGUNDY", "STONE", "INDIGO"]
SIZES = ["XS", "S", "M", "L", "XL", "OS"]
MATERIALS = ["100% COTTON", "COTTON/POLY", "WOOL BLEND", "LINEN", "RECYCLED POLYESTER", "ORGANIC COTTON"]
STATUSES = ["OPEN", "ACTIVE", "CLOSED"]

# ── Column-type inference (fallback when --types is not provided) ─────────────
# information_schema-style type strings, emitted verbatim as the CREATE TABLE column type.
BIGINT_COLUMNS = {"cnt_style", "cnt_colorway", "cnt_order", "cnt_documents"}
NUMERIC_COLUMNS = {"fob_calc", "sample_cost", "fob_negotiated", "total_order_volume", "total_shipment_qty"}
BOOLEAN_COLUMNS = {"active", "inline", "carry_over", "is_template"}


def inferred_type(column: str) -> str:
    """Best-guess Postgres type for a column when no live types were captured."""
    if column in BIGINT_COLUMNS:
        return "bigint"
    if column in NUMERIC_COLUMNS:
        return "numeric"
    if column in BOOLEAN_COLUMNS:
        return "boolean"
    return "text"


def value_family(pg_type: str) -> str:
    """Group a Postgres type into how its literal must be rendered in SQL."""
    t = pg_type.lower()
    if "bool" in t:
        return "bool"
    if any(k in t for k in ("int", "serial")):
        return "int"
    if any(k in t for k in ("numeric", "decimal", "real", "double", "money")):
        return "num"
    return "text"


def sql_literal(value: object, pg_type: str) -> str:
    """Render a Python value as a SQL literal for the given column type."""
    if value is None:
        return "NULL"
    family = value_family(pg_type)
    if family == "bool":
        return "TRUE" if value else "FALSE"
    if family in ("int", "num"):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"  # text: escape single quotes


# ── Synthetic value helpers (each encodes one real-world value shape) ─────────
def iso_timestamp(rng: random.Random) -> str:
    """An ISO-8601 string, mirroring the source where _modified_at is stored as varchar."""
    month, day, hour, minute = rng.randint(1, 12), rng.randint(1, 28), rng.randint(0, 23), rng.randint(0, 59)
    return f"2026-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00"


def html_description(rng: random.Random, text: str) -> str:
    """An HTML-wrapped description, mirroring the source's rich-text description fields."""
    size = rng.choice([8, 10, 12])
    return f'<p><span style="font-size:{size}px;">{text}</span></p>'


def style_code(rng: random.Random) -> str:
    """A style code shaped like 'AW-71505-012-319'."""
    prefix = rng.choice(["AW", "SS", "FW", "HO"])
    return f"{prefix}-{rng.randint(10000, 99999)}-{rng.randint(0, 999):03d}-{rng.randint(0, 999):03d}"


# ── Row builders (one per table; every whitelisted column is populated) ───────
def build_seasons(rng: random.Random) -> list[dict]:
    rows = []
    for i, name in enumerate(SEASONS, start=1):
        rows.append({
            "id": f"SEASON-{i:03d}", "code": name, "node_name": name,
            "description": html_description(rng, f"Season {name}"), "status": rng.choice(STATUSES),
            "crew": rng.choice(PEOPLE), "crew_type": rng.choice(CREW_TYPES),
            "cnt_style": rng.randint(20, 400), "cnt_colorway": rng.randint(40, 1200),
            "modified_by": rng.choice(PEOPLE), "_modified_at": iso_timestamp(rng),
        })
    return rows


def build_category1s(rng: random.Random, n: int, seasons: list[dict]) -> list[dict]:
    rows = []
    for i, name in enumerate(rng.sample(CATEGORY1_NAMES, k=min(n, len(CATEGORY1_NAMES))), start=1):
        rows.append({
            "id": f"CAT1-{i:03d}", "code": name, "node_name": name,
            "description": html_description(rng, f"Category 1 {name}"),
            "crew": rng.choice(PEOPLE), "crew_type": rng.choice(CREW_TYPES),
            "cnt_style": rng.randint(10, 200), "cnt_colorway": rng.randint(20, 600),
            "parent_season": rng.choice(seasons)["code"],
            "modified_by": rng.choice(PEOPLE), "_modified_at": iso_timestamp(rng),
        })
    return rows


def build_category2s(rng: random.Random, n: int, seasons: list[dict], category1s: list[dict]) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        rows.append({
            "id": f"CAT2-{i:03d}", "code": (name := rng.choice(CATEGORY2_NAMES)), "node_name": name,
            "description": html_description(rng, f"Category 2 {name}"),
            "category_1": rng.choice(category1s)["code"],
            "crew": rng.choice(PEOPLE), "crew_type": rng.choice(CREW_TYPES),
            "cnt_style": rng.randint(5, 120), "cnt_colorway": rng.randint(10, 300),
            "parent_season": rng.choice(seasons)["code"],
            "modified_by": rng.choice(PEOPLE), "_modified_at": iso_timestamp(rng),
        })
    return rows


def build_collections(
    rng: random.Random, n: int, seasons: list[dict], category1s: list[dict], category2s: list[dict]
) -> list[dict]:
    rows = []
    for i, name in enumerate(rng.sample(COLLECTION_NAMES, k=min(n, len(COLLECTION_NAMES))), start=1):
        rows.append({
            "id": f"COLL-{i:03d}", "wbs": f"WBS-{rng.randint(1000, 9999)}", "code": name, "node_name": name,
            "description": html_description(rng, f"Collection {name}"),
            "category_1": rng.choice(category1s)["code"], "category_2": rng.choice(category2s)["code"],
            "crew": rng.choice(PEOPLE), "crew_type": rng.choice(CREW_TYPES),
            "cnt_style": rng.randint(5, 80), "cnt_colorway": rng.randint(10, 240),
            "parent_season": rng.choice(seasons)["code"],
            "modified_by": rng.choice(PEOPLE), "_modified_at": iso_timestamp(rng),
        })
    return rows


def build_styles(
    rng: random.Random, n: int, seasons: list[dict], category1s: list[dict],
    category2s: list[dict], collections: list[dict]
) -> list[dict]:
    rows = []
    for i in range(1, n + 1):
        season = rng.choice(seasons)["code"]
        cost = round(rng.uniform(4.0, 85.0), 2)
        rows.append({
            "id": f"STYLE-{i:05d}", "code": style_code(rng), "wbs": f"WBS-{rng.randint(1000, 9999)}",
            "node_name": f"{rng.choice(PRODUCT_TYPES)} {rng.randint(100, 999)}",
            "description": html_description(rng, f"Product style {i}"),
            "style_mpv": f"MPV-{rng.randint(10000, 99999)}",
            "category_1": rng.choice(category1s)["code"], "category_2": rng.choice(category2s)["code"],
            "collection": rng.choice(collections)["code"], "parent_season": season, "original_season": season,
            "product_type": rng.choice(PRODUCT_TYPES), "development_type": rng.choice(DEV_TYPES),
            "shape": rng.choice(SHAPES), "theme": rng.choice(THEMES),
            "active": rng.random() < 0.8, "inline": rng.random() < 0.6,
            "carry_over": rng.random() < 0.3, "is_template": rng.random() < 0.05,
            "default_color": rng.choice(COLORS), "default_size": rng.choice(SIZES),
            "actual_size_range": f"{rng.choice(SIZES)}-{rng.choice(SIZES)}",
            "main_materials": rng.choice(MATERIALS),
            "crew": rng.choice(PEOPLE), "crew_type": rng.choice(CREW_TYPES),
            "classifier_3": rng.choice(["A", "B", "C"]),
            "designated_product_source": rng.choice(["VENDOR-A", "VENDOR-B", "VENDOR-C"]),
            "cnt_order": rng.randint(0, 25), "cnt_colorway": rng.randint(1, 12),
            "cnt_documents": rng.randint(0, 40),
            "fob_calc": cost, "sample_cost": round(cost * rng.uniform(1.1, 1.4), 2),
            "fob_negotiated": round(cost * rng.uniform(0.85, 1.0), 2),
            "total_order_volume": rng.randint(0, 50000), "total_shipment_qty": rng.randint(0, 50000),
            "modified_by": rng.choice(PEOPLE), "_modified_at": iso_timestamp(rng),
        })
    return rows


def emit_table_sql(schema: str, table: str, columns: list[str], rows: list[dict], types: dict[str, str]) -> str:
    """Render DROP/CREATE TABLE (whitelisted columns only) + chunked INSERTs for one table."""
    column_defs = ",\n    ".join(f'"{col}" {types[col]}' for col in columns)
    out = [
        f"DROP TABLE IF EXISTS {schema}.{table} CASCADE;",
        f"CREATE TABLE {schema}.{table} (\n    {column_defs}\n);",
    ]
    column_list = ", ".join(f'"{col}"' for col in columns)
    for start in range(0, len(rows), 100):  # chunk INSERTs so no single statement is huge
        chunk = rows[start:start + 100]
        values = ",\n    ".join(
            "(" + ", ".join(sql_literal(row[col], types[col]) for col in columns) + ")" for row in chunk
        )
        out.append(f"INSERT INTO {schema}.{table} ({column_list}) VALUES\n    {values};")
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic PLM data as portable SQL (stdout).")
    parser.add_argument("--policy", default=str(_PROJECT_ROOT / "policy.yaml"), help="Path to policy.yaml")
    parser.add_argument("--types", help="Optional schema_types.json from pull_sample.py for exact column types")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible output")
    parser.add_argument("--styles", type=int, default=200, help="Number of style rows")
    parser.add_argument("--category2s", type=int, default=24, help="Number of category2 rows")
    parser.add_argument("--collections", type=int, default=16, help="Number of collection rows")
    parser.add_argument("--category1s", type=int, default=8, help="Number of category1 rows")
    args = parser.parse_args()

    doc = PolicyDocument.model_validate(yaml.safe_load(Path(args.policy).read_text(encoding="utf-8")))
    captured: dict[str, dict[str, str]] = json.loads(Path(args.types).read_text()) if args.types else {}

    rng = random.Random(args.seed)
    seasons = build_seasons(rng)
    category1s = build_category1s(rng, args.category1s, seasons)
    category2s = build_category2s(rng, args.category2s, seasons, category1s)
    collections = build_collections(rng, args.collections, seasons, category1s, category2s)
    styles = build_styles(rng, args.styles, seasons, category1s, category2s, collections)
    generated = {
        "seasons": seasons, "category1s": category1s, "category2s": category2s,
        "collections": collections, "styles": styles,
    }

    print("-- GENERATED synthetic PLM data — see scripts/generate_synthetic_sql.py. No real data.")
    print(f"CREATE SCHEMA IF NOT EXISTS {doc.db_schema};\n")
    # Emit in the policy's declared table order so output is stable and reviewable.
    for table in doc.tables:
        columns = doc.tables[table].columns
        types = {col: captured.get(table, {}).get(col) or inferred_type(col) for col in columns}
        print(emit_table_sql(doc.db_schema, table, columns, generated[table], types))

    summary = ", ".join(f"{name}={len(rows)}" for name, rows in generated.items())
    print(f"Generated rows: {summary}", file=sys.stderr)
    print(f"Sample style codes to test get_style_by_code: {[s['code'] for s in styles[:3]]}", file=sys.stderr)
    print(f"Sample collections to test list_styles_in_collection: {COLLECTION_NAMES[:2]}", file=sys.stderr)


if __name__ == "__main__":
    main()
