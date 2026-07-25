# DataHub Steward Squad

![tests](https://img.shields.io/badge/tests-9%20passing-brightgreen)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green)
![Dependencies: none](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

ECC-style multi-agent stewardship for DataHub metadata.

> **30-second judge test:** `python3 -m datahub_steward_squad mcp-demo --apply` runs the whole read → analyze → writeback → verify loop over MCP with zero credentials.

DataHub Steward Squad is a runnable hackathon project that turns DataHub context into governed action. A five-agent team searches a DataHub-shaped metadata graph, traces lineage, detects quality and PII risks, drafts steward-facing remediation, and emits approval-gated DataHub MCP writeback proposals. A Chief Steward coordinator — powered by Claude when a key is present — reasons over the grounded findings and writes the executive brief.

Two things make it *real*, not a mockup:

- **Genuinely agentic.** With `ANTHROPIC_API_KEY` set, a Claude model does the steward reasoning and prioritization. Without a key it falls back to a deterministic engine, so the project always runs and the demo never breaks.
- **A real end-to-end MCP loop.** `mcp-demo` spins up a bundled DataHub-shaped MCP server and runs the full **read → analyze → writeback → verify** loop over JSON-RPC — with zero credentials. The PII tag and description updates are actually written through MCP mutation tools and confirmed by re-reading the graph.

The default demo runs fully offline from `examples/retail_finance_graph.json`, so judges can test it immediately. The same code path targets a live DataHub MCP Server through `mcp/datahub-mcp.local.json`.

## Why This Can Win

- **Real agent, not rules-in-a-trenchcoat:** a Claude-powered Chief Steward reasons over grounded findings, with a deterministic fallback so it always runs offline.
- **Real MCP loop:** `mcp-demo` reads the catalog, writes changes back, and verifies them through the Model Context Protocol — not just a JSON plan on disk.
- **Meaningful DataHub use:** centered on DataHub URNs, domains, owners, schema fields, assertions, lineage, glossary terms, and context documents.
- **Agent category fit:** an "Agents That Do Real Work" submission that finds governance risks and prepares updates the next steward can inherit.
- **Submission quality:** runnable code, passing CI, sample outputs, a demo script, Apache 2.0 license, an ECC-inspired team config, and a reusable DataHub Skill candidate.
- **Bonus path:** `skills/datahub-steward-squad/SKILL.md` is structured as a contribution candidate for the DataHub Skills ecosystem.

## Agent Team

The team follows the ECC team-builder/team-orchestration style from `affaan-m/ECC`, adapted into this new Apache-2.0 project:

| Agent | Job |
| --- | --- |
| Catalog Scout | Select relevant DataHub assets and metadata coverage gaps |
| Lineage Investigator | Trace upstream/downstream impact radius |
| Quality Sentinel | Detect assertion failures and PII classification gaps |
| Stewardship Writer | Generate governed MCP writeback proposals |
| Release Captain | Package SQL guardrails, dashboard, reports, and demo evidence |
| Chief Steward (coordinator) | Reason over grounded findings into an executive brief + prioritized plan (Claude or deterministic) |

See `agents/` and `team/ecc-datahub-steward-squad.json`.

## Quick Start

No dependencies, no credentials. Python 3.9+ and the standard library only.

```bash
python3 -m datahub_steward_squad inspect-fixture
python3 -m datahub_steward_squad run
```

Generated artifacts land in `examples/outputs/latest/`:

- `executive_summary.md` — Chief Steward brief (headline + prioritized actions)
- `risk_report.md`
- `datahub_mcp_writeback_plan.json`
- `generated_quality_sql.sql`
- `team_board.json`
- `steward_squad_document.md`
- `dashboard.html`
- `run_summary.json`

Open the dashboard directly in a browser:

```bash
open examples/outputs/latest/dashboard.html
```

## Reasoning Engines

The five worker agents always run deterministically — findings are grounded facts pulled straight from the graph. The Chief Steward coordinator then turns those facts into a decision brief using one of three engines:

```bash
# auto (default): use Claude if ANTHROPIC_API_KEY is set, else deterministic
python3 -m datahub_steward_squad run --engine auto

# require Claude (real agentic reasoning)
export ANTHROPIC_API_KEY=sk-ant-...
python3 -m datahub_steward_squad run --engine llm

# never call an LLM (fully offline, reproducible)
python3 -m datahub_steward_squad run --engine deterministic
```

The LLM never invents risks: it only reasons over findings the deterministic agents detected, and every mutation stays approval-gated. Override the model with `--model` or `STEWARD_LLM_MODEL` (default `claude-sonnet-5`). The Anthropic call uses only the Python standard library — no SDK required.

### Enabling the Claude engine

The Claude engine is optional. Everything above (including the full MCP loop) runs offline without it — so you can skip this section entirely and still see the whole project work.

To turn on real Claude reasoning:

1. **Create an API key** at [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys).
2. **Add API credits** at [console.anthropic.com/settings/billing](https://console.anthropic.com/settings/billing) — a run costs a fraction of a cent, so $5 is plenty. (API credits are separate from a Claude.ai subscription; a fresh key with no credits returns a `400 credit balance is too low` error.)
3. **Set the key.** Either export it directly:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```
   or use the provided template:
   ```bash
   cp .env.example .env      # then edit .env and paste your key
   set -a && source .env && set +a
   ```
4. **Run with Claude:**
   ```bash
   python3 -m datahub_steward_squad run --engine llm
   ```
   Success prints `Engine: llm (claude-sonnet-5)`. If the key is missing or has no credits, `--engine llm` exits with a clean, actionable message (no traceback), and `--engine auto` falls back to the deterministic engine so the demo never breaks.

`.env` is git-ignored — your key never lands in the repo.

## Live MCP Loop (read → analyze → writeback → verify)

`mcp-demo` runs the **entire** stewardship loop over the Model Context Protocol against a bundled DataHub-shaped MCP server (`datahub_steward_squad/mcp_server.py`). No DataHub instance and no credentials are needed.

```bash
# Dry run: read the catalog over MCP, analyze, print the writeback plan
python3 -m datahub_steward_squad mcp-demo

# Apply: approve the proposals, write them back via MCP mutation tools,
# then re-read the graph to prove the changes landed
python3 -m datahub_steward_squad mcp-demo --apply
```

Example verification output — the PII tag is written through MCP and confirmed by re-reading:

```
Applied writeback via MCP mutation tools:
  MCP-001 add_tags: applied
  MCP-002 save_document: applied

Verification (re-read through MCP):
  ...finance.fct_revenue: customer_email.tags [] -> ['urn:li:tag:PII']
```

Approve a subset with `--approve MCP-001,MCP-003`. The bundled server speaks the same read/mutation tool names as the official DataHub MCP Server, so the live boundary is a config swap (see below). You can also point any MCP host (Claude Desktop, etc.) straight at the mock server with `mcp/datahub-steward-mock.json`.

## Test

```bash
python3 -m unittest discover -s tests
```

## Live DataHub MCP Setup

The default demo does not need credentials. For a live catalog, configure DataHub MCP with:

```bash
cp mcp/datahub-mcp.local.json mcp/datahub-mcp.private.json
```

Then edit `DATAHUB_GMS_URL`, `DATAHUB_GMS_TOKEN`, and keep `TOOLS_IS_MUTATION_ENABLED=true` only when you are ready to review and approve mutation calls.

Official DataHub docs say the MCP server exposes read tools such as `search`, `get_entities`, and `get_lineage`, plus mutation tools including `update_description`, `add_tags`, and `save_document` when mutations are enabled. See `docs/datahub_mcp_setup.md`.

## Demo Command

```bash
python3 -m datahub_steward_squad run \
  --query revenue \
  --focus-domain Finance \
  --out examples/outputs/latest
```

The generated MCP writeback plan is intentionally not auto-applied. Judges can inspect exactly what would be sent to DataHub before any catalog mutation.

## Pre-Existing Work Disclosure

This repository is new work for the Build with DataHub: The Agent Hackathon. It uses `affaan-m/ECC` as a design reference for multi-agent team structure and orchestration vocabulary. No ECC source code is copied into this project. ECC is MIT-licensed; this project is Apache-2.0 licensed to satisfy the hackathon submission requirement.

## License

Apache License 2.0. See `LICENSE`.
