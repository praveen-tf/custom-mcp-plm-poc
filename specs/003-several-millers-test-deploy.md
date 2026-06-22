# 003 Several Millers VM — Interim Test Deploy (synthetic data, no-auth)

**Status:** in-progress
**Created:** 2026-06-22
**Last updated:** 2026-06-22

---

## 1. Overview

The production ChatGPT Enterprise connector (spec 002, Task 7) is **blocked**: the client has
not delivered the Entra app registrations, so the OAuth path cannot be wired. To exercise
`pg-mcp-server` *now*, this spec stands up an interim deployment on a Several Millers Azure VM
with two deliberate departures from production: (1) **synthetic dummy data** instead of real PLM
rows, and (2) **no-auth, bound to `127.0.0.1`** and reached only over an SSH tunnel. No real data
ever leaves the source, and the unauthenticated endpoint is never internet-facing. The server code
is unchanged; this adds three helper scripts and reuses the spec-001 column-scoped role generator.

## 2. Requirements

- WHEN `generate_synthetic_sql.py` runs, THEN it emits portable SQL containing **only whitelisted
  columns** (read from `policy.yaml`) and **no real values**, with reference columns wired together
  so both query templates return rows.
- WHEN `pull_sample.py` runs against the source, THEN the connection is **read-only** (no write is
  ever issued) and its output is written under git-ignored `scripts/sample_data/` and never shipped
  to the VM.
- WHEN `synthetic_load.sql` is loaded into `mg_dwh.centric_8_plm`, THEN all 5 whitelisted tables are
  created and populated (default volumes: `styles=200, collections=16, seasons=4, category1s=8,
  category2s=24`).
- WHEN the `mcp_readonly` role (from `generate_role_sql.py`) is applied, THEN it can `SELECT`
  whitelisted columns but any `INSERT`/`UPDATE`/`DROP` fails with
  `cannot execute INSERT in a read-only transaction`.
- WHEN the server starts with the three `PGMCP_OAUTH_*` vars blank and `PGMCP_HOST=127.0.0.1`, THEN
  the log shows `running WITHOUT authentication`, `database pool opened`, `policy validated against
  DB: 5 tables, 2 templates`, and `Uvicorn running on http://127.0.0.1:8000`.
- WHEN `smoke_test.py` runs against the live `/mcp/` endpoint, THEN it reports **9/9 checks passed**
  and exits 0; a non-whitelisted column, `SELECT *`, and any write are each rejected before the DB.
- WHEN the endpoint is reached from a laptop, THEN it is **only** via `ssh -L 8000:127.0.0.1:8000`
  — the server is never bound to a public interface.

### Out of Scope

- Any application code change (server logic, tools, policy) — owned by spec 001.
- Real PLM data on the VM, OAuth/Entra, and any public exposure of the endpoint — those are spec 002.
- Production hardening: TLS on the VM Postgres, autoscale, monitoring, secret rotation.
- A persistent service definition beyond the optional `nohup`/systemd note in Task 8.

## 3. Design

Real data is sampled locally only to learn value *shapes*; synthetic data of the same shape is the
only thing that travels to the VM. The endpoint stays private behind an SSH tunnel.

```
[operator laptop / source-reachable host]                 [Several Millers Azure VM]
  pull_sample.py ──(read-only, real sample stays local)        Postgres :5432
        │                                                         mg_dwh / centric_8_plm
        ▼                                                              ▲
  generate_synthetic_sql.py ── synthetic_load.sql ──(scp)──▶ psql -f ──┘
                                                                       │ (mcp_readonly,
                                                                       │  column-scoped)
                                       uv run python main.py ──────────┘
                                         no-auth, 127.0.0.1:8000/mcp/
                                              ▲
              ssh -L 8000:127.0.0.1:8000 ─────┘   smoke_test.py / MCP inspector
```

### Affected Files

| Layer | File | Change |
|-------|------|--------|
| Script | `pg-mcp-server/scripts/generate_synthetic_sql.py` | **New.** Synthetic dummy data → portable SQL. Offline. |
| Script | `pg-mcp-server/scripts/pull_sample.py` | **New.** Read-only real sample + live column types from source. Optional; output git-ignored. |
| Script | `pg-mcp-server/scripts/smoke_test.py` | **New.** MCP client health check; drives every tool, PASS/FAIL, non-zero exit on failure. |
| Config | `.gitignore` | Add `pg-mcp-server/scripts/sample_data/` + `…/synthetic_load.sql` so real samples and generated SQL stay out of git. |
| Reused | `pg-mcp-server/scripts/generate_role_sql.py` | Unchanged — emits the column-scoped `mcp_readonly` role from `policy.yaml`. |

### Key Decisions

- **Synthetic, not real, data.** Pull a small real sample (whitelisted columns only) locally to learn
  shapes, then generate fake rows of the same shape. No real row ever reaches the VM.
- **All 5 tables, whitelisted columns only.** Generating every table guarantees both templates and the
  open-query path have data to return; the SQL is built straight from `policy.yaml` so it can never
  include a non-whitelisted column.
- **No-auth + localhost + SSH tunnel.** An unauthenticated DB-query endpoint must not be public, so it
  binds to `127.0.0.1` and is reached only through `ssh -L`. To later test *with* auth, set the
  `PGMCP_OAUTH_*` vars against your own tenant (per spec 002).
- **Reuse the column-scoped role.** `generate_role_sql.py` emits the spec-001 column-level
  `GRANT SELECT` role, so the DB-level backstop is in force here too — synthetic data does not relax it.
- **Single root `.gitignore` (with project prefix).** This repo keeps one repo-wide `.gitignore`; the
  new ignore lines use the `pg-mcp-server/` prefix so they actually match in this layout.
- **VM provisioned SSH-only.** The Azure VM (Ubuntu, in `Several_Millers_Default`) opens inbound
  **SSH (22) only** — never 5432/8000 — matching the no-auth + tunnel design. Detailed portal
  click-steps live in `project_docs/azure_vm_test_deploy_runbook.md`.

## 4. Reference Documents

> Rule: read these before executing; do not duplicate their content here.

| Document | Location | What to look for |
|----------|----------|------------------|
| Spec 001 (the server) | `specs/001-pg-mcp-server.md` | Policy/whitelist model, tools exposed, no-auth local-dev mode |
| Spec 002 (prod deploy) | `specs/002-azure-entra-deploy-runbook.md` | What this is the interim stand-in for; the `PGMCP_OAUTH_*` vars to set for an auth test |
| VM provisioning (Portal) | `pg-mcp-server/project_docs/azure_vm_test_deploy_runbook.md` | From-scratch Azure VM create, SSH-only NSG, connect; plus the on-VM steps |
| Safe Postgres querying | `pg-mcp-server/project_docs/db_schema_centric_8_plm.md` | Whitelisted tables/columns, value shapes the synthetic generator imitates |
| Column-scoped role | `pg-mcp-server/project_docs/postgres_python_safe_querying.md` | Why column-level GRANTs (never table-level), read-only role |
| Policy + models | `pg-mcp-server/policy.yaml`, `pg-mcp-server/models.py` | The single source of truth the scripts read (`db_schema`, `tables[*].columns`) |
| Test conventions | `agent_docs/testing_guidelines.md` | Smoke-test style, PASS/FAIL + non-zero exit |

## 5. Implementation Checklist

Repo-side tasks (Tasks A–B) add the scripts and are completable here; the operator runbook (Tasks
1–9) runs from your laptop + the VM, and each ends with a **Verify** that must pass before moving
on. Run runbook commands from `pg-mcp-server/` unless noted.

- [x] **Task A: Add the three scripts**
      Files: `scripts/generate_synthetic_sql.py`, `scripts/pull_sample.py`, `scripts/smoke_test.py`
      Details: Read `policy.yaml`/`models.py` for table+column structure; generator emits whitelisted
      columns only; sample puller sets the connection read-only; smoke test drives every tool.
      Verify: `uv run ruff check scripts/` and `uv run mypy scripts/` are clean.

- [x] **Task B: Git-ignore real samples + generated SQL**
      Files: `.gitignore`
      Details: Add `pg-mcp-server/scripts/sample_data/` and `pg-mcp-server/scripts/synthetic_load.sql`.
      Verify: `git status` shows neither path as untracked after running the scripts.

- [ ] **Task 1 (optional): Pull a real sample to inform synthesis**
      Run where the source DB is reachable read-only; real values stay local (git-ignored):
      `PGMCP_SOURCE_DSN='postgresql://reader:***@<source-host>:5432/mg_dwh?sslmode=require' uv run python scripts/pull_sample.py --rows 25`
      Verify: `scripts/sample_data/schema_types.json` + `sample_<table>.json` exist; no write is ever
      issued to the source (the script sets the connection read-only).

- [ ] **Task 2: Generate the synthetic SQL (no source access needed)**
      `uv run python scripts/generate_synthetic_sql.py --types scripts/sample_data/schema_types.json > scripts/synthetic_load.sql`
      (drop `--types` if Task 1 was skipped; tune volume with `--styles/--collections/...`).
      Verify: stderr prints `Generated rows: …` + sample style codes; the `.sql` begins with
      `CREATE SCHEMA IF NOT EXISTS centric_8_plm;` and contains only whitelisted columns.

- [ ] **Task 3: Provision the Azure VM (Portal)**
      In resource group `Several_Millers_Default`, create an **Ubuntu Server 24.04 LTS** VM (e.g.
      `vm-pgmcp-test`, **Standard_B2s**) with **SSH public key** auth (user `azureuser`) and
      **inbound SSH (22) only** — do **not** open 5432 or 8000 (the endpoint stays private behind the
      tunnel). Optionally restrict the 22 rule to your IP and enable Auto-shutdown. Full click-by-click:
      `pg-mcp-server/project_docs/azure_vm_test_deploy_runbook.md` (Part 1).
      Verify: the VM shows **Running** with a public IP; `ssh azureuser@<PUBLIC_IP>` lands a shell.

- [ ] **Task 4: Provision Postgres on the VM + create the DB** *(depends on: Task 3)*
      On the VM (Ubuntu): `sudo apt-get update && sudo apt-get install -y postgresql`, then
      `sudo -u postgres createdb mg_dwh`. (Docker alternative: `postgres:16`, then `createdb mg_dwh`.)
      Verify: `sudo -u postgres psql -d mg_dwh -c '\conninfo'` connects.

- [ ] **Task 5: Transfer + load the synthetic SQL** *(depends on: Tasks 2, 4)*
      `scp scripts/synthetic_load.sql <user>@<vm>:/tmp/`, then on the VM
      `sudo -u postgres psql -d mg_dwh -v ON_ERROR_STOP=1 -f /tmp/synthetic_load.sql`.
      Verify: `sudo -u postgres psql -d mg_dwh -c "SELECT count(*) FROM centric_8_plm.styles;"` returns
      the generated count (e.g. 200).

- [ ] **Task 6: Create the column-scoped `mcp_readonly` role** *(depends on: Task 5)*
      `uv run python scripts/generate_role_sql.py > sql/role_setup.sql`, replace `CHANGE_ME` with a
      strong password, scp over, then `sudo -u postgres psql -d mg_dwh -v ON_ERROR_STOP=1 -f /tmp/role_setup.sql`.
      Verify: as `mcp_readonly`, `SELECT code FROM centric_8_plm.styles LIMIT 1` works but
      `INSERT INTO centric_8_plm.styles(id) VALUES ('x')` fails with
      `cannot execute INSERT in a read-only transaction`.

- [ ] **Task 7: Install + configure the server on the VM** *(depends on: Task 6)*
      Copy `pg-mcp-server/` to the VM (or `git clone`), `uv sync`, then create `.env`:
      `PGMCP_DATABASE_URL=postgresql://mcp_readonly:<password>@127.0.0.1:5432/mg_dwh`,
      `PGMCP_HOST=127.0.0.1`, and leave all three `PGMCP_OAUTH_*` blank
      (add `?sslmode=require` only if the VM's Postgres has TLS).
      Verify: `uv run python -c "from config import get_settings; get_settings()"` loads with no error.

- [ ] **Task 8: Run the server (no-auth, localhost)** *(depends on: Task 7)*
      `uv run python main.py` (to keep it running: a systemd unit, or
      `nohup uv run python main.py > server.log 2>&1 &`).
      Verify: log shows `running WITHOUT authentication`, `database pool opened`,
      `policy validated against DB: 5 tables, 2 templates`, then `Uvicorn running on http://127.0.0.1:8000`.

- [ ] **Task 9: Smoke-test end to end** *(depends on: Task 8)*
      On the VM: `uv run python scripts/smoke_test.py --url http://127.0.0.1:8000/mcp/`. To drive it
      from a laptop / MCP inspector, tunnel first: `ssh -L 8000:127.0.0.1:8000 <user>@<vm>`, then point
      the client at `http://127.0.0.1:8000/mcp/`.
      Verify: prints `9/9 checks passed` and exits 0.

## 6. Acceptance Criteria

- [ ] `synthetic_load.sql` loads cleanly into `mg_dwh.centric_8_plm`; only whitelisted columns, no real values.
- [ ] `mcp_readonly` reads whitelisted columns; writes fail (read-only transaction).
- [ ] Server runs no-auth on `127.0.0.1:8000`, logs the no-auth warning, validates policy (5 tables, 2 templates).
- [ ] `smoke_test.py` reports 9/9; non-whitelisted column, `SELECT *`, and write are all rejected before the DB.
- [ ] `scripts/sample_data/` and `scripts/synthetic_load.sql` are git-ignored.
- [ ] The endpoint is only ever reached via the SSH tunnel — never bound to a public interface.
- [ ] The Azure VM exists in `Several_Millers_Default` with **SSH (22) only** inbound (no public 5432/8000).
- [ ] `ruff` + `mypy` are clean on all three new scripts.

> Depends on the existing `pg-mcp-server` (spec 001): `policy.yaml`, `models.py`, `main.py`,
> `config.py`, `scripts/generate_role_sql.py`.
