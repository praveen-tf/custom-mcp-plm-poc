"""Tests for the policy data models."""

import pytest
import yaml
from pydantic import ValidationError

from conftest import POLICY_PATH
from models import PolicyDocument, TemplateParameter


def test_policy_document_parses_real_policy():
    document = PolicyDocument.model_validate(yaml.safe_load(POLICY_PATH.read_text()))
    assert document.db_schema == "centric_8_plm"
    assert "styles" in document.tables
    assert "get_style_by_code" in document.templates


def test_table_policy_requires_at_least_one_column():
    with pytest.raises(ValidationError):
        PolicyDocument.model_validate({"schema": "s", "tables": {"t": {"columns": []}}})


def test_template_parameter_defaults():
    param = TemplateParameter()
    assert param.type == "str"
    assert param.required is True
    assert param.default is None
