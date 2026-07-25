# DataHub MCP Setup

The Steward Squad runs its full **read → analyze → writeback → verify** loop over
the Model Context Protocol. There are two backends:

1. **Live DataHub (primary).** The official [`mcp-server-datahub`](https://docs.datahub.com/docs/features/feature-guides/mcp)
   talking to a real DataHub instance. This is what the hackathon submission is about.
2. **Bundled mock (offline fallback).** `datahub_steward_squad/mcp_server.py`, a
   DataHub-shaped MCP server that needs zero credentials so the demo always runs.

Both speak the same client (`mcp_client.py`); the live adapter (`live.py`)
bridges the real server's GraphQL-shaped responses into the squad's model.

---

## Live DataHub (primary path)

### 1. Stand up DataHub locally

```bash
pip install --upgrade acryl-datahub
datahub docker quickstart
```

This pulls and starts DataHub (GMS on `:8080`, the UI on `:9002`). A local
quickstart runs with `METADATA_SERVICE_AUTH_ENABLED=false`, so **a token is
optional locally**.

### 2. Seed the catalog with the demo fixture

The squad's story is built around the retail/finance fixture in
`examples/retail_finance_graph.json`. Ingest it into your live DataHub so the
live loop detects the *same* governance risks (owner gaps, PII columns, lineage
blast radius) as the offline demo:

```bash
pip install -e ".[live]"           # acryl-datahub SDK + uv
python scripts/ingest_fixture_to_datahub.py
```

This emits datasets (with schema fields, owners, tags, glossary terms, domains,
custom properties), the `finance_daily.load_revenue` datajob and the
`Executive Revenue KPI` dashboard with cross-type lineage, data-quality
assertions with pass/fail run events, and the `urn:li:tag:PII` tag that the PII
writeback attaches. Open http://localhost:9002 (login `datahub`/`datahub`) to
browse the seeded Finance domain.

As a result the live loop detects the same risk classes as the offline demo:
missing owners/descriptions, unclassified PII columns, lineage blast radius
(naming the datajob and dashboard), and **failing assertions** — the latter read
from DataHub's dataset `health` signal (no cloud-only assertions tool required).

> Prefer DataHub's own sample data? `datahub docker ingest-sample-data` also
> works when its bundled file matches your CLI version. The fixture seeder above
> is version-independent and keeps the offline and live demos telling one story.

### 3. (Optional) Generate a Personal Access Token

Only needed for DataHub Cloud or when GMS auth is enabled. In the UI:
**Settings → Access Tokens → Generate**. If "Access Tokens" isn't visible,
set `METADATA_SERVICE_AUTH_ENABLED=true` and restart the quickstart.

### 4. Configure the environment

```bash
cp .env.example .env
# edit .env:
#   DATAHUB_GMS_URL=http://localhost:8080
#   DATAHUB_GMS_TOKEN=<token>        # optional locally
#   TOOLS_IS_MUTATION_ENABLED=true
```

`.env` is git-ignored. The CLI auto-loads it in `--live` mode.

### 5. Run the live loop

```bash
# Dry run: read real metadata over MCP, analyze, print the writeback plan
python -m datahub_steward_squad mcp-demo --live

# Apply: write approved changes back through the real mutation tools, then
# re-read to prove they landed
python -m datahub_steward_squad mcp-demo --live --apply
```

Under the hood this launches `uvx mcp-server-datahub@latest` with your DataHub
env, reconstructs the graph from `search` / `get_entities` / `get_lineage`, runs
the squad, and (with `--apply`) executes `update_description` / `add_tags` /
`save_document` before verifying by re-reading. See `evidence/live_mcp_loop.txt`
for a recorded transcript.

### The real server's interface (recorded)

The real tool names overlap with our mock, but the argument schemas and response
shapes are entirely different (nested, camelCase GraphQL). The exact shapes are
recorded under `tests/fixtures/live/` (captured with `scripts/explore_live_mcp.py`)
and the live adapter is tested against them. Highlights:

| Tool | Real signature (differs from the mock) |
| --- | --- |
| `search` | `search(query, filter, num_results, sort_by, sort_order)` → `{searchResults: [{entity}], facets}` |
| `get_entities` | `get_entities(urns)` → GraphQL entities: `platform:{urn,name}`, `customProperties:[{key,value}]`, `ownership.owners[].owner.urn`, `schemaMetadata.fields[]` |
| `get_lineage` | `get_lineage(urn, upstream: bool, max_hops)` → `{upstreams/downstreams: {searchResults: [{entity, degree}]}}` (no "both" — two calls) |
| `update_description` | `update_description(entity_urn, operation, description, column_path)` |
| `add_tags` | `add_tags(tag_urns[], entity_urns[], column_paths[])` — **validates the tag URN exists first** |
| `add_terms` | `add_glossary_terms(term_urns[], entity_urns[], column_paths[])` |
| `save_document` | `save_document(document_type, title, content, ...)` — `document_type` ∈ Insight/Decision/FAQ/Analysis/Summary/Recommendation/Note/Context |

Writebacks land in `editableSchemaMetadata` / `editableProperties`; the server
surfaces those on re-read as `editedTags` / `editedDescription`, which the
adapter merges so verification sees the change.

### Point a general MCP host at DataHub

`mcp/datahub-mcp.local.json` is a drop-in config for Claude Desktop or any MCP
host:

```json
{
  "mcpServers": {
    "datahub": {
      "command": "uvx",
      "args": ["mcp-server-datahub@latest"],
      "env": {
        "DATAHUB_GMS_URL": "http://localhost:8080",
        "DATAHUB_GMS_TOKEN": "<your-datahub-token>",
        "TOOLS_IS_MUTATION_ENABLED": "true"
      }
    }
  }
}
```

Keep `TOOLS_IS_MUTATION_ENABLED=true` only when you are ready to review and
approve mutation proposals. The project never auto-applies generated plans.

---

## Bundled mock MCP server (offline fallback)

No DataHub, no credentials — the full loop still runs:

```bash
python -m datahub_steward_squad mcp-demo --apply
```

`datahub_steward_squad/mcp_server.py` speaks newline-delimited JSON-RPC 2.0 over
stdio and exposes the same tool *names* as the official server: `search`,
`get_entities`, `get_lineage`, `list_schema_fields` (read) and
`update_description`, `add_tags`, `add_terms`, `save_document` (mutation, gated
behind `--enable-mutations`). It serves `examples/retail_finance_graph.json` from
memory so writebacks are verifiable in-process. Use `mcp/datahub-steward-mock.json`
to drive it from a general MCP host.

---

## Troubleshooting

- **`uvx` not found** → `pip install uv` (or `pip install -e ".[live]"`).
- **Live loop can't connect** → check `datahub docker quickstart` is up and
  `DATAHUB_GMS_URL` is set. The offline demo always works:
  `python -m datahub_steward_squad mcp-demo --apply`.
- **DataHub filled the disk / a container crashed** → `datahub docker quickstart --stop`.
- **`add_tags` fails with "tag does not exist"** → run the fixture seeder, which
  creates `urn:li:tag:PII`; the real `add_tags` validates the tag URN first.

## Useful references

- DataHub MCP Server: https://docs.datahub.com/docs/features/feature-guides/mcp
- Agent Context Kit: https://docs.datahub.com/docs/dev-guides/agent-context/agent-context
- DataHub Skills: https://docs.datahub.com/docs/dev-guides/agent-context/skills
