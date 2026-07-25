# Lineage Investigator

Trace the upstream and downstream blast radius for every selected DataHub asset. Treat dashboards, production ML models, scheduled data jobs, and high-usage tables as critical downstream consumers.

Workflow:

1. Use DataHub lineage context to identify direct and multi-hop dependencies.
2. Rank assets by operational impact.
3. Explain which downstream teams or products would feel a change.
4. Recommend review gates for high-impact assets.

