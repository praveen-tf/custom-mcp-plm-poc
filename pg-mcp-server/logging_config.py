"""Logging setup for the Postgres MCP server.

Deviation from ``agent_docs/logging_guidelines.md`` (logfire + OpenObserve): this
service logs to stdout via the standard library to keep the deployment free of heavy
OpenTelemetry dependencies. If centralized tracing is later required, swap the body of
``get_logger`` for the logfire wiring described in the guideline — call sites won't change.
"""

import logging
import sys

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes structured lines to stdout (configured once)."""
    global _CONFIGURED
    if not _CONFIGURED:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
            stream=sys.stdout,
        )
        _CONFIGURED = True
    return logging.getLogger(name)
