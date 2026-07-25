# Three-Minute Demo Script

## 0:00-0:20 - Problem

"DataHub already knows ownership, lineage, quality, glossary terms, and schema context. The missing piece is an agent team that can turn that context into safe, governed steward work — and actually write it back."

## 0:20-0:45 - Team

Show `team/ecc-datahub-steward-squad.json`, the five agent files in `agents/`, and the Chief Steward coordinator (`agents/chief-steward.md`).

"Five worker agents detect risks deterministically. A Chief Steward — powered by Claude — reasons over those grounded findings and writes the brief."

## 0:45-1:15 - Run (with real agentic reasoning)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m datahub_steward_squad run --query revenue --focus-domain Finance --engine llm
```

Point out `Engine: llm (claude-...)` in the output. Then note the fallback:

"No key? `--engine auto` falls back to a deterministic engine, so the demo never breaks and judges can run it offline."

## 1:15-2:00 - Outputs

Open:

- `examples/outputs/latest/executive_summary.md` (the Chief Steward brief)
- `examples/outputs/latest/dashboard.html` (dark-mode dashboard, prioritized actions)
- `examples/outputs/latest/generated_quality_sql.sql`

Call out:

- Certified revenue table has a failing SQL assertion (the critical, ranked #1).
- Downstream impact includes executive reporting and a production ML model.
- Sensitive customer email is missing a PII classification.
- The generated SQL provides guardrail examples.

## 2:00-2:45 - Live DataHub MCP writeback (the money shot)

"Now the real thing — the whole loop against a **live DataHub**, through the official `mcp-server-datahub`."

```bash
python3 -m datahub_steward_squad mcp-demo --live --apply
```

Narrate the output live:

- It launches `uvx mcp-server-datahub@latest` and lists the **real** server's tools (`search`, `get_entities`, `get_lineage`, plus mutation tools).
- It reconstructs the graph **from real DataHub reads** ("4 assets, 3 lineage edges").
- It applies `update_description` / `add_tags` / `save_document` through **real MCP mutation tools**.
- It re-reads and shows verified diffs, e.g. `customer_email.tags [] -> ['PII']` and a drafted description landing on `raw.payments`.

Then flip to the DataHub UI (http://localhost:9002) and show the PII tag on the column and the "Steward Squad Risk Brief" document — written by the agent, now living in DataHub.

"Every mutation was approval-gated. And if you have no DataHub handy, drop `--live` — the identical loop runs against a bundled mock with zero credentials, so the demo never breaks."

## 2:45-3:00 - Why It Matters

"This is not another chat interface. It is a repeatable steward workflow that reads DataHub context, reasons over it with a real agent, writes governed changes back through MCP, and verifies them — so the next person or agent starts smarter."
