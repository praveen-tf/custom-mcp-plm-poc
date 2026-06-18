"""PostgreSQL access: a read-only connection pool and safe query execution.

Every pooled connection is configured read-only with a statement timeout and a fixed
``search_path`` (so bare table names resolve to the policy's schema). Read-only is
enforced at the connection level via ``set_read_only`` and, ultimately, by the
least-privilege SELECT-only database role — no statement can write.
"""

from typing import Any

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from logging_config import get_logger

logger = get_logger(__name__)

_INTROSPECT_SQL = """
    SELECT table_name, column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s
    ORDER BY table_name, ordinal_position
"""


async def _configure_readonly(conn: AsyncConnection) -> None:
    """Make every pooled connection read-only (applied before it is handed out)."""
    await conn.set_read_only(True)


class Database:
    """A pooled, read-only gateway to the target PostgreSQL database."""

    def __init__(
        self,
        conninfo: str,
        *,
        schema: str,
        statement_timeout_ms: int,
        max_rows: int,
        min_size: int = 1,
        max_size: int = 10,
    ) -> None:
        self._max_rows = max_rows
        options = f"-c statement_timeout={statement_timeout_ms} -c search_path={schema}"
        self._pool = AsyncConnectionPool(
            conninfo=conninfo,
            min_size=min_size,
            max_size=max_size,
            open=False,  # opened explicitly during server startup
            configure=_configure_readonly,
            kwargs={"autocommit": True, "options": options},
        )

    async def open(self) -> None:
        await self._pool.open()
        logger.info("database pool opened")

    async def close(self) -> None:
        await self._pool.close()

    async def execute(self, query: Any, params: Any | None = None) -> list[dict[str, Any]]:
        """Run a read-only query, returning at most ``max_rows`` rows as dicts.

        Args:
            query: SQL text (``%s`` / ``%(name)s`` placeholders) or a psycopg Composable.
            params: Bound parameter values — never string-concatenated into the SQL.
        """
        async with self._pool.connection() as conn:
            async with conn.transaction():  # read-only (connection configured above)
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(query, params)
                    return await cur.fetchmany(self._max_rows)

    async def introspect(self, schema: str) -> dict[str, dict[str, str]]:
        """Return ``{table: {column: data_type}}`` for every column in ``schema``."""
        async with self._pool.connection() as conn:
            async with conn.transaction():
                async with conn.cursor(row_factory=dict_row) as cur:
                    await cur.execute(_INTROSPECT_SQL, (schema,))
                    rows = await cur.fetchall()
        schema_map: dict[str, dict[str, str]] = {}
        for row in rows:
            schema_map.setdefault(row["table_name"], {})[row["column_name"]] = row["data_type"]
        return schema_map
