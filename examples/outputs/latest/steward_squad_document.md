# Steward Squad Risk Brief

Objective: Detect DataHub metadata risks in a Finance data product, reason over lineage and quality, and prepare governed MCP writeback proposals.
Focus domain: Finance
Assets inspected: 4

## Top Findings

### HIGH: finance.fct_revenue has downstream production blast radius
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Asset: finance.fct_revenue
- Score: 30
- Recommendation: Review quality and governance before schema or freshness changes are shipped.

### HIGH: finance_daily.load_revenue has downstream production blast radius
- URN: `urn:li:dataJob:(urn:li:dataFlow:(airflow,finance_daily,PROD),load_revenue)`
- Asset: finance_daily.load_revenue
- Score: 30
- Recommendation: Review quality and governance before schema or freshness changes are shipped.

### CRITICAL: finance.fct_revenue has failing sql assertion
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Asset: finance.fct_revenue
- Score: 30
- Recommendation: Create an incident note, notify the owner, and attach a remediation plan.

### HIGH: finance.fct_revenue.customer_email appears sensitive but is not tagged
- URN: `urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)`
- Asset: finance.fct_revenue
- Score: 24
- Recommendation: Propose a PII tag or glossary term on the schema field.

### HIGH: analytics.mart_revenue_by_region has downstream production blast radius
- URN: `urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.mart_revenue_by_region,PROD)`
- Asset: analytics.mart_revenue_by_region
- Score: 22
- Recommendation: Review quality and governance before schema or freshness changes are shipped.

## Proposed Writeback
Every mutation is approval-gated. Review the generated MCP plan before applying changes.