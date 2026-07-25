# DataHub MCP Setup

The offline demo uses `examples/retail_finance_graph.json`. For a live DataHub catalog, configure the official DataHub MCP Server.

## Bundled Mock MCP Server (no credentials)

This repo ships a DataHub-shaped MCP server so the full read → analyze → writeback → verify loop runs with zero setup:

```bash
# Run the whole loop and write changes back through MCP, then verify
python3 -m datahub_steward_squad mcp-demo --apply
```

The server (`datahub_steward_squad/mcp_server.py`) speaks newline-delimited JSON-RPC 2.0 over stdio and exposes the same tool names as the official server: `search`, `get_entities`, `get_lineage`, `list_schema_fields` (read) and `update_description`, `add_tags`, `add_terms`, `save_document` (mutation, gated behind `--enable-mutations`). `mcp_client.py` + `gateway.py` are the client side.

To drive the mock server from a general MCP host (Claude Desktop, etc.), use `mcp/datahub-steward-mock.json` (set `cwd` to this repo's absolute path).

## Going Live

Swap the bundled mock for the official server below. The gateway, agents, reasoning, and writeback logic are unchanged — only the `command`/`args` that `MCPStdioClient` launches change.

## Local MCP Server

DataHub documents the self-hosted MCP server with `uvx mcp-server-datahub@latest` and these environment variables:

- `DATAHUB_GMS_URL`
- `DATAHUB_GMS_TOKEN`

This repo includes `mcp/datahub-mcp.local.json`:

```json
{
  "mcpServers": {
    "datahub": {
      "command": "uvx",
      "args": ["mcp-server-datahub@latest"],
      "env": {
        "DATAHUB_GMS_URL": "<your-datahub-url>",
        "DATAHUB_GMS_TOKEN": "<your-datahub-token>",
        "TOOLS_IS_MUTATION_ENABLED": "true"
      }
    }
  }
}
```

Keep `TOOLS_IS_MUTATION_ENABLED=true` only when you are ready to review mutation proposals. The project never auto-applies generated plans.

## Tools Used by the Squad

Read-oriented tools:

- `search`
- `get_entities`
- `list_schema_fields`
- `get_lineage`
- `get_lineage_paths_between`
- `draft_sql_for_tables`

Mutation-oriented tools:

- `update_description`
- `add_tags`
- `add_terms`
- `set_lifecycle_stage`
- `save_document`

## Applying a Plan Manually

1. Run the project and inspect `datahub_mcp_writeback_plan.json`.
2. Remove or edit any proposal that should not be applied.
3. In an MCP-capable DataHub client, call each tool with the provided arguments.
4. Save the final `risk_report.md` or `steward_squad_document.md` as a DataHub context document.

## Useful Official References

- DataHub MCP Server: https://docs.datahub.com/docs/features/feature-guides/mcp
- Agent Context Kit: https://docs.datahub.com/docs/dev-guides/agent-context/agent-context
- DataHub Skills: https://docs.datahub.com/docs/dev-guides/agent-context/skills

