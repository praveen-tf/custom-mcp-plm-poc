"""Shared test setup: provide required config before any module imports settings."""

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# `config.get_settings()` requires PGMCP_DATABASE_URL; set a dummy (no connection is
# made during these tests) and point at the real policy regardless of cwd.
os.environ.setdefault("PGMCP_DATABASE_URL", "postgresql://u:p@localhost:5432/db")
os.environ.setdefault("PGMCP_POLICY_PATH", str(_PROJECT_ROOT / "policy.yaml"))

POLICY_PATH = _PROJECT_ROOT / "policy.yaml"
