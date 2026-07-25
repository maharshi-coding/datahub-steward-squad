from __future__ import annotations

import html
import json
from dataclasses import asdict
from pathlib import Path

from .models import DataHubGraph, SquadRun


def write_outputs(graph: DataHubGraph, run: SquadRun, out_dir: str | Path) -> dict[str, Path]:
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)

    outputs = {
        "summary": target / "run_summary.json",
        "risk_report": target / "risk_report.md",
        "executive_summary": target / "executive_summary.md",
        "mcp_plan": target / "datahub_mcp_writeback_plan.json",
        "sql": target / "generated_quality_sql.sql",
        "board": target / "team_board.json",
        "document": target / "steward_squad_document.md",
        "dashboard": target / "dashboard.html",
    }

    _write_json(outputs["summary"], run.as_dict())
    _write_json(outputs["mcp_plan"], _mcp_plan(run))
    _write_json(outputs["board"], [asdict(card) for card in run.team_cards])
    outputs["risk_report"].write_text(render_risk_report(graph, run), encoding="utf-8")
    outputs["executive_summary"].write_text(render_executive_summary(run), encoding="utf-8")
    outputs["sql"].write_text(run.generated_sql, encoding="utf-8")
    outputs["document"].write_text(run.steward_document, encoding="utf-8")
    outputs["dashboard"].write_text(render_dashboard(graph, run), encoding="utf-8")
    return outputs


def render_executive_summary(run: SquadRun) -> str:
    narrative = run.narrative or {}
    generated_by = narrative.get("generated_by", "deterministic")
    engine_label = "Claude" if run.engine == "llm" else "Deterministic template"
    lines = [
        "# Chief Steward Brief",
        "",
        f"> {narrative.get('headline', 'No headline generated.')}",
        "",
        f"- Reasoning engine: **{engine_label}** (`{generated_by}`)",
        f"- Objective: {run.objective}",
        f"- Focus domain: `{run.focus_domain or 'all'}`",
        "",
        "## Executive Summary",
        "",
        narrative.get("executive_summary", "No summary generated."),
        "",
        "## Prioritized Actions",
        "",
    ]
    actions = narrative.get("prioritized_actions", [])
    if not actions:
        lines.append("_No prioritized actions._")
    for action in actions:
        urgency = str(action.get("urgency", "monitor")).upper()
        finding_ids = ", ".join(action.get("finding_ids", [])) or "none"
        lines.extend(
            [
                f"{action.get('rank', '-')}. **[{urgency}] {action.get('title', 'Action')}**",
                f"   - Why: {action.get('why', '')}",
                f"   - Asset: `{action.get('asset_urn', '')}`",
                f"   - Related findings: {finding_ids}",
            ]
        )
    lines.extend(
        [
            "",
            "## Reviewer Note",
            "",
            narrative.get("reviewer_note", "Review all evidence before approving mutations."),
        ]
    )
    if narrative.get("fallback_reason"):
        lines.extend(["", f"> LLM fallback: {narrative['fallback_reason']}"])
    return "\n".join(lines) + "\n"


def render_risk_report(graph: DataHubGraph, run: SquadRun) -> str:
    narrative = run.narrative or {}
    engine_label = "Claude" if run.engine == "llm" else "deterministic"
    lines = [
        "# DataHub Steward Squad Risk Report",
        "",
        f"Objective: {run.objective}",
        f"Query: `{run.query or '*'}`",
        f"Focus domain: `{run.focus_domain or 'all'}`",
        f"Reasoning engine: `{engine_label}` ({narrative.get('generated_by', 'deterministic')})",
        f"Started at: `{run.started_at}`",
        "",
        "## Chief Steward Brief",
        "",
        f"> {narrative.get('headline', 'No headline generated.')}",
        "",
        narrative.get("executive_summary", ""),
        "",
        "## Scorecard",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
    ]
    for key, value in sorted(run.metrics.items()):
        lines.append(f"| {key.replace('_', ' ').title()} | {value} |")

    lines.extend(["", "## Findings", ""])
    for finding in run.findings:
        asset = graph.assets.get(finding.asset_urn)
        lines.extend(
            [
                f"### {finding.id} - {finding.severity.upper()} - {finding.title}",
                "",
                f"- Asset: `{asset.name if asset else finding.asset_urn}`",
                f"- URN: `{finding.asset_urn}`",
                f"- Agent: {finding.agent}",
                f"- Score: {finding.score}",
                f"- Recommendation: {finding.recommendation}",
                f"- Suggested DataHub tools: {', '.join(finding.suggested_tools) or 'none'}",
                "- Evidence:",
            ]
        )
        lines.extend([f"  - {item}" for item in finding.evidence])
        lines.append("")

    lines.extend(["## Proposed DataHub MCP Mutations", ""])
    for proposal in run.proposals:
        lines.extend(
            [
                f"### {proposal.id} - `{proposal.tool}`",
                "",
                proposal.description,
                "",
                f"- Requires approval: `{str(proposal.requires_approval).lower()}`",
                f"- Related findings: {', '.join(proposal.finding_ids) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def render_dashboard(graph: DataHubGraph, run: SquadRun) -> str:
    severity_counts = {
        severity: sum(1 for item in run.findings if item.severity == severity)
        for severity in ["critical", "high", "medium", "low"]
    }
    narrative = run.narrative or {}
    engine_llm = run.engine == "llm"
    engine_label = "Claude reasoning" if engine_llm else "Deterministic engine"
    engine_model = html.escape(str(narrative.get("generated_by", "deterministic")))

    top_findings = run.findings[:6]
    rows = "\n".join(
        f"""
        <tr>
          <td><span class="pill sev-{html.escape(finding.severity)}">{html.escape(finding.severity.upper())}</span></td>
          <td>{html.escape(finding.title)}</td>
          <td><code>{html.escape(finding.asset_urn)}</code></td>
          <td class="num">{finding.score}</td>
        </tr>
        """
        for finding in top_findings
    )

    actions = narrative.get("prioritized_actions", [])
    action_items = "\n".join(
        f"""
        <li class="action">
          <span class="rank">{html.escape(str(action.get('rank', '-')))}</span>
          <div>
            <div class="action-head">
              <strong>{html.escape(str(action.get('title', 'Action')))}</strong>
              <span class="pill urg-{html.escape(str(action.get('urgency', 'monitor')).lower())}">{html.escape(str(action.get('urgency', 'monitor')).upper())}</span>
            </div>
            <p>{html.escape(str(action.get('why', '')))}</p>
            <code>{html.escape(str(action.get('asset_urn', '')))}</code>
          </div>
        </li>
        """
        for action in actions
    ) or '<li class="action"><div><p>No prioritized actions.</p></div></li>'

    cards = "\n".join(
        f"""
        <section class="agent">
          <h3>{html.escape(card.owner)}</h3>
          <p>{html.escape(card.title)}</p>
          <strong>{html.escape(card.state.upper())}</strong>
        </section>
        """
        for card in run.team_cards
    )
    metric_items = "\n".join(
        f"<li><span>{html.escape(key.replace('_', ' ').title())}</span><strong>{html.escape(str(value))}</strong></li>"
        for key, value in sorted(run.metrics.items())
    )
    inspected = "\n".join(
        f"<li><code>{html.escape(graph.assets[urn].name)}</code><span>{html.escape(graph.assets[urn].platform)}</span></li>"
        for urn in run.selected_asset_urns
        if urn in graph.assets
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DataHub Steward Squad Dashboard</title>
  <style>
    :root {{
      color-scheme: light dark;
      --ink: #18212f;
      --muted: #5e6b7d;
      --line: #d7dee8;
      --panel: #ffffff;
      --bg: #f4f7fb;
      --hero: #0d1b2f;
      --hero-ink: #eaf1fb;
      --hero-muted: #a9bdd6;
      --accent: #14b8a6;
      --crit: #b42318;
      --high: #b54708;
      --med: #7a5c00;
      --now: #b42318;
      --soon: #b54708;
      --monitor: #475569;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --ink: #e7edf6;
        --muted: #9aa7b8;
        --line: #26303f;
        --panel: #131c28;
        --bg: #0b111a;
        --hero: #0a1522;
        --crit: #f87171;
        --high: #fbbf24;
        --med: #fcd34d;
        --now: #f87171;
        --soon: #fbbf24;
        --monitor: #94a3b8;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--bg);
    }}
    header {{
      padding: 36px clamp(20px, 5vw, 72px) 30px;
      background: radial-gradient(1200px 400px at 15% -10%, #1b3a5c 0%, var(--hero) 60%);
      color: var(--hero-ink);
    }}
    .eyebrow {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom: 14px; }}
    .badge {{
      display:inline-flex; align-items:center; gap:8px;
      background: rgba(20,184,166,.16); color: #7fe7d8;
      border: 1px solid rgba(20,184,166,.5);
      padding: 6px 12px; border-radius: 999px; font-size:.8rem; font-weight:600;
      letter-spacing:.02em;
    }}
    .badge .dot {{ width:8px; height:8px; border-radius:50%; background: var(--accent); }}
    .badge.det {{ background: rgba(148,163,184,.14); color:#cbd5e1; border-color: rgba(148,163,184,.4); }}
    .badge.det .dot {{ background:#94a3b8; }}
    header p.lede {{ max-width: 900px; color: var(--hero-muted); margin: 0; }}
    header .headline {{ max-width: 900px; font-size: clamp(1.1rem, 2.2vw, 1.5rem); font-weight:600; margin: 6px 0 14px; }}
    main {{ padding: 24px clamp(20px, 5vw, 72px) 56px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(2rem, 4vw, 3.4rem); letter-spacing: -0.01em; }}
    h2 {{ margin: 0 0 16px; font-size: 1.05rem; letter-spacing: 0; }}
    .grid {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); margin-bottom: 24px; }}
    .stat, .agent, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 18px;
    }}
    .stat {{ position: relative; overflow: hidden; }}
    .stat span {{ display: block; color: var(--muted); font-size: .85rem; text-transform: uppercase; letter-spacing:.04em; }}
    .stat strong {{ display: block; font-size: 2.4rem; margin-top: 6px; line-height:1; }}
    .stat.crit strong {{ color: var(--crit); }}
    .stat.high strong {{ color: var(--high); }}
    .panel {{ margin-bottom: 24px; overflow-x: auto; }}
    ul.metrics {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    ul.metrics li {{ display: flex; justify-content: space-between; gap: 16px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; }}
    ul.metrics li span {{ color: var(--muted); }}
    ul.assets {{ list-style: none; padding: 0; margin: 0; }}
    ul.assets li {{ display:flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding: 10px 0; }}
    ul.actions {{ list-style:none; padding:0; margin:0; display:grid; gap:12px; }}
    li.action {{ display:flex; gap:14px; align-items:flex-start; border:1px solid var(--line); border-radius:10px; padding:14px; }}
    li.action .rank {{ flex:0 0 auto; width:30px; height:30px; border-radius:50%; background:var(--accent); color:#04201c; font-weight:700; display:flex; align-items:center; justify-content:center; }}
    li.action .action-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:4px; }}
    li.action p {{ margin:4px 0 6px; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 760px; }}
    th, td {{ text-align: left; padding: 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
    td.num {{ text-align:right; font-variant-numeric: tabular-nums; font-weight:600; }}
    th {{ color: var(--muted); font-size: .8rem; text-transform: uppercase; letter-spacing:.04em; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: .82em; color: var(--muted); word-break: break-all; }}
    .pill {{ display:inline-block; padding: 2px 9px; border-radius: 999px; font-size:.72rem; font-weight:700; letter-spacing:.03em; border:1px solid transparent; }}
    .sev-critical, .urg-now {{ color: var(--crit); border-color: color-mix(in srgb, var(--crit) 45%, transparent); background: color-mix(in srgb, var(--crit) 12%, transparent); }}
    .sev-high, .urg-soon {{ color: var(--high); border-color: color-mix(in srgb, var(--high) 45%, transparent); background: color-mix(in srgb, var(--high) 12%, transparent); }}
    .sev-medium {{ color: var(--med); border-color: color-mix(in srgb, var(--med) 45%, transparent); background: color-mix(in srgb, var(--med) 12%, transparent); }}
    .urg-monitor {{ color: var(--monitor); border-color: color-mix(in srgb, var(--monitor) 45%, transparent); background: color-mix(in srgb, var(--monitor) 12%, transparent); }}
    .agent h3 {{ margin: 0 0 8px; }}
    .agent p {{ color: var(--muted); min-height: 44px; margin: 0 0 8px; }}
    .agent strong {{ color: var(--accent); font-size:.8rem; letter-spacing:.04em; }}
    .reviewer {{ margin-top: 6px; padding: 12px 14px; border-left: 3px solid var(--accent); background: color-mix(in srgb, var(--accent) 8%, transparent); border-radius: 6px; color: var(--muted); }}
    footer {{ padding: 20px clamp(20px, 5vw, 72px) 40px; color: var(--muted); font-size:.85rem; }}
    @media (max-width: 760px) {{
      .grid {{ grid-template-columns: 1fr 1fr; }}
      table {{ min-width: 620px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">
      <span class="badge {'llm' if engine_llm else 'det'}"><span class="dot"></span>{html.escape(engine_label)} · {engine_model}</span>
      <span class="badge det"><span class="dot"></span>Every mutation approval-gated</span>
    </div>
    <h1>DataHub Steward Squad</h1>
    <p class="headline">{html.escape(str(narrative.get('headline', '')))}</p>
    <p class="lede">{html.escape(str(narrative.get('executive_summary', run.objective)))}</p>
  </header>
  <main>
    <section class="grid" aria-label="Severity summary">
      <div class="stat crit"><span>Critical</span><strong>{severity_counts["critical"]}</strong></div>
      <div class="stat high"><span>High</span><strong>{severity_counts["high"]}</strong></div>
      <div class="stat"><span>Medium</span><strong>{severity_counts["medium"]}</strong></div>
      <div class="stat"><span>MCP Proposals</span><strong>{len(run.proposals)}</strong></div>
    </section>
    <section class="panel">
      <h2>Prioritized Actions</h2>
      <ul class="actions">{action_items}</ul>
      <div class="reviewer">Reviewer note: {html.escape(str(narrative.get('reviewer_note', 'Review all evidence before approving mutations.')))}</div>
    </section>
    <section class="panel">
      <h2>Top Findings</h2>
      <table>
        <thead><tr><th>Severity</th><th>Finding</th><th>DataHub URN</th><th>Score</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <section class="panel">
      <h2>Run Metrics</h2>
      <ul class="metrics">{metric_items}</ul>
    </section>
    <section class="panel">
      <h2>Agent Team</h2>
      <div class="grid">{cards}</div>
    </section>
    <section class="panel">
      <h2>Inspected Assets</h2>
      <ul class="assets">{inspected}</ul>
    </section>
  </main>
  <footer>Generated by DataHub Steward Squad · {html.escape(run.started_at)} · Objective: {html.escape(run.objective)}</footer>
</body>
</html>
"""


def _mcp_plan(run: SquadRun) -> dict[str, object]:
    return {
        "kind": "datahub_mcp_writeback_plan",
        "requires_human_approval": True,
        "mcp_server": "datahub",
        "generated_at": run.started_at,
        "notes": [
            "Mutation tools must be enabled on the DataHub MCP server.",
            "Review every proposal before calling the tool in a live DataHub tenant.",
        ],
        "tool_calls": [
            {
                "id": proposal.id,
                "tool": proposal.tool,
                "arguments": proposal.arguments,
                "description": proposal.description,
                "finding_ids": proposal.finding_ids,
                "requires_approval": proposal.requires_approval,
            }
            for proposal in run.proposals
        ],
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
