"""Pydantic models describing the access policy (whitelist + query templates).

These mirror the structure of ``policy.yaml``. The policy is the single source of
truth for what the model may reach: any table or column not listed here is invisible
and rejected before any SQL runs.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ParamType = Literal["str", "int", "float", "bool"]


class TemplateParameter(BaseModel):
    """A single parameter accepted by a query template."""

    type: ParamType = "str"
    required: bool = True
    default: str | int | float | bool | None = None
    description: str = ""


class QueryTemplate(BaseModel):
    """A pre-defined, parameterized query. The model fills in parameters only."""

    description: str = ""
    sql: str
    parameters: dict[str, TemplateParameter] = Field(default_factory=dict)


class TablePolicy(BaseModel):
    """The whitelisted columns for a single table."""

    columns: list[str] = Field(..., min_length=1)


class PolicyDocument(BaseModel):
    """The full parsed ``policy.yaml`` document."""

    model_config = ConfigDict(populate_by_name=True)

    # ``schema`` would shadow a BaseModel attribute, so store it as ``db_schema``.
    db_schema: str = Field(..., alias="schema")
    tables: dict[str, TablePolicy]
    templates: dict[str, QueryTemplate] = Field(default_factory=dict)
