"""A minimal, DataHub-shaped MCP server (JSON-RPC 2.0 over stdio).

This lets the Steward Squad exercise a *real* Model Context Protocol loop with
zero credentials: the mock server serves a DataHub-shaped metadata graph through
the same read tools a live DataHub MCP server exposes (``search``,
``get_entities``, ``get_lineage``, ``list_schema_fields``) and, when mutations
are enabled, the same mutation tools (``update_description``, ``add_tags``,
``add_terms``, ``save_document``). Mutations update the in-memory graph so a
follow-up read proves the writeback landed.

The transport is newline-delimited JSON-RPC 2.0 on stdin/stdout, matching the
MCP stdio contract. Never print anything but JSON-RPC messages to stdout; logs
go to stderr.

Run standalone (e.g. from an MCP host):

    python3 -m datahub_steward_squad.mcp_server --fixture examples/retail_finance_graph.json --enable-mutations
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from typing import Any

from .fixtures import load_graph
from .models import Column, DataHubGraph

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "datahub-steward-mock", "version": "0.1.0"}


class DataHubMockServer:
    """Serves a DataHubGraph over MCP-style tool calls."""

    def __init__(self, graph: DataHubGraph, enable_mutations: bool = False) -> None:
        self.graph = graph
        self.enable_mutations = enable_mutations

    # -- Tool catalog ----------------------------------------------------
    def tool_definitions(self) -> list[dict[str, Any]]:
        read_tools = [
            {
                "name": "search",
                "description": "Search DataHub assets by free-text query, domain, or entity type.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "domain": {"type": "string"},
                        "entity_type": {"type": "string"},
                    },
                },
            },
            {
                "name": "get_entities",
                "description": "Fetch full metadata (schema fields, assertions, owners) for URNs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"urns": {"type": "array", "items": {"type": "string"}}},
                    "required": ["urns"],
                },
            },
            {
                "name": "get_lineage",
                "description": "Return upstream/downstream lineage edges for a URN.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "urn": {"type": "string"},
                        "direction": {"type": "string", "enum": ["upstream", "downstream", "both"]},
                        "depth": {"type": "integer"},
                    },
                    "required": ["urn"],
                },
            },
            {
                "name": "list_schema_fields",
                "description": "List schema fields with tags and glossary terms for a dataset URN.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"urn": {"type": "string"}},
                    "required": ["urn"],
                },
            },
        ]
        mutation_tools = [
            {
                "name": "update_description",
                "description": "Set the description aspect on a DataHub entity.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "urn": {"type": "string"},
                        "description": {"type": "string"},
                        "mode": {"type": "string"},
                    },
                    "required": ["urn", "description"],
                },
            },
            {
                "name": "add_tags",
                "description": "Attach tags to an entity or one of its schema fields.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "urn": {"type": "string"},
                        "field_path": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["urn", "tags"],
                },
            },
            {
                "name": "add_terms",
                "description": "Attach glossary terms to an entity or one of its schema fields.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "urn": {"type": "string"},
                        "field_path": {"type": "string"},
                        "terms": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["urn", "terms"],
                },
            },
            {
                "name": "save_document",
                "description": "Save a context document into DataHub.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "parent_folder": {"type": "string"},
                    },
                    "required": ["title", "content"],
                },
            },
        ]
        if self.enable_mutations:
            return read_tools + mutation_tools
        return read_tools

    # -- Tool execution --------------------------------------------------
    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        handler = {
            "search": self._search,
            "get_entities": self._get_entities,
            "get_lineage": self._get_lineage,
            "list_schema_fields": self._list_schema_fields,
            "update_description": self._update_description,
            "add_tags": self._add_tags,
            "add_terms": self._add_terms,
            "save_document": self._save_document,
        }.get(name)
        if handler is None:
            raise ValueError(f"Unknown tool: {name}")
        if name in {"update_description", "add_tags", "add_terms", "save_document"} and not self.enable_mutations:
            raise PermissionError(
                f"Mutation tool '{name}' is disabled. Start the server with --enable-mutations."
            )
        return handler(arguments)

    def _search(self, args: dict[str, Any]) -> Any:
        entity_type = args.get("entity_type")
        entity_types = {entity_type} if entity_type else None
        results = self.graph.search(
            query=args.get("query", ""),
            domain=args.get("domain", ""),
            entity_types=entity_types,
        )
        return [self._asset_summary(asset) for asset in results]

    def _get_entities(self, args: dict[str, Any]) -> Any:
        urns = args.get("urns", [])
        return [asdict(self.graph.assets[urn]) for urn in urns if urn in self.graph.assets]

    def _get_lineage(self, args: dict[str, Any]) -> Any:
        urn = args["urn"]
        direction = args.get("direction", "both")
        depth = int(args.get("depth", 3))
        payload: dict[str, Any] = {"urn": urn}
        if direction in {"upstream", "both"}:
            payload["upstream"] = [a.urn for a in self.graph.upstream(urn, depth=depth)]
        if direction in {"downstream", "both"}:
            payload["downstream"] = [a.urn for a in self.graph.downstream(urn, depth=depth)]
        payload["edges"] = [
            asdict(edge)
            for edge in self.graph.lineage
            if edge.upstream == urn or edge.downstream == urn
        ]
        return payload

    def _list_schema_fields(self, args: dict[str, Any]) -> Any:
        asset = self.graph.assets.get(args["urn"])
        if asset is None:
            return []
        return [asdict(column) for column in asset.columns]

    def _update_description(self, args: dict[str, Any]) -> Any:
        asset = self._require_asset(args["urn"])
        asset.description = args["description"]
        return {"ok": True, "urn": asset.urn, "description": asset.description}

    def _add_tags(self, args: dict[str, Any]) -> Any:
        asset = self._require_asset(args["urn"])
        tags = list(args.get("tags", []))
        field_path = args.get("field_path")
        if field_path:
            column = self._require_column(asset, field_path)
            column.tags = _merge(column.tags, tags)
            return {"ok": True, "urn": asset.urn, "field_path": field_path, "tags": column.tags}
        asset.tags = _merge(asset.tags, tags)
        return {"ok": True, "urn": asset.urn, "tags": asset.tags}

    def _add_terms(self, args: dict[str, Any]) -> Any:
        asset = self._require_asset(args["urn"])
        terms = list(args.get("terms", []))
        field_path = args.get("field_path")
        if field_path:
            column = self._require_column(asset, field_path)
            column.terms = _merge(column.terms, terms)
            return {"ok": True, "urn": asset.urn, "field_path": field_path, "terms": column.terms}
        asset.terms = _merge(asset.terms, terms)
        return {"ok": True, "urn": asset.urn, "terms": asset.terms}

    def _save_document(self, args: dict[str, Any]) -> Any:
        document = {
            "title": args["title"],
            "body": args["content"],
            "parent_folder": args.get("parent_folder", ""),
        }
        self.graph.documents.append(document)
        return {"ok": True, "title": document["title"], "documents": len(self.graph.documents)}

    # -- helpers ---------------------------------------------------------
    def _asset_summary(self, asset) -> dict[str, Any]:
        return {
            "urn": asset.urn,
            "name": asset.name,
            "entity_type": asset.entity_type,
            "platform": asset.platform,
            "domain": asset.domain,
            "owner": asset.owner,
            "certified": asset.certified,
            "usage_30d": asset.usage_30d,
        }

    def _require_asset(self, urn: str):
        asset = self.graph.assets.get(urn)
        if asset is None:
            raise ValueError(f"Unknown URN: {urn}")
        return asset

    def _require_column(self, asset, field_path: str) -> Column:
        for column in asset.columns:
            if column.name == field_path:
                return column
        column = Column(name=field_path, native_type="unknown")
        asset.columns.append(column)
        return column


def _merge(existing: list[str], additions: list[str]) -> list[str]:
    merged = list(existing)
    for value in additions:
        if value not in merged:
            merged.append(value)
    return merged


# -- JSON-RPC 2.0 stdio loop --------------------------------------------
def serve(server: DataHubMockServer, stdin=None, stdout=None) -> None:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = _handle(server, message)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


def _handle(server: DataHubMockServer, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    message_id = message.get("id")

    # Notifications (no id) get no response.
    if message_id is None:
        return None

    if method == "initialize":
        return _ok(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _ok(message_id, {})
    if method == "tools/list":
        return _ok(message_id, {"tools": server.tool_definitions()})
    if method == "tools/call":
        params = message.get("params", {})
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        try:
            result = server.call_tool(name, arguments)
        except (ValueError, KeyError, PermissionError) as error:
            return _ok(
                message_id,
                {"content": [{"type": "text", "text": str(error)}], "isError": True},
            )
        return _ok(
            message_id,
            {"content": [{"type": "text", "text": json.dumps(result)}], "isError": False},
        )
    if method == "shutdown":
        return _ok(message_id, {})

    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def _ok(message_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="datahub-steward-mock-mcp")
    parser.add_argument("--fixture", default="examples/retail_finance_graph.json")
    parser.add_argument("--enable-mutations", action="store_true")
    args = parser.parse_args(argv)

    graph = load_graph(args.fixture)
    server = DataHubMockServer(graph, enable_mutations=args.enable_mutations)
    print(
        f"[datahub-steward-mock] serving {len(graph.assets)} assets "
        f"(mutations={'on' if args.enable_mutations else 'off'})",
        file=sys.stderr,
    )
    serve(server)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
