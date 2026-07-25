# Hackathon Strategy

## Target Category

Primary: Agents That Do Real Work.

Secondary: Metadata-Aware Code Generation and Development, because the project emits SQL guardrail artifacts and MCP writeback plans grounded in DataHub metadata.

## Judging Alignment

| Criterion | Project Evidence |
| --- | --- |
| Use of DataHub | Uses DataHub URNs, lineage, owners, schema fields, assertions, glossary terms, domains, tags, and MCP mutation plans. |
| Technical Execution | Runs with `python3 -m datahub_steward_squad run`, includes tests, and produces deterministic artifacts. |
| Originality | Composes an ECC-style agent team with DataHub context to create governed steward actions, not just catalog search. |
| Real-World Usefulness | Data teams need practical triage for ownership gaps, PII classification, freshness failures, and downstream blast radius. |
| Submission Quality | Includes README, Apache 2.0 license, demo script, sample outputs, dashboard, and reusable skill candidate. |

## Winning Demo Story

1. Open with the problem: DataHub has the context, but steward teams still triage metadata debt manually.
2. Run the squad on the Finance domain.
3. Show that it finds a certified revenue table with a failing assertion, downstream dashboard/model impact, and untagged sensitive fields.
4. Open `risk_report.md` and `dashboard.html`.
5. Open `datahub_mcp_writeback_plan.json` to show governed updates are ready, not blindly applied.
6. Close with the DataHub Skill candidate as the bonus contribution path.

## Pre-Existing Work Disclosure

`affaan-m/ECC` was used as inspiration for team composition and orchestration vocabulary. No ECC source code is copied into this repository. This project is new and licensed under Apache 2.0.

