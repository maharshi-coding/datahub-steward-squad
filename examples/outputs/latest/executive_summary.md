# Chief Steward Brief

> finance.fct_revenue is a certified, high-usage revenue table with a failing data-quality assertion and unclassified PII, and its blast radius extends through two other critical assets.

- Reasoning engine: **Claude** (`claude-sonnet-5`)
- Objective: Detect DataHub metadata risks in a Finance data product, reason over lineage and quality, and prepare governed MCP writeback proposals.
- Focus domain: `Finance`

## Executive Summary

A failing SQL assertion on finance.fct_revenue (18 negative-revenue rows expected to be 0) threatens a certified, high-usage (423/30d) asset that feeds Executive Revenue KPI, mart_revenue_by_region, and the churn_risk_model. The same table exposes an untagged customer_email column that matches PII heuristics, and both the upstream loader job and the downstream mart carry similar downstream blast-radius risk. Immediate remediation of the assertion and PII tagging is warranted before any schema or freshness changes ship downstream.

## Prioritized Actions

1. **[NOW] Investigate and remediate failing revenue assertion**
   - Why: A certified, high-usage table (423/30d) is producing 18 rows of negative revenue against an expected 0, risking downstream financial reporting and model accuracy.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: QLT-004
2. **[NOW] Freeze schema/freshness changes on finance.fct_revenue pending quality review**
   - Why: This certified, high-usage asset has three critical downstream dependents (analytics.mart_revenue_by_region, Executive Revenue KPI, churn_risk_model) that would propagate any unresolved quality issue.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: LIN-001, QLT-004
3. **[SOON] Approve PII tagging for customer_email column**
   - Why: An untagged column matching sensitive-data heuristics on a certified, high-usage table creates compliance exposure until classified.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
   - Related findings: PII-005
4. **[SOON] Review governance on finance_daily.load_revenue upstream job**
   - Why: This uncertified loader job feeds finance.fct_revenue and three other critical downstream assets, making it a high-leverage but less-governed control point.
   - Asset: `urn:li:dataJob:(urn:li:dataFlow:(airflow,finance_daily,PROD),load_revenue)`
   - Related findings: LIN-003
5. **[MONITOR] Monitor mart_revenue_by_region for downstream KPI impact**
   - Why: This certified, moderately-used mart directly feeds the Executive Revenue KPI, so upstream issues could surface in executive reporting.
   - Asset: `urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.mart_revenue_by_region,PROD)`
   - Related findings: LIN-002

## Reviewer Note

Before approving MCP-001 and MCP-002, confirm the customer_email column truly contains PII (not a false-positive naming match) and verify the assertion incident note captures the correct owner and remediation timeline.
