# Database Schema — `centric_8_plm` (Centric 8 PLM)

**Source:** Thoughtfully live PostgreSQL, accessed **read-only**. Data is synced from Centric 8 PLM via **Airbyte** into schema `centric_8_plm`. DDL captured 2026-06-17 (first 5 tables).

> This is reference material for building the whitelist. The authoritative whitelist is `pg-mcp-server/policy.yaml`. No row data is stored here.

## Tables (first batch)

| Table | Grain | Key | Reference columns (carry parent code/name) |
|-------|-------|-----|---------------------------------------------|
| `category1s` | Top category node | `id` (varchar) | `parent_season` |
| `category2s` | Sub-category node | `id` | `category_1`, `parent_season` |
| `collections` | Collection node | `id` | `category_1`, `category_2`, `parent_season` |
| `seasons` | Season | `id` | — |
| `styles` | Product style (the main entity, ~250 cols) | `id` | `category_1`, `category_2`, `collection`, `parent_season`, `original_season` |

Inferred hierarchy: `seasons` → `category1s` → `category2s` → `collections` → `styles`.
There are **no declared PK/FK constraints** (only btree indexes on `id`, `_modified_at`, `_airbyte_extracted_at`); relationships are carried in plain `varchar` columns holding the parent's **code/name** (confirmed by sample data, e.g. `parent_season = "2026 FALL/HOLIDAY"`).

## Column-handling rules

- **Excluded everywhere — Airbyte metadata:** `_airbyte_raw_id`, `_airbyte_extracted_at`, `_airbyte_meta`, `_airbyte_generation_id`, `_airbyte_deleted`, `_airbyte_delete_candidate`.
- **Excluded everywhere — all `jsonb` columns** (nested structures: `_links`, `issues`, `hierarchy`, all `mgf_*`, all `qa_*`, `printing_method`, etc.). Revisit individually if a specific one is needed.
- **Exposed — scalar identity / classification / count columns** (`varchar`/`int8`/`numeric`/`bool`). See `policy.yaml` for the exact per-table lists.
- **Sensitive cost/volume fields (`styles`): EXPOSED per user decision (2026-06-17)** — `fob_calc`, `sample_cost`, `fob_negotiated`, `total_order_volume`, `total_shipment_qty`. (Most other financials — margins, wholesale, forecasts — live in the excluded `jsonb` columns.)

## Data-shape notes

- `styles.description` contains **HTML markup** (e.g. `<p><span style="font-size:8px;">…</span></p>`). Returned raw to the model; consider tag-stripping later for cleaner output.
- Reference columns hold **human-readable codes/names**, so templates/filters can use friendly values (e.g. collection = `ALICE'S ADVENTURES IN WONDERLAND`, `product_type` = `HOT DRINKS`).
- `_modified_at` is stored as **`varchar`** (ISO-8601 string), not `timestamptz`.

## Design implications for the server

- Queries are **schema-qualified** (`centric_8_plm.styles`, …); the config, AST validator, and least-privilege GRANTs must all be **schema-aware** (not `public`).

## Open items to confirm at build time

- Exact join keys: whether `styles.category_1` / `category_2` / `collection` / `parent_season` match the parent's `code` vs `node_name` vs `id` — resolve via schema introspection + a sampled join during Task 6/12.
