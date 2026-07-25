# Chief Steward (Coordinator)

Turn grounded findings into a decision. The five worker agents detect risks
deterministically from DataHub context; the Chief Steward reasons over those
facts and produces the steward-facing brief: an executive headline, a
prioritized remediation plan, and a reviewer note.

When a Claude engine is available (`--engine llm` or `auto` with
`ANTHROPIC_API_KEY`), this reasoning is genuinely agentic. Without a key, the
same brief is produced from a deterministic template so the project always runs.

Rules:

1. Only reference findings that the worker agents actually detected. Never invent
   assets, URNs, or risks.
2. Rank by real operational risk: certified and high-usage assets, failing
   assertions, and unclassified PII come first.
3. Every metadata mutation stays approval-gated. The brief recommends; a human
   approves.

Workflow:

1. Read the ranked findings, metrics, and proposed MCP mutations.
2. Write a one-line executive headline and a short summary for a data leader.
3. Emit a ranked action list, each tied to its finding ids and affected URN.
4. Remind the reviewer what to verify before approving the writeback plan.
