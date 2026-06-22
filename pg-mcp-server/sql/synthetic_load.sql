-- ============================================================================
-- synthetic_load.sql — SELF-CONTAINED synthetic test fixture for pg-mcp-server.
--
-- ONE file to stand up the interim, no-auth test on the Several Millers VM:
-- it creates the read-only login role the server uses, the `centric_8_plm`
-- schema, the FIVE whitelisted tables, ~200 rows of synthetic data, and the
-- column-scoped grants — all in a single transaction.
--
-- EVERY value here is invented. There is no real PLM data in this file, so it
-- is safe to share/commit.
--
-- Run it on the VM as the postgres superuser, connected to the target DB:
--     sudo -u postgres createdb mg_dwh                                 # once
--     sudo -u postgres psql -d mg_dwh -v ON_ERROR_STOP=1 -f synthetic_load.sql
--
--   >>> BEFORE running: set a real password on line `PASSWORD 'CHANGE_ME'`
--       below, and use the SAME value in the server's .env PGMCP_DATABASE_URL
--       (postgresql://mcp_readonly:<pw>@127.0.0.1:5432/mg_dwh). <<<
--
-- Idempotent / re-runnable: it DROPs and recreates the schema and reapplies all
-- grants every run; the role is created only if it doesn't already exist (so a
-- reload never errors and never drops a role the server may be connected as).
-- NOTE: because the role is only created-if-absent, changing the password later
-- means an explicit `ALTER ROLE mcp_readonly PASSWORD '...';`, not a reload.
--
-- Only the whitelisted columns from policy.yaml are created. The server's
-- startup check (access_policy.validate_against_db) is NAME-ONLY: it verifies
-- each whitelisted table/column exists, never the type. Types below mirror prod
-- for the describe_table tool's sake (varchar / bigint / numeric / boolean).
-- `_modified_at` is kept as a varchar ISO-8601 string — the one type that
-- affects behaviour, so `ORDER BY _modified_at DESC` sorts chronologically
-- (lexicographically) exactly like the live DB.
--
-- Referential wiring (no FKs in prod either — refs carry the parent's
-- human-readable node_name): seasons -> category1s -> category2s ->
-- collections -> styles. Counts: 4 seasons, 4 cat1, 6 cat2, 8 collections,
-- 200 styles (25 per collection).
--
-- Known-good values for a smoke test:
--   * get_style_by_code         -> code = 'AW-71001-001-001'  (style g=1)
--   * list_styles_in_collection -> collection = 'ALICE''S ADVENTURES IN WONDERLAND'
--                                  (collection COL-01, has 25 styles)
-- ============================================================================

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Read-only login role the MCP server connects as (least-privilege backstop to
-- the app-layer whitelist). Mirrors scripts/generate_role_sql.py output.
-- Created only if absent so reloads don't error; grants are (re)applied below.
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mcp_readonly') THEN
        CREATE ROLE mcp_readonly LOGIN PASSWORD 'CHANGE_ME' NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END $$;

ALTER ROLE mcp_readonly SET default_transaction_read_only = on;

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema + tables (whitelisted columns only; see policy.yaml)
-- ─────────────────────────────────────────────────────────────────────────────

DROP SCHEMA IF EXISTS centric_8_plm CASCADE;
CREATE SCHEMA centric_8_plm;

CREATE TABLE centric_8_plm.seasons (
    id            varchar,
    code          varchar,
    node_name     varchar,
    description   varchar,
    status        varchar,
    crew          varchar,
    crew_type     varchar,
    cnt_style     bigint,
    cnt_colorway  bigint,
    modified_by   varchar,
    _modified_at  varchar
);

CREATE TABLE centric_8_plm.category1s (
    id            varchar,
    code          varchar,
    node_name     varchar,
    description   varchar,
    crew          varchar,
    crew_type     varchar,
    cnt_style     bigint,
    cnt_colorway  bigint,
    parent_season varchar,
    modified_by   varchar,
    _modified_at  varchar
);

CREATE TABLE centric_8_plm.category2s (
    id            varchar,
    code          varchar,
    node_name     varchar,
    description   varchar,
    category_1    varchar,
    crew          varchar,
    crew_type     varchar,
    cnt_style     bigint,
    cnt_colorway  bigint,
    parent_season varchar,
    modified_by   varchar,
    _modified_at  varchar
);

CREATE TABLE centric_8_plm.collections (
    id            varchar,
    wbs           varchar,
    code          varchar,
    node_name     varchar,
    description   varchar,
    category_1    varchar,
    category_2    varchar,
    crew          varchar,
    crew_type     varchar,
    cnt_style     bigint,
    cnt_colorway  bigint,
    parent_season varchar,
    modified_by   varchar,
    _modified_at  varchar
);

CREATE TABLE centric_8_plm.styles (
    id                        varchar,
    code                      varchar,
    wbs                       varchar,
    node_name                 varchar,
    description               varchar,
    style_mpv                 varchar,
    category_1                varchar,
    category_2                varchar,
    collection                varchar,
    parent_season             varchar,
    original_season           varchar,
    product_type              varchar,
    development_type          varchar,
    shape                     varchar,
    theme                     varchar,
    active                    boolean,
    inline                    boolean,
    carry_over                boolean,
    is_template               boolean,
    default_color             varchar,
    default_size              varchar,
    actual_size_range         varchar,
    main_materials            varchar,
    crew                      varchar,
    crew_type                 varchar,
    classifier_3              varchar,
    designated_product_source varchar,
    cnt_order                 bigint,
    cnt_colorway              bigint,
    cnt_documents             bigint,
    fob_calc                  numeric,
    sample_cost               numeric,
    fob_negotiated            numeric,
    total_order_volume        numeric,
    total_shipment_qty        numeric,
    modified_by               varchar,
    _modified_at              varchar
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Parent rows (small + explicit). node_name is the value children reference.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO centric_8_plm.seasons
    (id, code, node_name, description, status, crew, crew_type, cnt_style, cnt_colorway, modified_by, _modified_at)
VALUES
    ('SEA-01', '26SS', '2026 SPRING/SUMMER', '<p>Synthetic season.</p>', 'ACTIVE', 'MENS',   'SEASONAL', 120, 340, 'synthetic_loader', '2026-01-15T09:00:00.000Z'),
    ('SEA-02', '26FH', '2026 FALL/HOLIDAY',  '<p>Synthetic season.</p>', 'ACTIVE', 'WOMENS', 'SEASONAL',  98, 275, 'synthetic_loader', '2026-02-10T09:00:00.000Z'),
    ('SEA-03', '27SS', '2027 SPRING/SUMMER', '<p>Synthetic season.</p>', 'DRAFT',  'UNISEX', 'CORE',      64, 150, 'synthetic_loader', '2026-03-05T09:00:00.000Z'),
    ('SEA-04', '27FH', '2027 FALL/HOLIDAY',  '<p>Synthetic season.</p>', 'DRAFT',  'MENS',   'SEASONAL',  40,  90, 'synthetic_loader', '2026-04-01T09:00:00.000Z');

INSERT INTO centric_8_plm.category1s
    (id, code, node_name, description, crew, crew_type, cnt_style, cnt_colorway, parent_season, modified_by, _modified_at)
VALUES
    ('CAT1-01', 'C1-APP', 'APPAREL',     '<p>Synthetic category.</p>', 'MENS',   'SEASONAL', 80, 200, '2026 FALL/HOLIDAY',  'synthetic_loader', '2026-02-12T10:00:00.000Z'),
    ('CAT1-02', 'C1-ACC', 'ACCESSORIES', '<p>Synthetic category.</p>', 'WOMENS', 'SEASONAL', 50, 130, '2026 SPRING/SUMMER', 'synthetic_loader', '2026-02-12T10:00:00.000Z'),
    ('CAT1-03', 'C1-FTW', 'FOOTWEAR',    '<p>Synthetic category.</p>', 'UNISEX', 'CORE',     30,  75, '2027 SPRING/SUMMER', 'synthetic_loader', '2026-02-12T10:00:00.000Z'),
    ('CAT1-04', 'C1-HOM', 'HOME',        '<p>Synthetic category.</p>', 'UNISEX', 'CORE',     20,  45, '2027 FALL/HOLIDAY',  'synthetic_loader', '2026-02-12T10:00:00.000Z');

INSERT INTO centric_8_plm.category2s
    (id, code, node_name, description, category_1, crew, crew_type, cnt_style, cnt_colorway, parent_season, modified_by, _modified_at)
VALUES
    ('CAT2-01', 'C2-TOP', 'TOPS',      '<p>Synthetic sub-category.</p>', 'APPAREL',     'MENS',   'SEASONAL', 45, 120, '2026 FALL/HOLIDAY',  'synthetic_loader', '2026-02-14T10:00:00.000Z'),
    ('CAT2-02', 'C2-BOT', 'BOTTOMS',   '<p>Synthetic sub-category.</p>', 'APPAREL',     'WOMENS', 'SEASONAL', 35,  80, '2026 FALL/HOLIDAY',  'synthetic_loader', '2026-02-14T10:00:00.000Z'),
    ('CAT2-03', 'C2-OUT', 'OUTERWEAR', '<p>Synthetic sub-category.</p>', 'APPAREL',     'UNISEX', 'SEASONAL', 25,  60, '2026 SPRING/SUMMER', 'synthetic_loader', '2026-02-14T10:00:00.000Z'),
    ('CAT2-04', 'C2-BAG', 'BAGS',      '<p>Synthetic sub-category.</p>', 'ACCESSORIES', 'WOMENS', 'CORE',     20,  50, '2026 SPRING/SUMMER', 'synthetic_loader', '2026-02-14T10:00:00.000Z'),
    ('CAT2-05', 'C2-HAT', 'HATS',      '<p>Synthetic sub-category.</p>', 'ACCESSORIES', 'UNISEX', 'CORE',     15,  30, '2027 SPRING/SUMMER', 'synthetic_loader', '2026-02-14T10:00:00.000Z'),
    ('CAT2-06', 'C2-DRK', 'DRINKWARE', '<p>Synthetic sub-category.</p>', 'HOME',        'UNISEX', 'CORE',     10,  20, '2027 FALL/HOLIDAY',  'synthetic_loader', '2026-02-14T10:00:00.000Z');

INSERT INTO centric_8_plm.collections
    (id, wbs, code, node_name, description, category_1, category_2, crew, crew_type, cnt_style, cnt_colorway, parent_season, modified_by, _modified_at)
VALUES
    ('COL-01', 'WBS-C-01', 'COL001', 'ALICE''S ADVENTURES IN WONDERLAND', '<p>Synthetic collection.</p>', 'APPAREL',     'TOPS',      'WOMENS', 'SEASONAL', 25, 70, '2026 FALL/HOLIDAY',  'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-02', 'WBS-C-02', 'COL002', 'MIDNIGHT GARDEN',                   '<p>Synthetic collection.</p>', 'APPAREL',     'BOTTOMS',   'WOMENS', 'SEASONAL', 25, 65, '2026 FALL/HOLIDAY',  'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-03', 'WBS-C-03', 'COL003', 'URBAN SAFARI',                      '<p>Synthetic collection.</p>', 'APPAREL',     'OUTERWEAR', 'MENS',   'SEASONAL', 25, 60, '2026 SPRING/SUMMER', 'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-04', 'WBS-C-04', 'COL004', 'COASTAL BREEZE',                    '<p>Synthetic collection.</p>', 'ACCESSORIES', 'BAGS',      'WOMENS', 'CORE',     25, 55, '2026 SPRING/SUMMER', 'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-05', 'WBS-C-05', 'COL005', 'NEON NIGHTS',                       '<p>Synthetic collection.</p>', 'ACCESSORIES', 'HATS',      'UNISEX', 'CORE',     25, 50, '2027 SPRING/SUMMER', 'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-06', 'WBS-C-06', 'COL006', 'HERITAGE CRAFT',                    '<p>Synthetic collection.</p>', 'HOME',        'DRINKWARE', 'UNISEX', 'CORE',     25, 45, '2027 FALL/HOLIDAY',  'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-07', 'WBS-C-07', 'COL007', 'ARCTIC EXPEDITION',                 '<p>Synthetic collection.</p>', 'APPAREL',     'OUTERWEAR', 'MENS',   'SEASONAL', 25, 40, '2027 SPRING/SUMMER', 'synthetic_loader', '2026-03-01T11:00:00.000Z'),
    ('COL-08', 'WBS-C-08', 'COL008', 'BOTANICAL DREAMS',                  '<p>Synthetic collection.</p>', 'HOME',        'DRINKWARE', 'WOMENS', 'CORE',     25, 35, '2027 FALL/HOLIDAY',  'synthetic_loader', '2026-03-01T11:00:00.000Z');

-- ─────────────────────────────────────────────────────────────────────────────
-- Styles (200 rows). Generated with generate_series; each reference column is
-- pulled FROM the parent table by a deterministic modulo, so every value is
-- guaranteed to point at a real parent row.
-- ─────────────────────────────────────────────────────────────────────────────

INSERT INTO centric_8_plm.styles
    (id, code, wbs, node_name, description, style_mpv,
     category_1, category_2, collection, parent_season, original_season,
     product_type, development_type, shape, theme,
     active, inline, carry_over, is_template,
     default_color, default_size, actual_size_range, main_materials,
     crew, crew_type, classifier_3, designated_product_source,
     cnt_order, cnt_colorway, cnt_documents,
     fob_calc, sample_cost, fob_negotiated, total_order_volume, total_shipment_qty,
     modified_by, _modified_at)
SELECT
    'STY-' || lpad(g::text, 5, '0'),
    format('AW-%s-%s-%s', lpad((71000 + g)::text, 5, '0'), lpad((g % 1000)::text, 3, '0'), lpad((g % 500)::text, 3, '0')),
    'WBS-' || lpad(g::text, 5, '0'),
    'Synthetic Style ' || g,
    '<p><span style="font-size:8px;">Synthetic style ' || g || ' — placeholder description for testing.</span></p>',
    'MPV-' || lpad(g::text, 5, '0'),
    (SELECT node_name FROM centric_8_plm.category1s  WHERE id = 'CAT1-' || lpad((1 + g % 4)::text, 2, '0')),
    (SELECT node_name FROM centric_8_plm.category2s  WHERE id = 'CAT2-' || lpad((1 + g % 6)::text, 2, '0')),
    (SELECT node_name FROM centric_8_plm.collections WHERE id = 'COL-'  || lpad((1 + g % 8)::text, 2, '0')),
    (SELECT node_name FROM centric_8_plm.seasons     WHERE id = 'SEA-'  || lpad((1 + g % 4)::text, 2, '0')),
    (SELECT node_name FROM centric_8_plm.seasons     WHERE id = 'SEA-'  || lpad((1 + (g + 2) % 4)::text, 2, '0')),
    (ARRAY['HOT DRINKS', 'COLD DRINKS', 'OUTERWEAR', 'KNITWEAR', 'ACCESSORIES'])[1 + g % 5],
    (ARRAY['CORE', 'FASHION', 'CARRYOVER'])[1 + g % 3],
    (ARRAY['REGULAR', 'SLIM', 'OVERSIZED'])[1 + g % 3],
    (ARRAY['CLASSIC', 'SEASONAL', 'LIMITED'])[1 + g % 3],
    (g % 5 <> 0),
    (g % 2 = 0),
    (g % 4 = 0),
    (g % 40 = 0),
    (ARRAY['BLACK', 'WHITE', 'NAVY', 'OLIVE', 'BURGUNDY'])[1 + g % 5],
    (ARRAY['S', 'M', 'L', 'XL'])[1 + g % 4],
    'XS-XXL',
    (ARRAY['Cotton 100%', 'Polyester 100%', 'Wool blend', 'Ceramic', 'Stainless steel'])[1 + g % 5],
    (ARRAY['MENS', 'WOMENS', 'UNISEX'])[1 + g % 3],
    (ARRAY['SEASONAL', 'CORE'])[1 + g % 2],
    'CLS-' || lpad((g % 20)::text, 2, '0'),
    (ARRAY['Vendor A', 'Vendor B', 'Vendor C'])[1 + g % 3],
    (g % 15),
    (1 + g % 6),
    (g % 4),
    round((10 + g % 90 + 0.50)::numeric, 2),
    round((15 + g % 120 + 0.25)::numeric, 2),
    round((9 + g % 85 + 0.75)::numeric, 2),
    (100 + (g * 7) % 5000),
    (50 + (g * 5) % 4000),
    'synthetic_loader',
    to_char(timestamp '2026-06-21 12:00:00' - (g || ' hours')::interval, 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"')
FROM generate_series(1, 200) AS g;

-- Mirror prod: btree indexes on id and _modified_at for the main entity.
CREATE INDEX ON centric_8_plm.styles (id);
CREATE INDEX ON centric_8_plm.styles (_modified_at);

-- ─────────────────────────────────────────────────────────────────────────────
-- Least-privilege grants for mcp_readonly: COLUMN-LEVEL SELECT ONLY on the
-- whitelisted columns. Never add a table-level GRANT SELECT — it would override
-- these column restrictions and re-expose hidden columns. Mirrors role_setup.sql.
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE ALL ON ALL TABLES IN SCHEMA centric_8_plm FROM mcp_readonly;
REVOKE ALL ON SCHEMA centric_8_plm FROM mcp_readonly;
GRANT USAGE ON SCHEMA centric_8_plm TO mcp_readonly;

GRANT SELECT (_modified_at, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season) ON centric_8_plm.category1s TO mcp_readonly;
GRANT SELECT (_modified_at, category_1, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season) ON centric_8_plm.category2s TO mcp_readonly;
GRANT SELECT (_modified_at, category_1, category_2, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season, wbs) ON centric_8_plm.collections TO mcp_readonly;
GRANT SELECT (_modified_at, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, status) ON centric_8_plm.seasons TO mcp_readonly;
GRANT SELECT (_modified_at, active, actual_size_range, carry_over, category_1, category_2, classifier_3, cnt_colorway, cnt_documents, cnt_order, code, collection, crew, crew_type, default_color, default_size, description, designated_product_source, development_type, fob_calc, fob_negotiated, id, inline, is_template, main_materials, modified_by, node_name, original_season, parent_season, product_type, sample_cost, shape, style_mpv, theme, total_order_volume, total_shipment_qty, wbs) ON centric_8_plm.styles TO mcp_readonly;

COMMIT;
