"""Chief Steward reasoning pass.

The five deterministic agents produce *grounded* findings and proposals — facts
pulled straight from the DataHub graph. This pass turns those facts into the
steward-facing decision layer: an executive summary and a prioritized
remediation plan.

When a Claude engine is available the reasoning is genuinely agentic: the model
reads the grounded findings and writes the plan. Findings and MCP proposals stay
deterministic and evidence-backed, so the narrative can never invent risks that
are not in the graph. Without an API key the same structure is produced from a
deterministic template, so the project always runs.
"""

from __future__ import annotations

import json
from typing import Any

from .llm import LLMClient, LLMConfig, LLMUnavailable, resolve_config
from .models import DataHubGraph, SquadRun

SYSTEM_PROMPT = (
    "You are the Chief Steward coordinating a DataHub metadata governance squad. "
    "You are given grounded findings that were detected deterministically from a "
    "DataHub metadata graph (URNs, lineage, assertions, PII heuristics). Your job "
    "is to reason over them and produce a crisp steward decision brief. "
    "Rules: only reference findings that are provided; never invent assets, URNs, "
    "or risks; keep it practical and specific; assume every metadata mutation is "
    "approval-gated. Respond with STRICT JSON only, no prose, no code fences."
)

RESPONSE_SHAPE = {
    "headline": "one-sentence executive headline",
    "executive_summary": "2-4 sentence markdown summary for a data leader",
    "prioritized_actions": [
        {
            "rank": 1,
            "title": "short action title",
            "why": "one sentence on business/technical risk",
            "urgency": "now | soon | monitor",
            "asset_urn": "urn of the primary affected asset",
            "finding_ids": ["FINDING-ID"],
        }
    ],
    "reviewer_note": "one sentence reminding the human reviewer what to check before approving",
}


def apply_reasoning(
    graph: DataHubGraph,
    run: SquadRun,
    engine: str = "auto",
    model: str | None = None,
    client: LLMClient | None = None,
) -> None:
    """Populate ``run.narrative`` and ``run.engine`` based on the chosen engine.

    ``engine`` is one of ``auto`` (LLM when a key exists, else deterministic),
    ``llm`` (require an LLM; raise if unavailable), or ``deterministic``.
    """

    engine = (engine or "auto").lower()
    if engine == "deterministic":
        run.engine = "deterministic"
        run.narrative = _deterministic_narrative(graph, run)
        return

    resolved_client = client or _build_client(model)
    if resolved_client is None:
        if engine == "llm":
            raise LLMUnavailable(
                "engine='llm' requires ANTHROPIC_API_KEY. "
                "Set the key or use --engine auto/deterministic."
            )
        run.engine = "deterministic"
        run.narrative = _deterministic_narrative(graph, run)
        return

    try:
        narrative = _llm_narrative(graph, run, resolved_client)
    except (LLMUnavailable, ValueError, KeyError, json.JSONDecodeError) as error:
        if engine == "llm":
            raise
        run.engine = "deterministic"
        run.narrative = _deterministic_narrative(graph, run)
        run.narrative["fallback_reason"] = str(error)
        return

    run.engine = "llm"
    run.narrative = narrative


def _build_client(model: str | None) -> LLMClient | None:
    config: LLMConfig | None = resolve_config(model)
    if config is None:
        return None
    return LLMClient(config)


def _llm_narrative(graph: DataHubGraph, run: SquadRun, client: LLMClient) -> dict[str, Any]:
    context = _build_context(graph, run)
    prompt = (
        "DataHub steward run context (JSON):\n"
        f"{json.dumps(context, indent=2)}\n\n"
        "Produce a steward decision brief that matches EXACTLY this JSON shape:\n"
        f"{json.dumps(RESPONSE_SHAPE, indent=2)}\n\n"
        "Rank the actions by real operational risk (certified + high-usage assets, "
        "failing assertions, and unclassified PII come first). Return JSON only."
    )
    raw = client.complete(system=SYSTEM_PROMPT, prompt=prompt)
    narrative = _parse_json(raw)
    narrative["generated_by"] = client.config.model
    narrative["engine"] = "llm"
    narrative.setdefault("headline", "")
    narrative.setdefault("executive_summary", "")
    narrative.setdefault("prioritized_actions", [])
    narrative.setdefault("reviewer_note", "")
    return narrative


def _build_context(graph: DataHubGraph, run: SquadRun) -> dict[str, Any]:
    findings = []
    for finding in run.findings[:12]:
        asset = graph.assets.get(finding.asset_urn)
        findings.append(
            {
                "id": finding.id,
                "severity": finding.severity,
                "score": finding.score,
                "title": finding.title,
                "asset": asset.name if asset else finding.asset_urn,
                "asset_urn": finding.asset_urn,
                "certified": bool(asset.certified) if asset else False,
                "usage_30d": asset.usage_30d if asset else 0,
                "recommendation": finding.recommendation,
                "evidence": finding.evidence[:4],
            }
        )
    return {
        "objective": run.objective,
        "focus_domain": run.focus_domain or "all",
        "query": run.query or "*",
        "metrics": run.metrics,
        "assets_inspected": len(run.selected_asset_urns),
        "findings": findings,
        "proposed_mutations": [
            {"id": proposal.id, "tool": proposal.tool, "description": proposal.description}
            for proposal in run.proposals
        ],
    }


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM response did not contain a JSON object")
    return json.loads(text[start : end + 1])


def _deterministic_narrative(graph: DataHubGraph, run: SquadRun) -> dict[str, Any]:
    critical = [item for item in run.findings if item.severity == "critical"]
    high = [item for item in run.findings if item.severity == "high"]
    top = run.findings[:5]

    if critical:
        headline = (
            f"{len(critical)} critical governance risk(s) on certified {run.focus_domain or ''} "
            "assets need steward action before downstream consumers are affected."
        ).replace("  ", " ")
    elif high:
        headline = (
            f"{len(high)} high-severity metadata risk(s) detected across "
            f"{len(run.selected_asset_urns)} inspected asset(s)."
        )
    else:
        headline = (
            f"{len(run.findings)} metadata coverage gap(s) detected; no critical risks."
        )

    summary = (
        f"The steward squad inspected {len(run.selected_asset_urns)} DataHub asset(s) in the "
        f"{run.focus_domain or 'all'} domain and surfaced {len(run.findings)} finding(s): "
        f"{len(critical)} critical, {len(high)} high. "
        f"{run.metrics.get('failing_assertions', 0)} failing assertion(s) and "
        f"{run.metrics.get('pii_classification_gaps', 0)} PII classification gap(s) were found. "
        f"{len(run.proposals)} approval-gated DataHub MCP writeback proposal(s) are ready for review."
    )

    urgency_by_severity = {"critical": "now", "high": "soon", "medium": "monitor", "low": "monitor"}
    actions = []
    for rank, finding in enumerate(top, start=1):
        actions.append(
            {
                "rank": rank,
                "title": finding.title,
                "why": finding.recommendation,
                "urgency": urgency_by_severity.get(finding.severity, "monitor"),
                "asset_urn": finding.asset_urn,
                "finding_ids": [finding.id],
            }
        )

    return {
        "generated_by": "deterministic",
        "engine": "deterministic",
        "headline": headline,
        "executive_summary": summary,
        "prioritized_actions": actions,
        "reviewer_note": (
            "Confirm each affected URN and evidence in risk_report.md before approving any "
            "mutation in datahub_mcp_writeback_plan.json."
        ),
    }
