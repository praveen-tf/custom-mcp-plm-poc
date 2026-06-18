"""Tests for the access policy: whitelist enforcement and DB-consistency validation."""

import pytest

from access_policy import AccessPolicy, PolicyError
from conftest import POLICY_PATH
from models import PolicyDocument


def _real_policy() -> AccessPolicy:
    return AccessPolicy.from_file(POLICY_PATH)


def _introspected_from(policy: AccessPolicy) -> dict[str, dict[str, str]]:
    """Build a fake live schema that satisfies the policy (plus an extra hidden column)."""
    live = {table: {col: "text" for col in cols} for table, cols in policy.allowlist.items()}
    live["styles"]["password_hash"] = "text"  # exists in DB but not whitelisted
    return live


def test_from_file_loads_real_policy():
    policy = _real_policy()
    assert policy.schema == "centric_8_plm"
    assert policy.is_allowed_table("styles")
    assert not policy.is_allowed_table("users")


def test_sensitive_and_internal_columns_are_hidden():
    policy = _real_policy()
    assert policy.is_allowed_column("styles", "code")
    assert not policy.is_allowed_column("styles", "_airbyte_raw_id")
    assert not policy.is_allowed_column("styles", "mgf_godiva_margin")
    assert not policy.is_allowed_column("styles", "password_hash")


def test_filtered_schema_excludes_non_whitelisted():
    schema = _real_policy().filtered_schema()
    styles_cols = {entry["column"] for entry in schema["tables"]["styles"]}
    assert "code" in styles_cols
    assert "_airbyte_raw_id" not in styles_cols


def test_describe_table_rejects_unknown_table():
    with pytest.raises(PolicyError):
        _real_policy().describe_table("not_a_table")


def test_validate_against_db_happy_caches_types():
    policy = _real_policy()
    policy.validate_against_db(_introspected_from(policy))
    types = {entry["column"]: entry["type"] for entry in policy.describe_table("styles")["columns"]}
    assert types["code"] == "text"


def test_validate_against_db_missing_table():
    policy = _real_policy()
    live = _introspected_from(policy)
    del live["seasons"]
    with pytest.raises(PolicyError):
        policy.validate_against_db(live)


def test_validate_against_db_missing_column():
    policy = _real_policy()
    live = _introspected_from(policy)
    live["styles"].pop("code")
    with pytest.raises(PolicyError):
        policy.validate_against_db(live)


def test_template_referencing_disallowed_column_rejected():
    document = PolicyDocument.model_validate(
        {
            "schema": "centric_8_plm",
            "tables": {"styles": {"columns": ["id", "code"]}},
            "templates": {
                "bad": {
                    "sql": "SELECT ssn FROM styles WHERE id = %(id)s",
                    "parameters": {"id": {"type": "str"}},
                }
            },
        }
    )
    policy = AccessPolicy(document)
    with pytest.raises(PolicyError):
        policy.validate_against_db({"styles": {"id": "text", "code": "text", "ssn": "text"}})


def test_template_parameter_mismatch_rejected():
    document = PolicyDocument.model_validate(
        {
            "schema": "centric_8_plm",
            "tables": {"styles": {"columns": ["id", "code"]}},
            "templates": {
                "bad": {
                    "sql": "SELECT code FROM styles WHERE id = %(id)s",
                    "parameters": {"wrong_name": {"type": "str"}},
                }
            },
        }
    )
    policy = AccessPolicy(document)
    with pytest.raises(PolicyError):
        policy.validate_against_db({"styles": {"id": "text", "code": "text"}})
