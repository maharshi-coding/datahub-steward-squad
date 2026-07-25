# Chief Steward Brief

> finance.fct_revenue is failing a critical data quality check and feeding certified, high-usage downstream assets, requiring immediate remediation and PII tagging before any further changes ship.

- Reasoning engine: **Claude** (`claude-sonnet-5`)
- Objective: Detect DataHub metadata risks in a Finance data product, reason over lineage and quality, and prepare governed MCP writeback proposals.
- Focus domain: `Finance`

## Executive Summary

A certified, high-usage asset (finance.fct_revenue, 423 30-day queries) is failing a negative-revenue SQL assertion with 18 bad rows, and it fans out to three critical downstream consumers including an executive KPI and a churn model. The same asset has an untagged customer_email column that heuristically matches sensitive PII. Upstream, the finance_daily.load_revenue job and analytics.mart_revenue_by_region both carry production blast radius into the same critical downstream chain, so any schema or freshness change should be gated on quality and governance review first. Two MCP writeback proposals (PII tagging and a saved risk brief) are ready for approval-gated execution.

## Prioritized Actions

1. **[NOW] Open incident for failing revenue assertion**
   - Why: A certified, high-usage table is producing 18 rows of negative revenue, risking incorrect figures in an executive KPI and churn model.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: QLT-004
2. **[NOW] Tag customer_email as PII**
   - Why: An unclassified sensitive-looking column on a certified, high-usage table exposes compliance risk.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: PII-005
3. **[SOON] Gate changes to fct_revenue on quality/governance review**
   - Why: Three critical downstream assets (churn_risk_model, mart_revenue_by_region, Executive Revenue KPI) depend on this table, so unreviewed changes could cascade failures.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: LIN-001
4. **[SOON] Review load_revenue pipeline before schema/freshness changes**
   - Why: This uncertified but low-usage job feeds the same critical downstream chain as fct_revenue, amplifying upstream risk.
   - Asset: `urn:li:dataJob:(urn:li:dataFlow:(airflow,finance_daily,PROD),load_revenue)`
   - Related findings: LIN-003
5. **[MONITOR] Monitor mart_revenue_by_region for downstream impact**
   - Why: This certified, high-usage mart feeds the Executive Revenue KPI and should be watched given upstream quality issues.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.mart_revenue_by_region,PROD)`
   - Related findings: LIN-002

## Reviewer Note

Before approving the PII tag and risk-brief MCP writebacks, confirm the customer_email column truly contains sensitive data and that the incident/remediation plan for the failing assertion is referenced accurately in the saved brief.
