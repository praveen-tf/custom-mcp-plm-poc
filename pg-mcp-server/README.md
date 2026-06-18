# pg-mcp-server

A secure Python MCP (Model Context Protocol) server that lets AI agents query PostgreSQL safely. Only explicitly whitelisted tables and columns are visible — sensitive fields are hidden from the model and never reachable. Deployed as a remote HTTPS connector in ChatGPT Enterprise, delivering query results as chat output.

## Features

- **Table & column whitelisting**: Sensitive fields are excluded from `policy.yaml` and never appear in the advertised schema, blocking access at every layer.
- **Two query paths**:
  - *Primary constrained open-query mode*: Model writes a `SELECT`, validated by pglast AST parser against the whitelist. No `SELECT *`, stacked statements, or DML/DDL allowed.
  - *Parameterized templates*: Pre-defined typed MCP tools (e.g. `get_style_by_code(code: str)`) with bound parameters only — no raw SQL injection.
- **Read-only defense in depth**:
  - Column-level `SELECT`-only least-privilege database role (no table-level grants to prevent hidden columns from being re-exposed).
  - Read-only connections + `default_transaction_read_only`.
  - `statement_timeout` and row `LIMIT` clamping.
- **OAuth 2.1 authentication**: Microsoft Entra ID (or compatible authorization server) validates bearer tokens on every request.

## Tech Stack

- Python 3.12 (uv for package/environment management)
- FastMCP 3.x (Streamable HTTP at `/mcp/`)
- psycopg 3 (async connection pool)
- pglast (PostgreSQL AST validation)
- pydantic-settings (configuration management)

## Prerequisites

- **uv** (Python package manager; see [uv docs](https://docs.astral.sh/uv/))
- **PostgreSQL** (reachable and with a least-privilege role created; see [Setup](#setup))
- **.env configuration** with database connection details (see [Setup](#setup))

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in the required fields:

```bash
cp .env.example .env
```

Edit `.env`:
- `PGMCP_DATABASE_URL`: Connection string for the read-only database role (e.g. `postgresql://mcp_readonly:password@vm-host:5432/db?sslmode=require`)
- `PGMCP_POLICY_PATH`: Path to `policy.yaml` (default: `policy.yaml` in the project root)
- `PGMCP_HOST` / `PGMCP_PORT`: HTTP server bind address (default: `0.0.0.0:8000`)
- `PGMCP_STATEMENT_TIMEOUT_MS` / `PGMCP_MAX_ROWS`: Query hardening limits (default: 5000ms, 200 rows)
- `PGMCP_OAUTH_*`: OAuth 2.1 settings (optional for local dev, required for ChatGPT Enterprise connector)

For ChatGPT Enterprise, set the three OAuth fields to enable bearer-token authentication:
- `PGMCP_OAUTH_ISSUER_URL`: Entra ID issuer (e.g. `https://login.microsoftonline.com/<tenant-id>/v2.0`)
- `PGMCP_OAUTH_JWKS_URI`: Entra ID JWKS endpoint (e.g. `https://login.microsoftonline.com/<tenant-id>/discovery/v2.0/keys`)
- `PGMCP_OAUTH_AUDIENCE`: This server's resource identifier (e.g. `api://<app-id-uri>`)

### 3. Create the database role

Generate the least-privilege role SQL from the policy:

```bash
uv run python scripts/generate_role_sql.py > sql/role_setup.sql
```

Review `sql/role_setup.sql`, then apply it as a PostgreSQL admin:

```bash
psql -U postgres -d your_db -f sql/role_setup.sql
```

This creates the `mcp_readonly` role with column-level `SELECT` grants only (never table-level, which would re-expose hidden columns). Every time `policy.yaml` changes, regenerate and reapply.

### 4. Edit the access policy

Edit `policy.yaml` to declare which tables and columns the model may reach. Example:

```yaml
schema: public

tables:
  users:
    columns: [id, name, email]  # 'password_hash' intentionally omitted
  orders:
    columns: [id, user_id, total, created_at]

templates:
  get_user_by_id:
    description: Fetch a user by ID
    sql: "SELECT id, name, email FROM public.users WHERE id = %(user_id)s"
    parameters:
      user_id: { type: int, required: true }
```

Sensitive columns (e.g. `password_hash`, PII) are simply not listed — they are invisible to the model and cannot be queried via the open-query mode.

## Usage

### Local development

```bash
# Direct HTTP server
uv run python main.py
# Serves Streamable HTTP at http://0.0.0.0:8000/mcp/
```

### Production (ASGI)

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000
# Serves Streamable HTTP at http://0.0.0.0:8000/mcp/
```

For ChatGPT Enterprise, register the connector URL as `https://<your-host>/mcp/`.

### MCP tools

The server exposes three kinds of tools:

1. **`list_accessible_tables()`**: Lists all tables and their whitelisted columns.
2. **`describe_table(table)`**: Returns columns and data types for a single whitelisted table.
3. **`query(sql)`**: Executes a single read-only `SELECT` over whitelisted tables/columns (validated by pglast AST).
4. **Template tools** (one per `policy.yaml` template): e.g. `get_style_by_code(code: str)` — pre-defined typed queries with bound parameters.

## Architecture

The project follows a 3-layer design:

| Layer | File | Purpose |
|-------|------|---------|
| **Entry** | `main.py` | FastMCP server, tool registration, ASGI app for uvicorn, auth wiring, server startup/shutdown (open pool, validate policy vs DB, close pool on shutdown) |
| **Core Logic** | `access_policy.py` | Load `policy.yaml`, validate whitelist against live DB schema, filtered schema building, allowlist lookups |
| **Core Logic** | `database.py` | Async connection pool, read-only execution, introspection helper |
| **Core Logic** | `query_validator.py` | pglast AST validation — single `SELECT`, no `SELECT *`, no stacked statements, no DML/DDL, allowlist enforcement, LIMIT clamping |
| **Helpers** | `config.py` | Pydantic `Settings` (DB URL, policy path, OAuth, host/port, timeouts), `get_settings()` singleton |
| **Helpers** | `auth.py` | OAuth 2.1 JWT verification for FastMCP (Microsoft Entra ID) |
| **Helpers** | `models.py` | Pydantic v2 models: `PolicyDocument`, `TablePolicy`, `QueryTemplate`, `TemplateParameter` |
| **Helpers** | `logging_config.py` | Structured logging setup |
| **Config** | `policy.yaml` | Whitelist (tables → columns) + parameterized query templates |
| **Deploy** | `deploy.py` | Skeleton for Azure Container Apps + Key Vault |
| **Tests** | `tests/` | Unit and integration tests (run `uv run pytest`) |

## Configuration

### Environment variables

All variables are prefixed with `PGMCP_`:

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | str | (required) | psycopg connection string for the read-only role |
| `POLICY_PATH` | str | `policy.yaml` | Path to the access policy YAML file |
| `HOST` | str | `0.0.0.0` | HTTP server bind address |
| `PORT` | int | `8000` | HTTP server port |
| `STATEMENT_TIMEOUT_MS` | int | `5000` | Query timeout (milliseconds) |
| `MAX_ROWS` | int | `200` | Max rows per query result |
| `OAUTH_ISSUER_URL` | str | (optional) | OAuth issuer URL (required for ChatGPT Enterprise) |
| `OAUTH_JWKS_URI` | str | (optional) | OAuth JWKS endpoint (required for ChatGPT Enterprise) |
| `OAUTH_AUDIENCE` | str | (optional) | OAuth resource identifier / audience (required for ChatGPT Enterprise) |
| `OAUTH_REQUIRED_SCOPES` | list | `["pg.read"]` | Required OAuth scopes |

## Testing

Run the test suite:

```bash
uv run pytest
```

For integration tests that connect to the database, set `PGMCP_TEST_DATABASE_URL`:

```bash
PGMCP_TEST_DATABASE_URL="postgresql://mcp_readonly:...@host:5432/db" uv run pytest
```

## Deployment

### Azure Container Apps + Key Vault

A deployment skeleton is provided in `deploy.py`. Prerequisites:

- Azure Container Registry (ACR) for the image
- Azure Container Apps environment (VNet-integrated into the Postgres VM's VNet)
- Azure Key Vault with a secret for the database connection string
- NSG rule allowing the app subnet to reach the Postgres VM on port 5432

Configure via environment variables, then run:

```bash
# Dry-run (print commands)
AZ_RESOURCE_GROUP=my-rg AZ_ACR=myacr AZ_CONTAINERAPPS_ENV=my-env AZ_KEY_VAULT=my-kv \
  uv run python deploy.py

# Apply
AZ_RESOURCE_GROUP=my-rg AZ_ACR=myacr AZ_CONTAINERAPPS_ENV=my-env AZ_KEY_VAULT=my-kv \
  uv run python deploy.py --apply
```

The server is deployed with public HTTPS ingress; the ChatGPT connector URL is `https://<app-fqdn>/mcp/`.

### Docker

A `Dockerfile` is included for containerized deployment:

```bash
docker build -t pg-mcp-server .
docker run -e PGMCP_DATABASE_URL="..." -p 8000:8000 pg-mcp-server
```

## Security Notes

1. **The whitelist is the source of truth.** Anything not listed in `policy.yaml` is invisible and rejected before reaching the database.
2. **Column-level least-privilege role is the backstop.** The `mcp_readonly` role has `SELECT` on whitelisted columns only (never table-level grants). Even if the parser were bypassed, the database would reject unauthorized column access.
3. **Tool annotations are UX only, not a security boundary.** The actual enforcement happens in the AST validator and the database role.
4. **OAuth is the front door for ChatGPT Enterprise.** For local development without authentication, leave OAuth settings blank (logged warning: "running WITHOUT authentication").
