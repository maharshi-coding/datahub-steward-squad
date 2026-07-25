# DataHub Steward Squad Risk Report

Objective: Detect DataHub metadata risks in a Finance data product, reason over lineage and quality, and prepare governed MCP writeback proposals.
Query: `revenue`
Focus domain: `Finance`
Reasoning engine: `Claude` (claude-sonnet-5)
Started at: `2026-07-25T06:04:31.081291+00:00`

## Chief Steward Brief

> finance.fct_revenue is a certified, high-usage revenue table with a failing data-quality assertion and unclassified PII, and its blast radius extends through two other critical assets.

A failing SQL assertion on finance.fct_revenue (18 negative-revenue rows expected to be 0) threatens a certified, high-usage (423/30d) asset that feeds Executive Revenue KPI, mart_revenue_by_region, and the churn_risk_model. The same table exposes an untagged customer_email column that matches PII heuristics, and both the upstream loader job and the downstream mart carry similar downstream blast-radius risk. Immediate remediation of the assertion and PII tagging is warranted before any schema or freshness changes ship downstream.

## Scorecard

| Metric | Value |
| --- | ---: |
| Critical Findings | 1 |
| Failing Assertions | 1 |
| High Findings | 4 |
| High Impact Assets | 3 |
| Mcp Writeback Proposals | 2 |
| Missing Description Assets | 0 |
| Missing Owner Assets | 0 |
| Pii Classification Gaps | 1 |
| Selected Assets | 4 |

## Findings

### QLT-004 - CRITICAL - finance.fct_revenue has failing sql assertion

- Asset: `finance.fct_revenue`
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Agent: Quality Sentinel
- Score: 30
- Recommendation: Create an incident note, notify the owner, and attach a remediation plan.
- Suggested DataHub tools: get_entities, save_document, update_description
- Evidence:
  - Assertion: finance.fct_revenue negative revenue check
  - Observed: 18 rows
  - Expected: 0 rows
  - Last run: 2026-07-24T12:06:00Z
  - Refund adjustments are arriving without offsetting credit memos.

### LIN-001 - HIGH - finance.fct_revenue has downstream production blast radius

- Asset: `finance.fct_revenue`
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Agent: Lineage Investigator
- Score: 30
- Recommendation: Review quality and governance before schema or freshness changes are shipped.
- Suggested DataHub tools: get_lineage, get_lineage_paths_between, save_document
- Evidence:
  - Upstream dependencies: 3
  - Downstream dependencies: 3
  - Critical downstream assets: analytics.mart_revenue_by_region, Executive Revenue KPI, churn_risk_model

### LIN-003 - HIGH - finance_daily.load_revenue has downstream production blast radius

- Asset: `finance_daily.load_revenue`
- URN: `urn:li:dataJob:(urn:li:dataFlow:(airflow,finance_daily,PROD),load_revenue)`
- Agent: Lineage Investigator
- Score: 30
- Recommendation: Review quality and governance before schema or freshness changes are shipped.
- Suggested DataHub tools: get_lineage, get_lineage_paths_between, save_document
- Evidence:
  - Upstream dependencies: 1
  - Downstream dependencies: 4
  - Critical downstream assets: analytics.mart_revenue_by_region, Executive Revenue KPI, finance.fct_revenue, churn_risk_model

### PII-005 - HIGH - finance.fct_revenue.customer_email appears sensitive but is not tagged

- Asset: `finance.fct_revenue`
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Agent: Quality Sentinel
- Score: 24
- Recommendation: Propose a PII tag or glossary term on the schema field.
- Suggested DataHub tools: list_schema_fields, add_tags, add_terms
- Evidence:
  - Column type: varchar
  - Column name matches sensitive-data heuristic.
  - No PII tag or glossary term is attached.

### LIN-002 - HIGH - analytics.mart_revenue_by_region has downstream production blast radius

- Asset: `analytics.mart_revenue_by_region`
- URN: `urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.mart_revenue_by_region,PROD)`
- Agent: Lineage Investigator
- Score: 22
- Recommendation: Review quality and governance before schema or freshness changes are shipped.
- Suggested DataHub tools: get_lineage, get_lineage_paths_between, save_document
- Evidence:
  - Upstream dependencies: 3
  - Downstream dependencies: 1
  - Critical downstream assets: Executive Revenue KPI

## Proposed DataHub MCP Mutations

### MCP-001 - `add_tags`

Classify finance.fct_revenue.customer_email as PII

- Requires approval: `true`
- Related findings: PII-005

### MCP-002 - `save_document`

Save the squad risk brief into DataHub context documents

- Requires approval: `true`
- Related findings: LIN-001, LIN-002, LIN-003, QLT-004, PII-005
