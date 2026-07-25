# Live DataHub loop — recorded evidence

Terminal transcripts of the Steward Squad running its full **read → analyze →
writeback → verify** loop against a **real** local DataHub (v1.5.x quickstart)
via the official `mcp-server-datahub`, seeded with
`examples/retail_finance_graph.json` (see `scripts/ingest_fixture_to_datahub.py`).

- **`live_mcp_loop.txt`** — focused run (`mcp-demo --live --apply`, default
  `--query revenue`): detects the unclassified PII column on the certified
  revenue table and writes `urn:li:tag:PII` onto `finance.fct_revenue.customer_email`,
  verified by re-reading through MCP.
- **`live_mcp_loop_full.txt`** — broad run (`--query ""`, all Finance datasets):
  applies two `update_description`s, three column `add_tags`, and one
  `save_document`, with five verified before/after diffs against real DataHub.

Reproduce with the steps in [../docs/datahub_mcp_setup.md](../docs/datahub_mcp_setup.md).
The raw real-server response shapes these were built against are recorded under
`../tests/fixtures/live/`.
