"""End-to-end DataHub MCP loop: read -> analyze -> writeback -> verify.

Spins up the bundled mock DataHub MCP server, reconstructs the metadata graph
from MCP read tools, runs the steward squad, then (optionally) applies the
approved writeback proposals through MCP mutation tools and re-reads the graph
to prove the changes landed. No credentials required.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .gateway import DataHubMCPGateway
from .mcp_client import MCPStdioClient
from .orchestrator import run_squad
from .render import write_outputs


def server_command(fixture: str, enable_mutations: bool) -> list[str]:
    command = [sys.executable, "-m", "datahub_steward_squad.mcp_server", "--fixture", fixture]
    if enable_mutations:
        command.append("--enable-mutations")
    return command


def run_mcp_demo(
    fixture: str = "examples/retail_finance_graph.json",
    query: str = "revenue",
    focus_domain: str = "Finance",
    objective: str = "Run a governed DataHub stewardship loop over MCP.",
    engine: str = "auto",
    model: str | None = None,
    apply: bool = False,
    approved_ids: set[str] | None = None,
    out: str | None = None,
    cwd: str | None = None,
    log=print,
) -> dict[str, Any]:
    command = server_command(fixture, enable_mutations=apply)
    with MCPStdioClient(command, cwd=cwd) as client:
        tools = [tool["name"] for tool in client.list_tools()]
        log(f"MCP server tools: {', '.join(tools)}")

        gateway = DataHubMCPGateway(client)
        graph = gateway.build_graph(query="", domain="")
        log(f"Reconstructed graph from MCP: {len(graph.assets)} assets, {len(graph.lineage)} lineage edges")

        run = run_squad(
            graph=graph,
            objective=objective,
            query=query,
            focus_domain=focus_domain,
            engine=engine,
            model=model,
        )
        log(f"Engine: {run.engine} | Findings: {len(run.findings)} | Proposals: {len(run.proposals)}")

        outputs = {}
        if out:
            outputs = write_outputs(graph, run, Path(out))

        applied: list[dict[str, Any]] = []
        verification: list[dict[str, Any]] = []
        if apply:
            before = _snapshot(gateway, run)
            applied = gateway.apply_proposals(run.proposals, approved_ids=approved_ids)
            log("")
            log("Applied writeback via MCP mutation tools:")
            for item in applied:
                log(f"  {item['id']} {item['tool']}: {item['status']}")
            verification = _verify(gateway, run, before)
            log("")
            log("Verification (re-read through MCP):")
            for change in verification:
                log(f"  {change['urn']}: {change['field']} {change['before']!r} -> {change['after']!r}")

        return {
            "engine": run.engine,
            "findings": len(run.findings),
            "proposals": len(run.proposals),
            "outputs": {name: str(path) for name, path in outputs.items()},
            "applied": applied,
            "verification": verification,
        }


def _target_urns(run) -> list[str]:
    seen: list[str] = []
    for proposal in run.proposals:
        urn = proposal.arguments.get("urn")
        if urn and urn not in seen:
            seen.append(urn)
    return seen


def _snapshot(gateway: DataHubMCPGateway, run) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for urn in _target_urns(run):
        entity = gateway.read_asset(urn)
        if entity is not None:
            snapshot[urn] = entity
    return snapshot


def _verify(gateway: DataHubMCPGateway, run, before: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for urn, prior in before.items():
        after = gateway.read_asset(urn)
        if after is None:
            continue
        if prior.get("description", "") != after.get("description", ""):
            changes.append(
                {
                    "urn": urn,
                    "field": "description",
                    "before": _short(prior.get("description", "")),
                    "after": _short(after.get("description", "")),
                }
            )
        before_cols = {c["name"]: c for c in prior.get("columns", [])}
        for column in after.get("columns", []):
            prior_col = before_cols.get(column["name"], {})
            if prior_col.get("tags", []) != column.get("tags", []):
                changes.append(
                    {
                        "urn": urn,
                        "field": f"{column['name']}.tags",
                        "before": prior_col.get("tags", []),
                        "after": column.get("tags", []),
                    }
                )
    return changes


def _short(text: str, limit: int = 48) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"
