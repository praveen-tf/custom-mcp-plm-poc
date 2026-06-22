"""Smoke-test a running pg-mcp-server over Streamable HTTP, end to end.

Connects as a real MCP client, lists the tools, and exercises every tool path against
whatever data is loaded: the schema tools, both query templates, the open-query mode,
and the whitelist rejection path. Prints a PASS/FAIL line per check and exits non-zero
if any check fails — so it doubles as a deployment health check on the VM.

Run it after the server is up (no-auth local dev):
    uv run python scripts/smoke_test.py --url http://127.0.0.1:8000/mcp/
"""

import argparse
import asyncio
import sys
from typing import Any

from fastmcp import Client

EXPECTED_TOOLS = {
    "list_accessible_tables", "describe_table", "query",
    "get_style_by_code", "list_styles_in_collection",
}


def result_data(result: object) -> Any:
    """Pull the structured payload out of a CallToolResult across fastmcp versions."""
    return getattr(result, "data", None) or getattr(result, "content", result)


async def run(url: str) -> bool:
    checks: list[tuple[str, bool]] = []

    def check(label: str, passed: bool) -> None:
        checks.append((label, passed))
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")

    async with Client(url) as client:
        tools = {tool.name for tool in await client.list_tools()}
        check(f"tools listed: {sorted(tools)}", EXPECTED_TOOLS <= tools)

        schema = result_data(await client.call_tool("list_accessible_tables", {}))
        styles_columns = {col["column"] for col in schema["tables"]["styles"]}
        check("styles is advertised", "styles" in schema["tables"])
        check("hidden column absent from advertised schema", "_airbyte_raw_id" not in styles_columns)

        # Use the open-query path to fetch a real code + collection, then drive the templates.
        sample = result_data(await client.call_tool(
            "query", {"sql": "SELECT code, collection FROM styles LIMIT 1"}
        ))
        check("open-query SELECT returns a row", bool(sample))
        code, collection = sample[0]["code"], sample[0]["collection"]

        by_code = result_data(await client.call_tool("get_style_by_code", {"code": code}))
        check(f"get_style_by_code('{code}') returns the style", bool(by_code))

        in_collection = result_data(await client.call_tool(
            "list_styles_in_collection", {"collection": collection}
        ))
        check(f"list_styles_in_collection('{collection}') returns rows", bool(in_collection))

        # Whitelist enforcement: each of these must be REJECTED before touching the DB.
        for label, bad_sql in [
            ("non-whitelisted column rejected", "SELECT mgf_godiva_margin FROM styles"),
            ("SELECT * rejected", "SELECT * FROM styles"),
            ("write statement rejected", "DROP TABLE centric_8_plm.styles"),
        ]:
            try:
                await client.call_tool("query", {"sql": bad_sql})
                check(label, False)  # should not reach here
            except Exception:
                check(label, True)

    failed = [label for label, passed in checks if not passed]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed.")
    return not failed


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test a running pg-mcp-server.")
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp/", help="Streamable HTTP /mcp/ URL")
    args = parser.parse_args()
    if not asyncio.run(run(args.url)):
        sys.exit(1)


if __name__ == "__main__":
    main()
