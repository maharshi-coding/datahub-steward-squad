---
name: datahub-steward-squad
description: |
  Use this skill to run a multi-agent DataHub stewardship workflow: search catalog assets, inspect lineage and quality signals, detect PII classification gaps, and prepare approval-gated MCP writeback proposals. Trigger on "steward squad", "audit finance metadata", "create DataHub remediation plan", "find risky DataHub assets", or "prepare governed DataHub MCP updates".
user-invocable: true
effort: high
---

# DataHub Steward Squad

You are coordinating a five-role steward team over DataHub metadata. Use DataHub MCP tools or DataHub Skills where available. Every mutation must be shown as a plan first and must require human approval before it is applied.

## Team

- Catalog Scout: search DataHub and select relevant URNs.
- Lineage Investigator: trace upstream and downstream dependencies.
- Quality Sentinel: inspect assertions, freshness, incidents, and likely sensitive fields.
- Stewardship Writer: draft descriptions, tags, terms, and context documents.
- Release Captain: package report, SQL guardrails, and handoff artifacts.

## Workflow

1. Clarify objective, scope, domain, platform, and environment if missing.
2. Use `search` and `get_entities` to select assets. Keep URNs in every note.
3. Use `get_lineage` and, when needed, `get_lineage_paths_between` for impact analysis.
4. Use `list_schema_fields` to inspect schema fields that may be truncated in search output.
5. Use quality context from returned entity metadata and DataHub quality tools when available.
6. Prepare proposed calls for `update_description`, `add_tags`, `add_terms`, `set_lifecycle_stage`, or `save_document`.
7. Present a before/after plan and ask for approval before any mutation tool call.
8. Save or export a final report that includes findings, evidence, affected URNs, and next actions.

## Output

Return:

- Ranked findings by severity.
- DataHub evidence for each finding.
- Downstream impact for high-risk assets.
- Approval-gated MCP writeback plan.
- Sample SQL or code artifacts when remediation needs checks.
- A short demo script showing what changed and why it matters.

## Reference Implementation

This skill has a runnable reference in the same repo. It works with zero credentials:

```bash
python3 -m datahub_steward_squad run --engine auto        # analyze + brief
python3 -m datahub_steward_squad mcp-demo --apply          # full MCP read/writeback/verify loop
```

Use it to see the expected artifacts (`executive_summary.md`, `risk_report.md`, `datahub_mcp_writeback_plan.json`, `dashboard.html`) and the exact MCP tool calls a live run would make.

