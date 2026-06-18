"""Entry point: build the MCP server, register tools, and run over Streamable HTTP.

This is the "table of contents" for the server. It wires the access policy, the
database layer, and the open-query validator into a small set of MCP tools:

  - ``list_accessible_tables`` / ``describe_table`` — the filtered schema (whitelist only)
  - one typed tool per template (decision D3), e.g. ``get_style_by_code``
  - ``query`` — the primary constrained open-query mode (validated single SELECT)

Run locally:    uv run python main.py
Run (ASGI):     uv run uvicorn main:app --host 0.0.0.0 --port 8000   # serves /mcp/
"""

import inspect
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from access_policy import AccessPolicy, PolicyError
from auth import build_auth
from config import get_settings
from database import Database
from logging_config import get_logger
from models import QueryTemplate
from query_validator import QueryNotAllowed, enforce_limit, validate_select

logger = get_logger(__name__)

settings = get_settings()
policy = AccessPolicy.from_file(settings.policy_path)
database = Database(
    settings.database_url,
    schema=policy.schema,
    statement_timeout_ms=settings.statement_timeout_ms,
    max_rows=settings.max_rows,
)

# All tools are read-only; these hints are UX only, never a security boundary.
READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
_PARAM_TYPES = {"str": str, "int": int, "float": float, "bool": bool}


@asynccontextmanager
async def lifespan(_server: FastMCP):
    """Open the pool, introspect the database, and validate the policy before serving."""
    await database.open()
    introspected = await database.introspect(policy.schema)
    policy.validate_against_db(introspected)  # fail fast on policy/DB mismatch
    try:
        yield
    finally:
        await database.close()


mcp = FastMCP("pg-mcp-server", lifespan=lifespan, auth=build_auth(settings))


@mcp.tool(annotations=READ_ONLY)
def list_accessible_tables() -> dict[str, Any]:
    """List the tables and columns you are allowed to query.

    Only whitelisted tables/columns appear here. Sensitive or unlisted fields are
    intentionally hidden and cannot be reached by any tool.
    """
    return policy.filtered_schema()


@mcp.tool(annotations=READ_ONLY)
def describe_table(table: Annotated[str, "A whitelisted table name"]) -> dict[str, Any]:
    """Describe the allowed columns (and data types) of one whitelisted table."""
    try:
        return policy.describe_table(table)
    except PolicyError as exc:
        raise ValueError(str(exc))


@mcp.tool(annotations=READ_ONLY)
async def query(
    sql: Annotated[str, "A single read-only SELECT over whitelisted tables and columns"],
) -> list[dict[str, Any]]:
    """Run an ad-hoc read-only SELECT.

    Rejected unless it is a single SELECT referencing only whitelisted tables and
    columns (no SELECT *, no writes, no multiple statements). A row LIMIT is enforced
    automatically, and the query runs as a read-only, least-privilege database role.
    """
    try:
        validate_select(sql, policy.schema, policy.allowlist)
    except QueryNotAllowed as exc:
        raise ValueError(f"query rejected: {exc}")
    return await database.execute(enforce_limit(sql, settings.max_rows))


def _register_template_tool(name: str, template: QueryTemplate) -> None:
    """Register one MCP tool per template, with typed parameters (decision D3).

    The tool's signature is built from the template's declared parameters so the model
    sees a named tool with typed args (e.g. ``get_style_by_code(code: str)``). Parameter
    values are bound by psycopg, never concatenated into the SQL.
    """
    parameters = [
        inspect.Parameter(
            param_name,
            inspect.Parameter.KEYWORD_ONLY,
            default=(inspect.Parameter.empty if spec.required else spec.default),
            annotation=_PARAM_TYPES[spec.type],
        )
        for param_name, spec in template.parameters.items()
    ]

    async def run_template(**kwargs: Any) -> list[dict[str, Any]]:
        return await database.execute(template.sql, kwargs)

    run_template.__name__ = name
    run_template.__doc__ = template.description or f"Run the '{name}' query template."
    run_template.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    run_template.__annotations__ = {param.name: param.annotation for param in parameters}
    run_template.__annotations__["return"] = list
    mcp.tool(annotations=READ_ONLY)(run_template)


for _template_name, _template in policy.templates.items():
    _register_template_tool(_template_name, _template)


# ASGI app for production (uvicorn). The ChatGPT connector URL is <https-base>/mcp/.
app = mcp.http_app()


if __name__ == "__main__":
    mcp.run(transport="http", host=settings.host, port=settings.port)
