-- GENERATED from policy.yaml by scripts/generate_role_sql.py — do not edit by hand.
-- Least-privilege, read-only role for the Postgres MCP server (schema: centric_8_plm).

CREATE ROLE mcp_readonly LOGIN PASSWORD 'CHANGE_ME' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Start from zero, then grant only what the whitelist needs.
REVOKE ALL ON ALL TABLES IN SCHEMA centric_8_plm FROM mcp_readonly;
REVOKE ALL ON SCHEMA centric_8_plm FROM mcp_readonly;
GRANT USAGE ON SCHEMA centric_8_plm TO mcp_readonly;

ALTER ROLE mcp_readonly SET default_transaction_read_only = on;

-- COLUMN-LEVEL SELECT ONLY. Never add a table-level GRANT SELECT below:
-- it would override these column restrictions and re-expose hidden columns.
GRANT SELECT (_modified_at, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season) ON centric_8_plm.category1s TO mcp_readonly;
GRANT SELECT (_modified_at, category_1, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season) ON centric_8_plm.category2s TO mcp_readonly;
GRANT SELECT (_modified_at, category_1, category_2, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, parent_season, wbs) ON centric_8_plm.collections TO mcp_readonly;
GRANT SELECT (_modified_at, cnt_colorway, cnt_style, code, crew, crew_type, description, id, modified_by, node_name, status) ON centric_8_plm.seasons TO mcp_readonly;
GRANT SELECT (_modified_at, active, actual_size_range, carry_over, category_1, category_2, classifier_3, cnt_colorway, cnt_documents, cnt_order, code, collection, crew, crew_type, default_color, default_size, description, designated_product_source, development_type, fob_calc, fob_negotiated, id, inline, is_template, main_materials, modified_by, node_name, original_season, parent_season, product_type, sample_cost, shape, style_mpv, theme, total_order_volume, total_shipment_qty, wbs) ON centric_8_plm.styles TO mcp_readonly;
