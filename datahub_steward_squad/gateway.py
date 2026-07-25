"""Bridge between DataHub MCP tools and the Steward Squad's data model.

``build_graph`` reconstructs a :class:`DataHubGraph` purely from MCP *read*
tools (``search`` -> ``get_entities`` -> ``get_lineage``), exactly how a live
DataHub MCP integration would. ``apply_proposals`` executes approved writeback
proposals through MCP *mutation* tools, so the read -> analyze -> writeback loop
runs end to end over the protocol.
"""

from __future__ import annotations

from typing import Any

from .mcp_client import MCPStdioClient
from .models import Asset, DataHubGraph, LineageEdge, Proposal


class DataHubMCPGateway:
    def __init__(self, client: MCPStdioClient) -> None:
        self.client = client

    def build_graph(self, query: str = "", domain: str = "") -> DataHubGraph:
        summaries = self.client.call_tool("search", {"query": query, "domain": domain}) or []
        urns = [item["urn"] for item in summaries]
        entities = self.client.call_tool("get_entities", {"urns": urns}) or []
        assets = {entity["urn"]: Asset.from_dict(entity) for entity in entities}

        edges: dict[tuple[str, str], LineageEdge] = {}
        for urn in assets:
            lineage = self.client.call_tool("get_lineage", {"urn": urn, "direction": "both"}) or {}
            for raw in lineage.get("edges", []):
                key = (raw["upstream"], raw["downstream"])
                edges[key] = LineageEdge.from_dict(raw)

        return DataHubGraph(assets=assets, lineage=list(edges.values()))

    def apply_proposals(
        self, proposals: list[Proposal], approved_ids: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """Execute approved proposals via MCP mutation tools.

        ``approved_ids`` is the human approval gate. ``None`` means every
        proposal was approved (used by the demo); an empty set applies nothing.
        """

        results: list[dict[str, Any]] = []
        for proposal in proposals:
            approved = approved_ids is None or proposal.id in approved_ids
            if not approved:
                results.append({"id": proposal.id, "tool": proposal.tool, "status": "skipped"})
                continue
            try:
                result = self._apply_one(proposal)
                results.append(
                    {"id": proposal.id, "tool": proposal.tool, "status": "applied", "result": result}
                )
            except Exception as error:  # surface, do not abort the batch
                results.append(
                    {"id": proposal.id, "tool": proposal.tool, "status": "error", "error": str(error)}
                )
        return results

    def _apply_one(self, proposal: Proposal) -> Any:
        """Execute a single proposal via its MCP tool.

        The mock speaks the squad's proposal tool names/args directly. The live
        gateway overrides this to translate onto the real server's signatures.
        """
        return self.client.call_tool(proposal.tool, proposal.arguments)

    def read_asset(self, urn: str) -> dict[str, Any] | None:
        entities = self.client.call_tool("get_entities", {"urns": [urn]}) or []
        return entities[0] if entities else None
