# 001 Postgres MCP Server (ChatGPT Enterprise Connector)

**Status:** draft
**Created:** 2026-06-17
**Last updated:** 2026-06-17

---

## 1. Overview

A custom Python MCP (Model Context Protocol) server that lets AI agents query a PostgreSQL database **safely**, exposing only an explicit whitelist of tables and columns so sensitive fields (password hashes, PII) are never reachable or even visible in the advertised schema. It supports two query paths — a **primary constrained open-query mode** plus a small curated set of pre-defined **parameterized templates** — both rigorously bound by the whitelist. The server is deployed as a **remote HTTPS connector** registered in **ChatGPT Enterprise**, so business users see query results as chat output. Built in Python with `uv`, hosted (not stdio).

## 2. Requirements

- WHEN the server starts, THEN it loads an access policy (whitelisted tables → allowed columns, plus query templates) and validates it against the live DB schema, failing fast if a whitelisted table/column does not exist.
- WHEN a client requests the schema (`list_accessible_tables` / `describe_table`), THEN only whitelisted tables and columns are returned — non-whitelisted tables and sensitive columns never appear.
- WHEN a client runs a **template** (e.g. `get_user_profile`), THEN the server executes a pre-defined parameterized query with bound parameters only (no SQL text supplied by the client).
- WHEN a client uses **open-query mode**, THEN the SQL is parsed to an AST and rejected unless it is a single read-only `SELECT` that references only whitelisted tables and columns (no `SELECT *`, no stacked statements, no DML/DDL).
- WHEN any query references a table or column outside the whitelist, THEN it is rejected with a clear error **before** touching the database.
- WHEN any query executes, THEN it runs as a least-privilege, **read-only** role inside a read-only transaction, with an enforced `statement_timeout` and a clamped row `LIMIT`.
- WHEN ChatGPT Enterprise connects, THEN the server is reachable over **public HTTPS via Streamable HTTP** and authenticates the caller (auth model — see `DECISION NEEDED` D1).

### Out of Scope

- Write/INSERT/UPDATE/DELETE access of any kind (read-only only).
- Apps SDK custom inline UI widget (rich rendered tables in chat) — v1 returns text/Markdown + structured JSON; widget is a future spec.
- Deep Research mode support (`search`/`fetch` tools) — v1 targets Developer-Mode connector tools; future spec if needed.
- Multi-database / cross-DB joins, query result caching, and write-back of audit logs to the target DB.
- Production hosting/IaC hardening beyond a deployable container + `deploy.py` skeleton (covered by a follow-on deploy spec).

## 3. Design

> **D1 (Auth) — DECIDED:** **OAuth 2.1 (Auth Code + PKCE)** with **Microsoft Entra ID** as the authorization server. (ChatGPT does not support static API keys; no-auth was the alternative but rejected given DB access.)
> **D2 (Open-query interface) — DECIDED:** accept a raw `SELECT` validated by **pglast AST** (max flexibility, matches "open query format"); the column-level read-only DB role is the real backstop behind the parser. This is the **primary** query path.
> **D3 (Templates surface) — DECIDED:** **dynamically generate one typed MCP tool per template**. Open-query mode (D2) is the **primary** path; templates are a **small curated set** of blessed queries, so per-template tools give the best ergonomics/safety with no tool-list bloat.
> **D4 (Hosting & connectivity) — DECIDED:** Host the HTTPS server on **Azure Container Apps** (managed public HTTPS ingress, scale-to-zero) with secrets in **Azure Key Vault**. The Container Apps environment is **VNet-integrated** into the Postgres VM's VNet; an NSG rule allows the app subnet to reach the VM on **5432**. Target DB is **self-hosted PostgreSQL on the VM** with standard role/password auth; enforce `sslmode=require` if SSL is configured on the VM.

### Architecture (3-layer)

Tools (Layer 1, in `main.py`) are thin boundaries that delegate to the core classes; all whitelist enforcement lives in Layer 2.

| Layer | File | Change |
|-------|------|--------|
| Entry point | `main.py` | Build `FastMCP`, register MCP tools (`list_accessible_tables`, `describe_table`, template tool(s), `query`), wire auth, launch Streamable HTTP via ASGI/uvicorn |
| Core logic | `access_policy.py` | `AccessPolicy`: load `policy.yaml`, validate vs live schema, allowlist checks for table/column identifiers, build filtered schema |
| Core logic | `database.py` | `Database`: `psycopg` `AsyncConnectionPool`, read-only execution helper, `information_schema` introspection |
| Core logic | `query_validator.py` | `validate_select()`: pglast AST walk — single read-only SELECT, allowlisted tables/cols, no `*`, no stacked stmts, clamp LIMIT |
| Helpers | `config.py` | `pydantic-settings` `Settings` (DB conninfo, policy path, OAuth settings, host/port, timeouts) + `get_settings()` |
| Helpers | `auth.py` | OAuth 2.1 `TokenVerifier` + `AuthSettings` wiring for FastMCP (per D1) |
| Helpers | `models.py` | Pydantic v2 models: `TablePolicy`, `QueryTemplate`, `QueryResult` |
| Helpers | `logging_config.py` | `get_logger()` per foundation logging guidelines |
| Config/data | `policy.yaml` | Whitelist (tables→columns) + templates; sensitive columns simply omitted |
| Deploy | `deploy.py` | Deployment skeleton (per D4) |
| Tests | `tests/test_access_policy.py`, `test_query_validator.py`, `test_database.py`, `test_tools.py`, `conftest.py` | Unit + integration tests |

### Key Decisions

- **Build custom (not Google MCP Toolbox):** user requires a Python server deployable as a ChatGPT Enterprise connector with strict **field-level** whitelisting; whether Toolbox covers column-level filtering is evaluated as the final task (Task 13), not as the foundation.
- **FastMCP 3.x** (`uv add fastmcp`): lowest-boilerplate, actively maintained, wraps the official `mcp` package. Streamable HTTP at `/mcp/`. (Ref: `mcp_python_sdk.md`.)
- **psycopg 3 async + `AsyncConnectionPool`:** built-in `sql.Identifier` composition is essential for safe dynamic identifiers; LLM latency dominates so asyncpg's speed edge is irrelevant. (Ref: `postgres_python_safe_querying.md`.)
- **Defense in depth, DB role is the backstop:** (1) allowlist validation before composing SQL, (2) column-level `SELECT`-only least-priv role, (3) `default_transaction_read_only` + per-query read-only transaction. `READ ONLY` alone is not sufficient per PG docs — the role is authoritative.
- **pglast for open-query AST validation** (Postgres's own grammar) over regex; quoting is not validation.
- **Sensitive columns filtered at every layer:** absent from `policy.yaml`, excluded from GRANTs, and never in the advertised schema — they cannot reach the model.
- **Azure deployment target:** host on **Azure Container Apps** (VNet-integrated) with **Azure Key Vault** for secrets; target DB is **self-hosted PostgreSQL on a VM** reached over the **private VNet** (NSG allow 5432 from the app subnet). Standard Postgres role/password auth; enforce `sslmode=require` if SSL is configured on the VM. (See D4.)

## 4. Reference Documents

> Rule: read these before writing code; do not duplicate their content in the spec.

| Document | Location | What to look for |
|----------|----------|------------------|
| ChatGPT Enterprise MCP | `pg-mcp-server/project_docs/chatgpt_enterprise_mcp.md` | Connector vs App, Streamable HTTP, OAuth 2.1, Developer-Mode gating, `search`/`fetch` nuance |
| MCP Python SDK / FastMCP | `pg-mcp-server/project_docs/mcp_python_sdk.md` | Tool defs, `transport="http"`, ASGI launch, `TokenVerifier`/`AuthSettings`, annotations |
| Safe Postgres querying | `pg-mcp-server/project_docs/postgres_python_safe_querying.md` | psycopg pool, `sql.Identifier`, read-only role + GRANTs, pglast AST, hardening |
| Config & data models | `agent_docs/configs_data_models.md` | `pydantic-settings`, `get_settings()` + `lru_cache`, Pydantic v2 models |
| Logging | `agent_docs/logging_guidelines.md` | `get_logger()`, logfire, stdout fallback |
| Testing | `agent_docs/testing_guidelines.md` | pytest fixtures, `conftest.py`, coverage targets |
| Style | `agent_docs/style_guidelines.md` | PEP8/100-char, type hints, Google docstrings |
| Google MCP Toolbox eval | `pg-mcp-server/project_docs/google_mcp_toolbox.md` | *(created by Task 13)* field-level whitelist support; build-vs-adopt verdict |

## 5. Implementation Checklist

- [ ] **Task 1: Project scaffolding & deps**
      Files: `pyproject.toml`
      Details: `uv add fastmcp "psycopg[binary,pool]" pglast pydantic pydantic-settings pyyaml uvicorn`; `uv add --dev` already has pytest/ruff/mypy. Create empty module files per the layer table.

- [ ] **Task 2: Config** *(depends on: Task 1)*
      Files: `config.py`, `.env`, `.env.example`
      Details: `Settings(BaseSettings)` — DB conninfo, `policy_path`, OAuth settings, host/port, `statement_timeout_ms`, `max_rows`. `get_settings()` with `lru_cache`.
      Ref: `agent_docs/configs_data_models.md`. Test: invalid/missing env raises at startup.

- [ ] **Task 3: Data models** *(depends on: Task 1)*
      Files: `models.py`
      Details: Pydantic v2 `TablePolicy`, `QueryTemplate` (name, description, sql, typed params), `QueryResult`.

- [ ] **Task 4: AccessPolicy — load & validate** *(depends on: Tasks 2,3)*
      Files: `access_policy.py`, `policy.yaml`, `logging_config.py`
      Details: load YAML into models; allowlist lookup helpers `is_allowed_table/column`; build filtered schema dict. Startup validation deferred to Task 6 (needs DB).
      Test (`test_access_policy.py`): allowed vs denied identifiers; sensitive column never in filtered schema.

- [ ] **Task 5: Database layer** *(depends on: Task 2)*
      Files: `database.py`
      Details: `AsyncConnectionPool`; `execute_readonly()` (read-only txn, `statement_timeout`, bound params, row cap); `introspect_schema()` via `information_schema`.
      Ref: `postgres_python_safe_querying.md`. Test (`test_database.py`): read-only txn rejects writes; timeout honored (mock or test DB).

- [ ] **Task 6: Startup policy validation** *(depends on: Tasks 4,5)*
      Files: `access_policy.py`
      Details: cross-check every whitelisted table/column against `introspect_schema()`; fail fast with a clear error on mismatch.
      Test: bogus column in policy → startup error.

- [ ] **Task 7: Open-query AST validator** *(depends on: Task 4)* — *resolve D2 first*
      Files: `query_validator.py`
      Details: pglast parse → reject non-SELECT, multiple statements, `SELECT *`, non-allowlisted tables/cols; clamp/inject `LIMIT`.
      Ref: `postgres_python_safe_querying.md`. Test (`test_query_validator.py`): injection attempts, stacked queries, disallowed table/column, comment tricks all rejected; valid SELECT passes.

- [ ] **Task 8: Auth** *(depends on: Task 2)* — *resolve D1 first*
      Files: `auth.py`
      Details: OAuth 2.1 `TokenVerifier` + `AuthSettings` (or documented no-auth path). Authz enforced server-side, not via annotation hints.
      Ref: `mcp_python_sdk.md`, `chatgpt_enterprise_mcp.md`.

- [ ] **Task 9: MCP tools & server** *(depends on: Tasks 4,5,6,7,8)* — *resolve D3 first*
      Files: `main.py`
      Details: `FastMCP` server; tools `list_accessible_tables`, `describe_table`, template tool(s) (per D3), `query` (open mode). Tools annotated `readOnlyHint=True`; return text + structured content.
      Test (`test_tools.py`): each tool happy path + denial path with `AccessPolicy`/`Database` test doubles.

- [ ] **Task 10: HTTP launch** *(depends on: Task 9)*
      Files: `main.py`
      Details: serve Streamable HTTP at `/mcp/` (`transport="http"` / ASGI `http_app()` + uvicorn); bind host/port from config.

- [ ] **Task 11: Least-privilege DB role** *(depends on: Task 5)*
      Files: `sql/role_setup.sql`, README section
      Details: `CREATE ROLE` (LOGIN, NOSUPERUSER); **column-level** `GRANT SELECT (cols)` per whitelisted table — never a table-level `GRANT SELECT`; `default_transaction_read_only=on`.
      Ref: `postgres_python_safe_querying.md`.

- [ ] **Task 12: Integration test + local run** *(depends on: Tasks 9,10,11)*
      Files: `tests/test_integration.py`, `conftest.py`
      Details: end-to-end against a disposable Postgres (seeded with a sensitive column) — confirm template + open-query work and sensitive column is unreachable through every tool. Manual: connect MCP inspector / Developer-Mode connector.

- [ ] **Task 13: Containerize & Azure deploy skeleton** *(depends on: Task 12)*
      Files: `Dockerfile`, `.dockerignore`, `deploy.py`
      Details: Dockerfile running the ASGI app under uvicorn; `deploy.py` skeleton for **Azure Container Apps** (VNet-integrated env, secrets pulled from **Azure Key Vault**, NSG allow 5432 to the VM). Detailed production hardening deferred to a follow-on deploy spec.

- [ ] **Task 14: Google MCP Toolbox evaluation (LAST)** *(depends on: Task 12)*
      Files: `pg-mcp-server/project_docs/google_mcp_toolbox.md`
      Details: research `googleapis/mcp-toolbox`; determine whether it supports **field-level (column) whitelisting** and ChatGPT-connector deployment out of the box. Write a build-vs-adopt verdict comparing it to this implementation. (Deferred to last per user direction — do not research until this task is active.)

## 6. Acceptance Criteria

- [ ] All checklist tasks done; D1–D4 decisions recorded in the spec.
- [ ] `list_accessible_tables`/`describe_table` expose only whitelisted tables/columns; a seeded sensitive column (e.g. `password_hash`) is provably unreachable through every tool and absent from the advertised schema.
- [ ] A template (`get_user_profile`) returns correct rows with bound params only.
- [ ] Open-query mode accepts a valid whitelisted `SELECT` and rejects: non-SELECT, stacked statements, `SELECT *`, non-whitelisted table/column, and injection attempts — before hitting the DB.
- [ ] Queries run read-only as the least-priv role; writes fail at the DB layer; `statement_timeout` and row `LIMIT` enforced.
- [ ] Server is reachable over Streamable HTTP and authenticates per D1; verified with MCP inspector and/or a ChatGPT Enterprise Developer-Mode connector.
- [ ] `uv run pytest` passes; no new ruff/mypy errors; critical-path coverage ≥ 80%.
- [ ] `project_docs/google_mcp_toolbox.md` written with a clear build-vs-adopt verdict.
