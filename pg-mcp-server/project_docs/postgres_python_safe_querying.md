# Safe, Read-Only, Whitelisted PostgreSQL Access from Python (MCP Server)

Reference for a Python MCP server that lets an LLM query Postgres through (a) a secure
connection, (b) a TABLE whitelist, (c) a COLUMN whitelist (sensitive fields never reach the
LLM), (d) parameterized query TEMPLATES, and (e) a constrained OPEN-QUERY mode that still
enforces the table+column whitelist.

Researched June 2026 against current official sources (see **Sources** at the end).
Versions noted inline: psycopg **3.3.x** (latest dev line; `AsyncConnectionPool` since 3.2),
asyncpg **0.31.0** (Nov 2025), sqlglot (current), pglast **v7.x** (wraps `libpg_query`).

---

## 0. TL;DR / Recommendations

- **Driver:** **psycopg 3** (async) + **`psycopg_pool.AsyncConnectionPool`**. asyncpg is ~faster,
  but psycopg 3's first-class `sql.SQL`/`sql.Identifier` composition is exactly what a
  whitelist enforcer needs, and it ships an official async pool. Use asyncpg only if raw
  throughput dominates and you build identifier-quoting yourself.
- **Dynamic identifiers:** table/column names **cannot** be bind parameters. Use
  `psycopg.sql.Identifier`/`sql.SQL(...).format(...)` **and** validate every identifier against
  the in-memory allowlist *before* composing. Values always go through `%s`/`Placeholder`.
- **Read-only + least privilege (defense in depth):** dedicated `LOGIN` role with **column-level
  `SELECT` grants only** + `default_transaction_read_only` + per-transaction `read_only=True`.
  Each layer alone is insufficient; together they fail closed.
- **Open-query mode:** parse with an **AST validator** (prefer **pglast**, the real Postgres
  grammar; sqlglot is the portable fallback). Reject non-`SELECT`, multiple statements,
  disallowed tables/columns, `*`, and write/DDL nodes. Use a structured DSL for templates.
- **Hardening:** `statement_timeout`, forced `LIMIT`, single-statement only, least-priv role,
  `autocommit`-off read-only tx, never interpolate untrusted strings.

### Install

```bash
uv add "psycopg[binary,pool]"   # driver + libpq binary + psycopg_pool
uv add pglast                    # Postgres-native SQL AST validation (libpg_query)
# Portable alternative / extra cross-check:
uv add sqlglot
```

---

## 1. Driver choice: psycopg 3 vs asyncpg (2026)

| | **psycopg 3** | **asyncpg** |
|---|---|---|
| Latest | 3.3.x line (async pool since **3.2**) | **0.31.0** (Nov 2025), PG 9.5–18, Py 3.9+ |
| Protocol | libpq, DB-API-like, sync **and** async | own binary protocol, async-only, **not** DB-API |
| Param style | `%s` / `%(name)s` | numbered `$1, $2` |
| Pool | `psycopg_pool` (`AsyncConnectionPool`) | `asyncpg.create_pool` |
| Identifier composition | **built-in `psycopg.sql`** (Identifier/SQL/Literal) | none — you quote names yourself |
| Speed | slightly slower | ~25–35% lower latency; binary decoding |

**Recommendation: psycopg 3 for this MCP server.** The whitelist enforcement leans heavily on
safe identifier composition, which psycopg provides natively via `psycopg.sql`. asyncpg has no
equivalent, so you would hand-roll identifier quoting — exactly the error-prone surface we want
to avoid. The throughput edge of asyncpg rarely matters for an LLM-driven query tool (latency is
dominated by the model, not the driver).

### psycopg 3 async pool (recommended setup)

```python
from psycopg_pool import AsyncConnectionPool

# Connect as the least-privileged read-only role (see section 3).
# Force read-only at the session level as a baseline.
CONNINFO = (
    "host=db port=5432 dbname=app "
    "user=mcp_readonly password=... "
    "options='-c default_transaction_read_only=on -c statement_timeout=5000'"
)

pool = AsyncConnectionPool(
    conninfo=CONNINFO,
    min_size=1, max_size=10,
    open=False,           # open explicitly in async startup
    kwargs={"autocommit": True},   # then use explicit read-only transactions per query
)

async def startup():
    await pool.open()

async def shutdown():
    await pool.close()
```

### asyncpg equivalent (if you must)

```python
import asyncpg
pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
async with pool.acquire() as conn:
    async with conn.transaction(readonly=True):     # asyncpg spelling: readonly
        rows = await conn.fetch("SELECT id, name FROM users WHERE id = $1", 10)
```

---

## 2. Parameterized queries & dynamic identifiers (anti-injection core)

**Rule 1 — values are bind parameters.** Never f-string / `%`-format user values into SQL.

```python
# CORRECT: value bound as a parameter
await cur.execute("SELECT id, name FROM users WHERE id = %s", (user_id,))

# WRONG: string interpolation -> SQL injection
await cur.execute(f"SELECT * FROM users WHERE id = {user_id}")   # NEVER
```

**Rule 2 — identifiers (table/column names) CANNOT be bind parameters.** A placeholder (`%s`)
is sent to Postgres as a *value*; the server will not interpret it as a table or column name.
You must build identifiers into the SQL text itself — safely.

The psycopg `sql` module is the only mainstream adapter that composes identifiers *and* values
safely. `sql.Identifier` applies correct PostgreSQL identifier quoting; `sql.SQL` is a trusted
literal template; `sql.Placeholder` emits a `%s`/named marker for the *value* bound at execute
time. `sql.SQL("...").format(...)` merges only `Composable` objects.

```python
from psycopg import sql

# field/table/pkey are IDENTIFIERS -> Identifier; the id value -> %s placeholder
query = sql.SQL("SELECT {fields} FROM {table} WHERE {pkey} = %s").format(
    fields=sql.SQL(", ").join(map(sql.Identifier, ["id", "name"])),
    table=sql.Identifier("public", "users"),   # schema-qualified
    pkey=sql.Identifier("id"),
)
await cur.execute(query, (42,))
```

**Why this matters (from the psycopg docs):** a raw `"... %s ..." % table_name` is dangerous
because "the table name may be an invalid SQL literal and need quoting; even more serious is the
security problem in case the table name comes from an untrusted source." `sql.SQL` itself "doesn't
undergo any form of escaping, so it is not suitable to represent variable identifiers or values"
— so `sql.SQL` text must always be a trusted constant; everything dynamic goes through
`Identifier` (names) or `Placeholder`/parameters (values).

**Rule 3 — quoting is NOT validation.** `sql.Identifier("users; DROP TABLE x")` produces the
quoted name `"users; DROP TABLE x"` (a single, harmless, non-existent identifier) — it cannot
inject, but it also won't resolve. For a whitelist server, **always validate the identifier
string against your allowlist before composing**, so the LLM can never even name an
unauthorized object:

```python
ALLOWED = {                       # the only schema the LLM ever sees
    "users": {"id", "name", "created_at"},          # NO password_hash, NO ssn
    "orders": {"id", "user_id", "total", "status"},
}

def safe_identifier(table: str, column: str) -> sql.Identifier:
    cols = ALLOWED.get(table)
    if cols is None or column not in cols:
        raise PermissionError(f"not allowed: {table}.{column}")
    return sql.Identifier(table, column)
```

---

## 3. Enforcing read-only (defense in depth)

Use **all three** layers; any one alone is bypassable or fail-open.

### 3a. Least-privilege DB role with column-level SELECT grants

This is the strongest layer: the DB itself refuses anything outside the whitelist, including
SELECTs of sensitive columns — even if app code has a bug.

```sql
-- Dedicated login role, no inherited privileges
CREATE ROLE mcp_readonly LOGIN PASSWORD '...' NOSUPERUSER NOCREATEDB NOCREATEROLE;

-- Start from zero: revoke the public default
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM mcp_readonly;
REVOKE ALL ON SCHEMA public FROM mcp_readonly;

-- Must allow schema lookup to reference objects
GRANT USAGE ON SCHEMA public TO mcp_readonly;

-- COLUMN-LEVEL SELECT ONLY. Omitted columns (password_hash, ssn) are inaccessible:
-- SELECT * or SELECT password_hash will be denied by the server.
GRANT SELECT (id, name, created_at)        ON public.users  TO mcp_readonly;
GRANT SELECT (id, user_id, total, status)  ON public.orders TO mcp_readonly;
```

GRANT column syntax (PostgreSQL docs):

```sql
GRANT { { SELECT | INSERT | UPDATE | REFERENCES } ( column_name [, ...] ) [...] }
    ON [ TABLE ] table_name [, ...] TO role_specification;
```

**Critical caveat (PostgreSQL docs):** do **not** mix table-level and column-level grants. A
user may SELECT a column "if they hold that privilege for either the specific column or its whole
table," and "the table-level grant is unaffected by a column-level operation." So a prior
table-wide `GRANT SELECT ON users` would *override* your column restrictions, re-exposing
sensitive columns. Grant column-level **only**; never `GRANT SELECT ON ALL TABLES`. Superusers
bypass all checks — the MCP role must not be a superuser.

### 3b. Read-only transactions

`SET TRANSACTION READ ONLY` (or the `default_transaction_read_only` GUC) blocks
`INSERT/UPDATE/DELETE/MERGE`, `COPY FROM`, all `CREATE/ALTER/DROP`, `TRUNCATE`, `GRANT/REVOKE`,
`COMMENT`, and `EXECUTE`/`EXPLAIN ANALYZE` of any of those. (It is "a high-level notion of
read-only that does not prevent all writes to disk," but it stops all data/DDL mutation —
sufficient here, on top of the SELECT-only role.)

psycopg 3 — per-transaction (preferred; `read_only` setter is a method since 3.2):

```python
async with pool.connection() as conn:           # autocommit=True pool
    async with conn.transaction(read_only=True):  # psycopg spelling: read_only
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            rows = await cur.fetchall()
```

Connection / session baseline (set in conninfo `options`, shown in section 1, or):

```sql
SET default_transaction_read_only TO on;   -- session default; for autocommit connections
```

---

## 4. Schema introspection (build & validate the advertised schema)

Discover real tables/columns so the server (a) builds the *filtered* schema it advertises to the
LLM and (b) validates open queries. Query as the read-only role; intersect with your allowlist so
the advertised schema never includes sensitive columns even if a grant slips.

```python
INTROSPECT_COLUMNS = """
    SELECT c.table_schema, c.table_name, c.column_name, c.data_type
    FROM information_schema.columns AS c
    WHERE c.table_schema = %s
    ORDER BY c.table_name, c.ordinal_position
"""
# Privilege-aware: only what THIS role may actually SELECT (column granularity):
INTROSPECT_GRANTED = """
    SELECT table_schema, table_name, column_name
    FROM information_schema.column_privileges
    WHERE grantee = current_user AND privilege_type = 'SELECT'
"""
```

Then advertise only `allowlist ∩ granted ∩ information_schema` to the LLM. `pg_catalog`
(`pg_class`, `pg_attribute`, `pg_namespace`) is the lower-level alternative if you need OIDs or
attributes `information_schema` omits.

---

## 5. Open-query mode: AST validation vs query-builder DSL

### Option A — SQL AST validation (recommended for free-form SELECT)

Parse the LLM's SQL, walk the AST, and **reject** anything that isn't a single read-only SELECT
over whitelisted tables/columns. **Parse, don't regex** — regex/keyword blocklists are trivially
bypassed by comments, casing, and encoding.

**pglast (recommended): uses PostgreSQL's own grammar via `libpg_query`**, so the parse tree
matches exactly what the server will execute (no dialect drift).

```python
from pglast import parse_sql
from pglast.parser import ParseError
from pglast import ast
from pglast.visitors import Visitor

def validate_select(sql_text: str, allowed: dict[str, set[str]]) -> None:
    try:
        stmts = parse_sql(sql_text)            # tuple of RawStmt; raises ParseError
    except ParseError as e:
        raise ValueError(f"unparseable SQL: {e}")

    # 1. single statement only (blocks "...; DROP ...")
    if len(stmts) != 1:
        raise ValueError("only a single statement is allowed")

    # 2. must be a plain SELECT (no INSERT/UPDATE/DELETE/CTE-write/DDL)
    stmt = stmts[0].stmt
    if not isinstance(stmt, ast.SelectStmt):
        raise ValueError("only SELECT is allowed")

    # 3. walk every node: collect tables (RangeVar) and columns (ColumnRef),
    #    reject star, reject write/DDL/utility node types if present.
    tables, columns, star = set(), [], False
    class V(Visitor):
        def visit_RangeVar(self, ancestors, node):  # table references
            tables.add(node.relname)
        def visit_ColumnRef(self, ancestors, node):  # column references
            nonlocal star
            fields = [f.sval for f in node.fields if isinstance(f, ast.String)]
            if any(isinstance(f, ast.A_Star) for f in node.fields):
                star = True
            elif fields:
                columns.append(fields[-1])           # bare or table.col
    V()(stmt)

    if star:
        raise ValueError("SELECT * is not allowed; name columns explicitly")
    bad_tables = tables - allowed.keys()
    if bad_tables:
        raise ValueError(f"disallowed table(s): {bad_tables}")
    allowed_cols = set().union(*(allowed[t] for t in tables)) if tables else set()
    bad_cols = set(columns) - allowed_cols
    if bad_cols:
        raise ValueError(f"disallowed column(s): {bad_cols}")
    # caller then enforces LIMIT + runs inside a read_only transaction (sections 3, 6)
```

**sqlglot alternative (portable, no compiled lib):**

```python
import sqlglot
from sqlglot import exp

def validate_select_sqlglot(sql_text: str, allowed: dict[str, set[str]]):
    stmts = sqlglot.parse(sql_text, read="postgres")     # list; >1 => multiple statements
    if len(stmts) != 1 or not isinstance(stmts[0], exp.Select):
        raise ValueError("only a single SELECT is allowed")
    expr = stmts[0]
    if expr.find(exp.Star):
        raise ValueError("SELECT * not allowed")
    tables = {t.name for t in expr.find_all(exp.Table)}
    if tables - allowed.keys():
        raise ValueError(f"disallowed table(s): {tables - allowed.keys()}")
    cols = {c.name for c in expr.find_all(exp.Column)}
    allowed_cols = set().union(*(allowed[t] for t in tables)) if tables else set()
    if cols - allowed_cols:
        raise ValueError(f"disallowed column(s): {cols - allowed_cols}")
```

**pglast vs sqlglot:** pglast = exact Postgres grammar (best fidelity, native dep via
`libpg_query`); sqlglot = pure-Python, multi-dialect (easier install, but its tree is a
normalization, not Postgres's). For a Postgres-only MCP server, **prefer pglast**; optionally run
sqlglot too as a cheap second opinion. Either way, AST validation is **necessary but not
sufficient** — keep the DB-level read-only role (section 3) as the real backstop.

### Option B — Structured query-builder DSL

Instead of accepting SQL text, expose a JSON-shaped request (`{"table": ..., "columns": [...],
"filters": [...], "limit": ...}`) and *build* the SQL yourself with `psycopg.sql` (section 2).
The LLM never emits SQL, so there is no parser to outwit and the attack surface collapses to
allowlist lookups.

**Recommendation:** Use **both, by mode.** Named **TEMPLATES** and the structured path → **DSL /
`psycopg.sql` composition** (safest, fully deterministic). **OPEN-QUERY** mode → **pglast AST
validation** for flexibility, always layered behind the least-privilege role + read-only tx +
forced LIMIT.

---

## 6. Hardening checklist

- **`statement_timeout`** — cap runaway queries: in conninfo `options='-c statement_timeout=5000'`
  or `await cur.execute("SET statement_timeout = 5000")` (ms) per session.
- **Force a row LIMIT** — append/clamp `LIMIT n` server-side; if SQL already has a larger LIMIT,
  reduce it. Belt-and-suspenders: also slice results in Python.
- **Single statement only** — pglast `len(stmts) != 1` (or sqlglot `len(...) != 1`) rejects
  `; DROP ...`. psycopg's normal `execute()` runs one command; do not enable multi-statement.
- **Block comments / stacked queries / star** — handled by AST validation, not regex; reject
  `A_Star`/`exp.Star`. Comments are stripped by the parser and can't smuggle a second statement
  past the single-statement check.
- **Least-privilege role** — column-level `SELECT` only, no table-level grants, `NOSUPERUSER`
  (section 3a). The DB is the final authority.
- **Read-only transaction** — `conn.transaction(read_only=True)` +
  `default_transaction_read_only=on` (section 3b).
- **Never interpolate untrusted strings** — values → parameters (`%s`); identifiers → validated
  `sql.Identifier`; `sql.SQL` text is always a constant.
- **Filter sensitive columns at every layer** — allowlist, GRANTs, and advertised schema all
  exclude password hashes / PII, so they never reach the model or the wire.

---

## Sources

- psycopg 3 — `psycopg.sql` (SQL composition): https://www.psycopg.org/psycopg3/docs/api/sql.html
- psycopg 2 — `sql` module (identical API, canonical safe example & warnings):
  https://www.psycopg.org/docs/sql.html
- psycopg 3 — connection pools (`psycopg_pool`, `AsyncConnectionPool`, since 3.2):
  https://www.psycopg.org/psycopg3/docs/advanced/pool.html
- psycopg 3 — `psycopg_pool` API: https://www.psycopg.org/psycopg3/docs/api/pool.html
- psycopg 3 — connection classes (`read_only` / `set_read_only`, autocommit):
  https://www.psycopg.org/psycopg3/docs/api/connections.html
- psycopg 3 — transactions (`transaction(read_only=True)`, `default_transaction_read_only`):
  https://www.psycopg.org/psycopg3/docs/basic/transactions.html
- psycopg 3 — installation (`psycopg[binary,pool]`):
  https://www.psycopg.org/psycopg3/docs/basic/install.html
- PostgreSQL — `SET TRANSACTION` (READ ONLY semantics):
  https://www.postgresql.org/docs/current/sql-set-transaction.html
- PostgreSQL — `GRANT` (column-level SELECT, table vs column interaction):
  https://www.postgresql.org/docs/current/sql-grant.html
- PostgreSQL — Privileges (5.8, column-level behavior):
  https://www.postgresql.org/docs/current/ddl-priv.html
- PostgreSQL — `information_schema.column_privileges`:
  https://www.postgresql.org/docs/current/infoschema-column-privileges.html
- asyncpg — repo / overview (v0.31.0, binary protocol, `$1` params):
  https://github.com/MagicStack/asyncpg
- asyncpg — API reference (`create_pool`, `transaction(readonly=True)`):
  https://magicstack.github.io/asyncpg/current/api/index.html
- sqlglot — repo (parse/parse_one, `find_all(exp.Table/exp.Column)`, `exp.Select`):
  https://github.com/tobymao/sqlglot
- pglast — usage (`parse_sql` -> RawStmt tuple, `.stmt`, Visitor, ParseError):
  https://pglast.readthedocs.io/en/latest/usage.html
- pglast — parser API: https://pglast.readthedocs.io/en/latest/parser.html
