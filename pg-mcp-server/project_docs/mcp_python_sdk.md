# MCP Python SDK — Reference for a Remote PostgreSQL Connector (2026)

Scope: build a custom **Python** MCP server, run it over **remote HTTP** transport, and register it as a **ChatGPT (Enterprise) connector**. Verified against official sources June 2026. See Sources at bottom.

---

## 1. SDK choice — `fastmcp` (standalone) vs `mcp` (official SDK)

There are two real options; both use the *same* `@mcp.tool` decorator style:

| | Package | What it is |
|---|---|---|
| Official SDK | `mcp` (`mcp[cli]`) | The official MCP Python SDK. Includes a **bundled FastMCP 1.x** at `mcp.server.fastmcp`. Lower-level, full transport/protocol control. v1.x stable; v2.0.0aN in alpha. |
| Standalone FastMCP | `fastmcp` | The actively maintained high-level framework (jlowin/PrefectHQ). **FastMCP 1.0 was merged into the official SDK in 2024; the standalone project has since moved far ahead** — now at **v3.0** (Feb 2026), built on MCP protocol 1.25.x. De-facto community standard, lowest boilerplate. Depends on `mcp` under the hood. |

**Recommendation for this project: use the standalone `fastmcp` (3.x).** Reasons: it is the most actively developed, has first-class HTTP deployment, ASGI integration, auth middleware, and the cleanest decorator API. The official `mcp` SDK only embeds the older FastMCP 1.x.

> If you ever need a custom transport or raw protocol control that FastMCP doesn't expose, drop to the official `mcp` low-level `Server` — but you almost certainly won't for a Postgres tool server.

Import note: with `fastmcp` you import `from fastmcp import FastMCP`. With the official SDK you import `from mcp.server.fastmcp import FastMCP`. Shared types (e.g. `ToolAnnotations`) come from `mcp.types` in both.

---

## 2. Defining tools, resources, prompts

Descriptions matter — the LLM selects/calls tools from the docstring + the typed signature.

```python
from typing import Annotated
from fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("pg-mcp-server")

class RowCount(BaseModel):
    table: str
    rows: int = Field(description="Number of rows matched")

@mcp.tool
def count_rows(
    table: Annotated[str, "Whitelisted table name to count rows in"],
    where: Annotated[str | None, "Optional parameterized predicate"] = None,
) -> RowCount:
    """Return the number of rows in a whitelisted table.

    Only tables on the allowlist may be queried; `where` is bound as a
    parameter, never string-concatenated into SQL.
    """
    ...
    return RowCount(table=table, rows=42)
```

- **Type annotations are required** for structured output / input-schema generation.
- **Description priority:** `@mcp.tool(description=...)` > docstring (Google/NumPy/Sphinx styles parsed) > per-param `Annotated[T, "..."]` / `Field(description=...)`.
- Return types supported: Pydantic models, `TypedDict`, dataclasses, `dict[str, T]`, primitives → auto-generates the JSON output schema.

Resources and prompts:

```python
@mcp.resource("schema://tables")
def list_tables() -> str:
    """Expose the allowlisted table/column catalog as a resource."""
    return "...catalog text..."

@mcp.resource("schema://table/{name}")          # templated resource
def table_schema(name: str) -> str:
    return f"columns of {name}"

@mcp.prompt
def safe_query_prompt(question: str) -> str:
    """Prompt template that steers the model toward allowlisted columns."""
    return f"Answer using only whitelisted columns. Question: {question}"
```

---

## 3. Remote transport — Streamable HTTP (what ChatGPT needs)

**Use Streamable HTTP, not stdio, not SSE.** SSE was deprecated in the MCP spec (March 2025 revision); Streamable HTTP is the current standard. ChatGPT connectors require a remote HTTPS endpoint.

In standalone **fastmcp** the transport value is `"http"` (alias of Streamable HTTP). Default endpoint path is **`/mcp/`**, default host `127.0.0.1`, port `8000`.

```python
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)   # serves http://host:8000/mcp/
```

CLI (no `__main__` edit needed):

```bash
fastmcp run server.py --transport http --host 0.0.0.0 --port 8000
```

ASGI integration (recommended for production / uvicorn / containers):

```python
# app.py
from fastmcp import FastMCP
mcp = FastMCP("pg-mcp-server")
# ... register tools ...
app = mcp.http_app()      # returns a Starlette ASGI app mounting /mcp/
```
```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

> Official `mcp` SDK equivalents: `mcp.run(transport="streamable-http")` and `mcp.streamable_http_app()` (note: value is `"streamable-http"`, app method differs from fastmcp's `http_app()`). It also needs a Starlette `lifespan` that runs `mcp.session_manager.run()`.

ChatGPT connector URL = your public HTTPS base + `/mcp/`, e.g. `https://pg-mcp.example.com/mcp/`. (For local dev, `ngrok http 8000` → use the ngrok URL.)

---

## 4. ChatGPT connector requirements (search + fetch)

ChatGPT will **reject a connector that lacks `search` and `fetch` tools** unless the workspace has Developer Mode enabled (available on Pro/Team/**Enterprise**/Edu). For Deep Research / "company knowledge" use, implement exactly these two **read-only** tools. Each must return the JSON in `structuredContent` **and** the same JSON as a stringified `content` text block.

`search(query)` → result shape:
```json
{ "results": [ { "id": "doc-1", "title": "Human title", "url": "https://example.com" } ] }
```

`fetch(id)` → result shape:
```json
{ "id": "doc-1", "title": "Human title", "text": "Full document text",
  "url": "https://example.com", "metadata": { "source": "optional k/v" } }
```

Returning both `structuredContent` and `content` in fastmcp:

```python
import json
from fastmcp.tools.tool import ToolResult
from mcp.types import ToolAnnotations

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
def search(query: str) -> ToolResult:
    """Search whitelisted Postgres data; returns id/title/url hits for ChatGPT."""
    payload = {"results": [{"id": "users:1", "title": "User 1", "url": "https://app/users/1"}]}
    return ToolResult(content=json.dumps(payload), structured_content=payload)
```

For this Postgres project: map `search` to your parameterized/constrained-query lookups returning row identifiers; map `fetch(id)` to return the full record text for an id.

---

## 5. Auth — OAuth 2.1 / bearer tokens

MCP remote servers authenticate via **OAuth 2.1**; the server acts as an OAuth **Resource Server** and validates bearer tokens (RFC 9728 Protected Resource Metadata advertises the Authorization Server). ChatGPT/OpenAI send the token in the `authorization` header on every request (OpenAI does not store it).

Official `mcp` SDK token-verifier hook:

```python
from pydantic import AnyHttpUrl
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

class PgTokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        # validate JWT / introspect; return None to reject
        ...

mcp = FastMCP(
    "pg-mcp-server",
    token_verifier=PgTokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl("https://auth.example.com"),
        resource_server_url=AnyHttpUrl("https://pg-mcp.example.com"),
        required_scopes=["pg.read"],
    ),
)
```

Standalone `fastmcp` 3.x ships auth providers/middleware (bearer/JWT verifiers and an `auth=` parameter on `FastMCP`) plus middleware hooks to gate individual tools. **Always enforce authorization inside the tool/server** — tool annotation hints are NOT a security boundary. Keep the Postgres allowlist + parameterization as a second layer regardless of auth.

---

## 6. Structured output & tool annotations

- **Structured output:** annotate the return type (Pydantic/TypedDict/dataclass/dict) → SDK emits `structuredContent` + an output JSON schema, and also a text `content` block for compatibility. Use `ToolResult(content=..., structured_content=...)` when you need to control both explicitly (required for ChatGPT search/fetch).
- **Annotations** (UX hints, untrusted — clients MUST NOT use them as the sole security gate):

| Annotation | Meaning |
|---|---|
| `title` | Human-readable tool title |
| `readOnlyHint` | Tool does not modify state (set **True** for all read-only Postgres query tools) |
| `destructiveHint` | May perform destructive updates |
| `idempotentHint` | Repeat calls with same args = no extra effect |
| `openWorldHint` | Interacts with external/unbounded entities (False for a fixed DB) |

```python
from mcp.types import ToolAnnotations

@mcp.tool(annotations=ToolAnnotations(
    title="Run Whitelisted Query", readOnlyHint=True,
    idempotentHint=True, openWorldHint=False,
))
def run_query(template: str, params: dict) -> dict:
    """Execute a pre-approved parameterized query template."""
    ...
```
A dict also works: `@mcp.tool(annotations={"readOnlyHint": True})`.

---

## 7. Packaging & deploy with `uv`

Install (pick the standalone framework recommended above):

```bash
uv init pg-mcp-server
cd pg-mcp-server
uv add fastmcp                 # the framework (pulls in mcp)
uv add "psycopg[binary,pool]"  # PostgreSQL driver + connection pool
uv add uvicorn                 # ASGI server for production HTTP
# (optional) uv add pydantic-settings   # config from env
```

Alternative if you instead use the official SDK directly:
```bash
uv add "mcp[cli]"              # official SDK + `mcp dev` / `mcp install` tooling
```

Run locally:
```bash
uv run fastmcp run server.py --transport http --host 0.0.0.0 --port 8000
# or:  uv run uvicorn app:app --host 0.0.0.0 --port 8000
```

Container (typical):
```dockerfile
FROM python:3.12-slim
RUN pip install uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```
Front it with HTTPS (load balancer / reverse proxy). ChatGPT connector URL = `https://<host>/mcp/`.

---

## Recent changes to flag (2026)

- **FastMCP 3.0** released Feb 2026 (new Providers/Transforms core); upgrading 3.2→3.3+ via pip can break imports → `pip install --force-reinstall fastmcp`.
- Standalone `fastmcp` uses transport name **`"http"`** and `http_app()`; the **official SDK** uses **`"streamable-http"`** and `streamable_http_app()` — don't mix them up.
- **SSE is deprecated** (MCP spec March 2025); target Streamable HTTP only.
- ChatGPT custom MCP connectors require **`search` + `fetch`** tools (or Developer Mode), returning JSON in both `structuredContent` and stringified `content`.

---

## Sources

- Official Python SDK (README, examples): https://github.com/modelcontextprotocol/python-sdk
- FastMCP docs — Welcome / project relationship: https://gofastmcp.com/getting-started/welcome
- FastMCP installation: https://gofastmcp.com/getting-started/installation
- FastMCP running the server (HTTP, `http_app()`, CLI): https://gofastmcp.com/deployment/running-server
- FastMCP tools (annotations, ToolResult, descriptions): https://gofastmcp.com/servers/tools
- FastMCP ↔ ChatGPT integration: https://gofastmcp.com/integrations/chatgpt
- OpenAI Apps SDK — build your MCP server (search/fetch shapes): https://developers.openai.com/apps-sdk/build/mcp-server
- OpenAI — MCP and Connectors (transport/auth): https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- OpenAI — Building a Deep Research MCP Server: https://developers.openai.com/cookbook/examples/deep_research_api/how_to_build_a_deep_research_mcp_server/readme
- MCP blog — Tool Annotations as Risk Vocabulary (hints are untrusted): https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/
- MCP spec / docs: https://modelcontextprotocol.io
