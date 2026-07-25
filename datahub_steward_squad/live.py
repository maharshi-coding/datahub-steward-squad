"""Live DataHub MCP integration.

Launches the **real** ``mcp-server-datahub`` (via ``uvx``) and adapts its
GraphQL-shaped tool responses into the Steward Squad's :class:`DataHubGraph`
model. The bundled offline mock (:mod:`.mcp_server`) and the default
``DataHubMCPGateway`` are left completely intact — this module is the live
counterpart, selected with ``mcp-demo --live``.

The real server's tool *names* overlap with the mock (``search``,
``get_entities``, ``get_lineage``, ``update_description``, ``add_tags`` ...) but
its argument schemas and response shapes are entirely different (nested,
camelCase GraphQL). :class:`LiveDataHubMCPGateway` bridges that gap and
:func:`translate_proposal` maps the squad's writeback proposals onto the real
mutation tools' signatures.

Importing this module is stdlib-only. Actually *running* the live loop needs
``uv``/``uvx`` and network access to a DataHub GMS (the optional ``live``
extra) — nothing the offline path depends on.
"""

from __future__ import annotations

import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .gateway import DataHubMCPGateway
from .models import Asset, Column, DataHubGraph, LineageEdge, Proposal

# The official self-hosted DataHub MCP server. Override with DATAHUB_MCP_COMMAND
# (space-separated) to pin a version or use a different launcher.
DEFAULT_MCP_COMMAND = ["uvx", "mcp-server-datahub@latest"]

# Document type accepted by the real save_document tool (see its inputSchema).
STEWARD_DOCUMENT_TYPE = "Summary"


class LiveConfigError(RuntimeError):
    """Raised when live-mode configuration (e.g. DATAHUB_GMS_URL) is missing."""


# --------------------------------------------------------------------------- #
# Configuration / process launch
# --------------------------------------------------------------------------- #
def load_dotenv(path: str | os.PathLike = ".env") -> dict[str, str]:
    """Minimal stdlib ``.env`` loader.

    Sets each ``KEY=VALUE`` into ``os.environ`` (without overwriting values that
    are already set), and returns the parsed mapping. No-op if the file is
    absent. Deliberately dependency-free — no python-dotenv.
    """
    loaded: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return loaded
    for raw_line in p.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        loaded[key] = value
        os.environ.setdefault(key, value)
    return loaded


def live_server_command() -> list[str]:
    override = os.environ.get("DATAHUB_MCP_COMMAND")
    if override:
        return override.split()
    return list(DEFAULT_MCP_COMMAND)


def live_server_env(enable_mutations: bool) -> dict[str, str]:
    """Build the child-process environment for the real MCP server.

    ``DATAHUB_GMS_URL`` is required. ``DATAHUB_GMS_TOKEN`` is optional (a local
    quickstart with ``METADATA_SERVICE_AUTH_ENABLED=false`` needs no token; a
    token is required for DataHub Cloud or when GMS auth is enabled).
    """
    url = os.environ.get("DATAHUB_GMS_URL")
    if not url:
        raise LiveConfigError(
            "DATAHUB_GMS_URL is not set. Copy .env.example to .env and set your "
            "DataHub GMS URL (e.g. http://localhost:8080), or export it directly. "
            "See docs/datahub_mcp_setup.md."
        )
    env = {
        "DATAHUB_GMS_URL": url,
        "TOOLS_IS_MUTATION_ENABLED": "true" if enable_mutations else "false",
    }
    token = os.environ.get("DATAHUB_GMS_TOKEN")
    if token:
        env["DATAHUB_GMS_TOKEN"] = token
    return env


# --------------------------------------------------------------------------- #
# Response adapter: real GraphQL shapes -> DataHubGraph model
# --------------------------------------------------------------------------- #
def _custom_props(raw: dict[str, Any]) -> dict[str, str]:
    """DataHub returns customProperties as ``[{"key","value"}]``; flatten it."""
    props = (raw.get("properties") or {}).get("customProperties") or []
    out: dict[str, str] = {}
    for item in props:
        if isinstance(item, dict) and "key" in item:
            out[str(item["key"])] = str(item.get("value", ""))
    return out


def _platform_name(raw: dict[str, Any]) -> str:
    plat = raw.get("platform")
    if isinstance(plat, dict):
        if plat.get("name"):
            return plat["name"]
        urn = plat.get("urn", "")
        if urn:
            return urn.split(":")[-1]
    # Fall back to parsing the dataset URN: urn:li:dataset:(urn:li:dataPlatform:X,...)
    urn = raw.get("urn", "")
    marker = "dataPlatform:"
    if marker in urn:
        return urn.split(marker, 1)[1].split(",")[0].strip(")")
    return "unknown"


def _owner_urn(raw: dict[str, Any]) -> str:
    owners = (raw.get("ownership") or {}).get("owners") or []
    if owners:
        return (owners[0].get("owner") or {}).get("urn", "") or ""
    return ""


def _entity_tags(raw: dict[str, Any]) -> list[str]:
    tags = (raw.get("tags") or {}).get("tags") or []
    out: list[str] = []
    for item in tags:
        tag = item.get("tag") or {}
        name = (tag.get("properties") or {}).get("name")
        value = name or tag.get("urn", "")
        if value:
            out.append(value)
    return out


def _entity_terms(raw: dict[str, Any]) -> list[str]:
    terms = (raw.get("glossaryTerms") or {}).get("terms") or []
    out: list[str] = []
    for item in terms:
        term = item.get("term") or {}
        value = term.get("urn") or (term.get("properties") or {}).get("name") or ""
        if value:
            out.append(value)
    return out


def _field_name_list(value: Any) -> list[str]:
    """Field-level tags/glossaryTerms come back as name strings; stay defensive."""
    out: list[str] = []
    for item in value or []:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            candidate = item.get("name") or item.get("urn")
            if candidate:
                out.append(candidate)
    return out


def _dedupe(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
    return seen


def _columns(raw: dict[str, Any]) -> list[Column]:
    fields = (raw.get("schemaMetadata") or {}).get("fields") or []
    cols: list[Column] = []
    for field in fields:
        # The real server merges editableSchemaMetadata (where add_tags /
        # update_description writes land) into each field under "edited*" keys,
        # separate from the ingested schemaMetadata values. Combine both so a
        # writeback is visible on re-read.
        tags = _dedupe(
            _field_name_list(field.get("tags") or field.get("globalTags"))
            + _field_name_list(field.get("editedTags"))
        )
        terms = _dedupe(
            _field_name_list(field.get("glossaryTerms"))
            + _field_name_list(field.get("editedGlossaryTerms"))
        )
        cols.append(
            Column(
                name=field.get("fieldPath", ""),
                native_type=field.get("nativeDataType") or field.get("type") or "unknown",
                description=field.get("editedDescription") or field.get("description", "") or "",
                tags=tags,
                terms=terms,
            )
        )
    return cols


def _domain_name(raw: dict[str, Any], custom: dict[str, str]) -> str:
    dom = (raw.get("domain") or {}).get("domain") or {}
    name = (dom.get("properties") or {}).get("name")
    return name or custom.get("domain", "")


def _entity_type_from_urn(urn: str) -> str:
    prefixes = {
        "urn:li:dataset:": "dataset",
        "urn:li:dashboard:": "dashboard",
        "urn:li:mlModel:": "mlmodel",
        "urn:li:dataJob:": "datajob",
        "urn:li:chart:": "chart",
    }
    for prefix, kind in prefixes.items():
        if urn.startswith(prefix):
            return kind
    return "dataset"


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def parse_entity(raw: dict[str, Any]) -> Asset:
    """Adapt one real ``get_entities`` entity into an :class:`Asset`."""
    urn = raw.get("urn", "")
    custom = _custom_props(raw)
    props = raw.get("properties") or {}
    editable = raw.get("editableProperties") or {}
    name = props.get("name") or raw.get("name") or urn
    # editableProperties.description is where update_description writes land; it
    # is the effective description in DataHub, so prefer it over the ingested one.
    description = editable.get("description") or props.get("description") or ""
    return Asset(
        urn=urn,
        name=name,
        entity_type=_entity_type_from_urn(urn),
        platform=_platform_name(raw),
        env=custom.get("env", "PROD"),
        domain=_domain_name(raw, custom),
        owner=_owner_urn(raw),
        description=description,
        tags=_entity_tags(raw),
        terms=_entity_terms(raw),
        columns=_columns(raw),
        assertions=[],  # not exposed by the read tools the gateway uses
        usage_30d=_to_int(custom.get("usage_30d", "0")),
        certified=str(custom.get("certified", "")).lower() == "true",
        properties={"table": custom.get("table", name)},
    )


# --------------------------------------------------------------------------- #
# Mutation translation: squad proposals -> real tool signatures
# --------------------------------------------------------------------------- #
def translate_proposal(proposal: Proposal) -> tuple[str, dict[str, Any]]:
    """Map a squad :class:`Proposal` onto the real MCP mutation tool + args.

    The squad's proposals use the mock's argument names (``urn``, ``field_path``,
    ``mode`` ...). The real tools use different names (``entity_urn``,
    ``column_paths``, ``operation`` ...) and batch shapes.
    """
    tool = proposal.tool
    args = proposal.arguments

    if tool == "update_description":
        translated: dict[str, Any] = {
            "entity_urn": args["urn"],
            "operation": args.get("mode", "replace"),
            "description": args.get("description", ""),
        }
        if args.get("field_path"):
            translated["column_path"] = args["field_path"]
        return "update_description", translated

    if tool == "add_tags":
        return "add_tags", {
            "tag_urns": list(args.get("tags", [])),
            "entity_urns": [args["urn"]],
            "column_paths": [args.get("field_path")],
        }

    if tool == "add_terms":
        return "add_terms", {
            "term_urns": list(args.get("terms", [])),
            "entity_urns": [args["urn"]],
            "column_paths": [args.get("field_path")],
        }

    if tool == "save_document":
        return "save_document", {
            "document_type": STEWARD_DOCUMENT_TYPE,
            "title": args.get("title", "Steward Squad Risk Brief"),
            "content": args.get("content", ""),
        }

    # Unknown tool: pass through unchanged.
    return tool, args


# --------------------------------------------------------------------------- #
# Live gateway
# --------------------------------------------------------------------------- #
class LiveDataHubMCPGateway(DataHubMCPGateway):
    """Gateway backed by the real ``mcp-server-datahub``.

    Overrides the three seams that differ from the mock: graph reconstruction
    (:meth:`build_graph`), single-entity re-read (:meth:`read_asset`, used by
    verification), and mutation execution (:meth:`_apply_one`, via
    :func:`translate_proposal`). The approval-gate loop in
    :meth:`DataHubMCPGateway.apply_proposals` is reused unchanged.
    """

    #: Datasets are what the squad analyzes; cap the catalog sweep.
    SEARCH_LIMIT = 50

    def build_graph(self, query: str = "", domain: str = "") -> DataHubGraph:
        results = (
            self.client.call_tool(
                "search",
                {
                    "query": query or "*",
                    "filter": "entity_type = dataset",
                    "num_results": self.SEARCH_LIMIT,
                },
            )
            or {}
        )
        urns = [
            (sr.get("entity") or {}).get("urn")
            for sr in results.get("searchResults", [])
            if (sr.get("entity") or {}).get("urn")
        ]

        assets: dict[str, Asset] = {}
        if urns:
            entities = self.client.call_tool("get_entities", {"urns": urns}) or []
            if isinstance(entities, dict):
                entities = [entities]
            for entity in entities:
                if not isinstance(entity, dict) or entity.get("error") or "urn" not in entity:
                    continue
                asset = parse_entity(entity)
                assets[asset.urn] = asset

        edges: dict[tuple[str, str], LineageEdge] = {}
        for urn in list(assets):
            for block_key, is_upstream in (("upstreams", True), ("downstreams", False)):
                resp = (
                    self.client.call_tool(
                        "get_lineage", {"urn": urn, "upstream": is_upstream, "max_hops": 1}
                    )
                    or {}
                )
                block = resp.get(block_key) or {}
                for sr in block.get("searchResults", []):
                    # max_hops=1 keeps only direct neighbours; guard on degree anyway.
                    if sr.get("degree") not in (1, None):
                        continue
                    other = (sr.get("entity") or {}).get("urn")
                    if not other:
                        continue
                    upstream, downstream = (other, urn) if is_upstream else (urn, other)
                    edges[(upstream, downstream)] = LineageEdge(
                        upstream=upstream, downstream=downstream
                    )

        return DataHubGraph(assets=assets, lineage=list(edges.values()))

    def read_asset(self, urn: str) -> dict[str, Any] | None:
        entities = self.client.call_tool("get_entities", {"urns": [urn]}) or []
        if isinstance(entities, dict):
            entities = [entities]
        for entity in entities:
            if isinstance(entity, dict) and entity.get("urn") == urn and not entity.get("error"):
                return asdict(parse_entity(entity))
        return None

    def _apply_one(self, proposal: Proposal) -> Any:
        tool, arguments = translate_proposal(proposal)
        return self.client.call_tool(tool, arguments)
