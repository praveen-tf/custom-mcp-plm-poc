"""The access policy: the table/column whitelist and query templates the server exposes.

Loaded from ``policy.yaml`` at startup and validated against the live database schema
(``validate_against_db``). Anything not present in the policy is invisible to the model
and rejected before any SQL runs — sensitive columns simply aren't listed.
"""

from pathlib import Path

import yaml

from logging_config import get_logger
from models import PolicyDocument, QueryTemplate
from query_validator import QueryNotAllowed, placeholder_names, validate_template_sql

logger = get_logger(__name__)


class PolicyError(Exception):
    """Raised when the policy is invalid or inconsistent with the live database."""


class AccessPolicy:
    """In-memory view of the whitelist + templates, with fast allowlist lookups."""

    def __init__(self, document: PolicyDocument) -> None:
        self._doc = document
        # table -> set(columns) for O(1) allowlist checks.
        self._allowed: dict[str, set[str]] = {
            table: set(policy.columns) for table, policy in document.tables.items()
        }
        # (table, column) -> data_type, populated by validate_against_db().
        self._column_types: dict[tuple[str, str], str] = {}

    @classmethod
    def from_file(cls, path: str | Path) -> "AccessPolicy":
        """Load and parse a policy from a YAML file."""
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls(PolicyDocument.model_validate(raw))

    @property
    def schema(self) -> str:
        return self._doc.db_schema

    @property
    def tables(self) -> list[str]:
        return list(self._allowed)

    @property
    def allowlist(self) -> dict[str, set[str]]:
        """table -> allowed columns, as consumed by the open-query validator."""
        return self._allowed

    @property
    def templates(self) -> dict[str, QueryTemplate]:
        return self._doc.templates

    def is_allowed_table(self, table: str) -> bool:
        return table in self._allowed

    def is_allowed_column(self, table: str, column: str) -> bool:
        return column in self._allowed.get(table, set())

    def get_template(self, name: str) -> QueryTemplate:
        try:
            return self._doc.templates[name]
        except KeyError:
            raise PolicyError(f"unknown template: {name}")

    def _columns_with_types(self, table: str) -> list[dict[str, str]]:
        return [
            {"column": column, "type": self._column_types.get((table, column), "unknown")}
            for column in self._doc.tables[table].columns
        ]

    def filtered_schema(self) -> dict:
        """The catalog advertised to the model: only whitelisted tables/columns."""
        return {
            "schema": self.schema,
            "tables": {table: self._columns_with_types(table) for table in self._allowed},
        }

    def describe_table(self, table: str) -> dict:
        """Return the whitelisted columns (and types) of one table."""
        if not self.is_allowed_table(table):
            raise PolicyError(f"table not allowed or unknown: {table}")
        return {"schema": self.schema, "table": table, "columns": self._columns_with_types(table)}

    def validate_against_db(self, introspected: dict[str, dict[str, str]]) -> None:
        """Fail fast if the policy is inconsistent with the live database.

        Args:
            introspected: Live schema as ``{table: {column: data_type}}`` for this
                policy's schema (from ``Database.introspect``).

        Raises:
            PolicyError: If a whitelisted table/column is missing in the database, or a
                template references something outside the whitelist, or a template's
                declared parameters don't match its SQL placeholders.
        """
        for table, columns in self._allowed.items():
            live = introspected.get(table)
            if live is None:
                raise PolicyError(f"whitelisted table not found in DB: {self.schema}.{table}")
            missing = columns - live.keys()
            if missing:
                raise PolicyError(
                    f"whitelisted columns not found in {self.schema}.{table}: {sorted(missing)}"
                )
            for column in columns:
                self._column_types[(table, column)] = live[column]

        self._validate_templates()
        logger.info(
            "policy validated against DB: %d tables, %d templates",
            len(self._allowed),
            len(self._doc.templates),
        )

    def _validate_templates(self) -> None:
        for name, template in self._doc.templates.items():
            declared = set(template.parameters)
            used = placeholder_names(template.sql)
            if declared != used:
                raise PolicyError(
                    f"template '{name}': declared parameters {sorted(declared)} do not match "
                    f"SQL placeholders {sorted(used)}"
                )
            try:
                validate_template_sql(template.sql, self.schema, self._allowed)
            except QueryNotAllowed as exc:
                raise PolicyError(f"template '{name}' references non-whitelisted objects: {exc}")
