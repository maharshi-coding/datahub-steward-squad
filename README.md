# DataHub Steward Squad

![tests](https://img.shields.io/badge/tests-29%20passing-brightgreen)
![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue)
![License Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green)
![Offline path: stdlib only](https://img.shields.io/badge/offline%20path-stdlib%20only-brightgreen)

ECC-style multi-agent stewardship for DataHub metadata.

> **The real thing:** `python3 -m datahub_steward_squad mcp-demo --live --apply` runs the whole read → analyze → writeback → verify loop against a **real DataHub** via the official `mcp-server-datahub`.
>
> **Zero-credential fallback:** drop `--live` to run the identical loop against a bundled DataHub-shaped mock — no DataHub, no keys — so the demo never breaks.

DataHub Steward Squad is a runnable hackathon project that turns DataHub context into governed action. A five-agent team searches DataHub, traces lineage, detects quality and PII risks, drafts steward-facing remediation, and emits approval-gated MCP writeback proposals. A Chief Steward coordinator — powered by Claude when a key is present — reasons over the grounded findings and writes the executive brief.

Two things make it *real*, not a mockup:

- **A real DataHub MCP loop.** `mcp-demo --live` launches the official `mcp-server-datahub`, reconstructs the graph from real `search` / `get_entities` / `get_lineage` calls, then writes approved fixes back through real `update_description` / `add_tags` / `save_document` mutation tools and re-reads to prove they landed. We inspected the real server's actual interface (recorded under `tests/fixtures/live/`) and built an adapter for its GraphQL-shaped responses — we do **not** reimplement DataHub.
- **Genuinely agentic.** With `ANTHROPIC_API_KEY` set, a Claude model does the steward reasoning and prioritization. Without a key it falls back to a deterministic engine, so the project always runs.

The same loop runs offline against a bundled mock (`mcp_server.py`) with zero credentials, so judges can test it in seconds — then flip `--live` to point it at real DataHub. See [docs/datahub_mcp_setup.md](docs/datahub_mcp_setup.md) and a recorded live transcript in [evidence/live_mcp_loop.txt](evidence/live_mcp_loop.txt).

## Why This Can Win

- **Runs against real DataHub:** `mcp-demo --live` uses the official `mcp-server-datahub` — reading real metadata and writing governed changes back — not a reimplementation of DataHub's APIs.
- **Real agent, not rules-in-a-trenchcoat:** a Claude-powered Chief Steward reasons over grounded findings, with a deterministic fallback so it always runs offline.
- **Real MCP loop:** reads the catalog, writes changes back, and verifies them through the Model Context Protocol — not just a JSON plan on disk.
- **Meaningful DataHub use:** centered on DataHub URNs, domains, owners, schema fields, lineage, glossary terms, tags, and context documents.
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

## Live DataHub MCP Loop (read → analyze → writeback → verify)

`mcp-demo --live` runs the **entire** stewardship loop over MCP against a **real
DataHub** through the official `mcp-server-datahub`. Full setup (quickstart,
seeding, token) is in [docs/datahub_mcp_setup.md](docs/datahub_mcp_setup.md); the short version:

```bash
pip install --upgrade acryl-datahub
datahub docker quickstart                       # DataHub on :8080 / UI on :9002
pip install -e ".[live]"                        # acryl-datahub SDK + uv (uvx)
python scripts/ingest_fixture_to_datahub.py     # seed the retail/finance fixture
cp .env.example .env                            # set DATAHUB_GMS_URL (+ token if auth on)

# Dry run: read REAL metadata over MCP, analyze, print the writeback plan
python3 -m datahub_steward_squad mcp-demo --live

# Apply: write approved fixes back through real mutation tools, then re-read
python3 -m datahub_steward_squad mcp-demo --live --apply
```

Against the seeded catalog the live loop detects the same risk classes as the
offline demo — missing owners/descriptions, unclassified PII columns, lineage
blast radius (naming the real datajob and dashboard), and **failing data-quality
assertions** (read from DataHub's dataset `health` signal). Recorded live
verification output ([evidence/live_mcp_loop_full.txt](evidence/live_mcp_loop_full.txt)) — real
descriptions and column PII tags written through `mcp-server-datahub` and
confirmed by re-reading:

```
Applied writeback via MCP mutation tools:
  MCP-001 update_description: applied
  MCP-002 add_tags: applied
  ...
Verification (re-read through MCP):
  ...snowflake,raw.payments,PROD): description '' -> 'raw.payments is a snowflake dataset in the Fi...'
  ...snowflake,raw.payments,PROD): customer_email.tags [] -> ['PII']
  ...snowflake,finance.fct_revenue,PROD): customer_email.tags [] -> ['PII']
```

### Zero-credential offline fallback

Drop `--live` to run the identical loop against the bundled DataHub-shaped mock
server (`datahub_steward_squad/mcp_server.py`) — no DataHub, no credentials:

```bash
python3 -m datahub_steward_squad mcp-demo --apply
```

Approve a subset with `--approve MCP-001,MCP-003`. The mock speaks the same tool
*names* as the official server, so the offline demo mirrors the live one. You can
also point any MCP host (Claude Desktop, etc.) at the mock with
`mcp/datahub-steward-mock.json`, or at real DataHub with `mcp/datahub-mcp.local.json`.

## Test

```bash
python3 -m unittest discover -s tests
```

29 tests, including the live adapter checked against recorded real-server
responses in `tests/fixtures/live/` — so live parsing is covered without DataHub running.

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
