"""Probe the REAL mcp-server-datahub and record its actual interface.

Launches ``uvx mcp-server-datahub@latest`` through our MCPStdioClient, calls
tools/list plus sample tools/call for the read tools the gateway uses, and dumps
the raw JSON to tests/fixtures/live/ so the live adapter can be built against
real shapes (and tested with recorded fixtures).

    set -a && source .env && set +a
    python scripts/explore_live_mcp.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from datahub_steward_squad.mcp_client import MCPStdioClient

OUT = Path("tests/fixtures/live")
TARGET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)"


def _dump(name: str, obj) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(f"  wrote tests/fixtures/live/{name}.json")


def main() -> int:
    env = {
        "DATAHUB_GMS_URL": os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080"),
        "TOOLS_IS_MUTATION_ENABLED": os.environ.get("TOOLS_IS_MUTATION_ENABLED", "true"),
    }
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    if token:
        env["DATAHUB_GMS_TOKEN"] = token

    command = ["uvx", "mcp-server-datahub@latest"]
    print(f"Launching: {' '.join(command)}  (GMS={env['DATAHUB_GMS_URL']})")

    with MCPStdioClient(command, env=env) as client:
        tools = client.list_tools()
        names = [t["name"] for t in tools]
        print(f"\ntools/list -> {len(tools)} tools:")
        for t in tools:
            print(f"  - {t['name']}")
        _dump("tools_list", tools)

        print("\nsearch(query='*', filter='entity_type = dataset')")
        search = client.call_tool(
            "search", {"query": "*", "filter": "entity_type = dataset", "num_results": 10}
        )
        _dump("search", search)

        print(f"\nget_entities([{TARGET}])")
        entities = client.call_tool("get_entities", {"urns": [TARGET]})
        _dump("get_entities", entities)

        print(f"\nlist_schema_fields({TARGET})")
        fields = client.call_tool("list_schema_fields", {"urn": TARGET})
        _dump("list_schema_fields", fields)

        print(f"\nget_lineage({TARGET}, upstream=True)")
        up = client.call_tool("get_lineage", {"urn": TARGET, "upstream": True, "max_hops": 3})
        _dump("get_lineage_upstream", up)

        print(f"\nget_lineage({TARGET}, upstream=False)")
        down = client.call_tool("get_lineage", {"urn": TARGET, "upstream": False, "max_hops": 3})
        _dump("get_lineage_downstream", down)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
