"""Open-query validation: accept only a single read-only SELECT over whitelisted objects.

The model may write its own SQL, but every query is parsed to an AST with pglast
(PostgreSQL's own grammar, via libpg_query) and rejected unless it is a single
``SELECT`` referencing only whitelisted tables and columns. We parse, never regex —
keyword blocklists are trivially defeated by comments, casing, and encoding.

This is one layer of defense; the column-level read-only database role is the real
backstop (see ``sql/role_setup.sql``).
"""

import re

from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.visitors import Visitor

# psycopg placeholders (`%(name)s` and `%s`). Used only to neutralize template SQL
# before AST-parsing it for whitelist validation (libpg_query can't parse placeholders).
_PLACEHOLDER_RE = re.compile(r"%\((\w+)\)s|%s")


class QueryNotAllowed(Exception):
    """Raised when a query violates the read-only / whitelist constraints."""


def _collect(stmt: ast.Node) -> tuple[set[tuple[str | None, str]], list[str], bool]:
    """Walk a parsed statement and collect referenced tables, columns, and `*` usage."""
    tables: set[tuple[str | None, str]] = set()
    columns: list[str] = []
    star = False

    class _Collector(Visitor):
        def visit_RangeVar(self, ancestors, node):  # noqa: N802 (pglast naming)
            tables.add((node.schemaname, node.relname))

        def visit_ColumnRef(self, ancestors, node):  # noqa: N802
            nonlocal star
            names = [field.sval for field in node.fields if isinstance(field, ast.String)]
            if any(isinstance(field, ast.A_Star) for field in node.fields):
                star = True
            elif names:
                columns.append(names[-1])  # bare `col` or qualified `table.col`

    _Collector()(stmt)
    return tables, columns, star


def _enforce_whitelist(
    tables: set[tuple[str | None, str]],
    columns: list[str],
    star: bool,
    schema: str,
    allowed: dict[str, set[str]],
) -> None:
    if star:
        raise QueryNotAllowed("SELECT * is not allowed; name columns explicitly")
    for schema_name, table in tables:
        if schema_name is not None and schema_name != schema:
            raise QueryNotAllowed(f"schema not allowed: {schema_name}")
        if table not in allowed:
            raise QueryNotAllowed(f"table not allowed: {table}")
    permitted = set().union(*(allowed[table] for _, table in tables)) if tables else set()
    disallowed = sorted(set(columns) - permitted)
    if disallowed:
        raise QueryNotAllowed(f"column(s) not allowed: {disallowed}")


def _select_statement(sql_text: str) -> ast.SelectStmt:
    """Parse `sql_text`, asserting it is exactly one SELECT statement."""
    try:
        statements = parse_sql(sql_text)
    except ParseError as exc:
        raise QueryNotAllowed(f"unparseable SQL: {exc}")
    if len(statements) != 1:
        raise QueryNotAllowed("only a single statement is allowed")
    stmt = statements[0].stmt
    if not isinstance(stmt, ast.SelectStmt):
        raise QueryNotAllowed("only SELECT statements are allowed")
    return stmt


def validate_select(sql_text: str, schema: str, allowed: dict[str, set[str]]) -> None:
    """Raise ``QueryNotAllowed`` unless `sql_text` is a whitelisted single SELECT."""
    stmt = _select_statement(sql_text)
    tables, columns, star = _collect(stmt)
    if not tables:
        raise QueryNotAllowed("query must reference at least one whitelisted table")
    _enforce_whitelist(tables, columns, star, schema, allowed)


def placeholder_names(sql_text: str) -> set[str]:
    """Return the set of named ``%(name)s`` placeholders found in `sql_text`."""
    return {match.group(1) for match in _PLACEHOLDER_RE.finditer(sql_text) if match.group(1)}


def validate_template_sql(sql_text: str, schema: str, allowed: dict[str, set[str]]) -> None:
    """Validate a template's SQL against the whitelist (placeholders neutralized first)."""
    neutralized = _PLACEHOLDER_RE.sub("1", sql_text)
    validate_select(neutralized, schema, allowed)


def enforce_limit(sql_text: str, max_rows: int) -> str:
    """Append ``LIMIT max_rows`` when the query has no top-level limit.

    When the query already specifies a limit it is left untouched; the database layer
    additionally caps the number of rows it fetches, and ``statement_timeout`` bounds
    runtime — so the row cap holds regardless.
    """
    stmt = _select_statement(sql_text)
    if stmt.limitCount is None:
        return f"{sql_text.strip().rstrip(';').strip()} LIMIT {max_rows}"
    return sql_text
