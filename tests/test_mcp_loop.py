import unittest
from pathlib import Path

from datahub_steward_squad.gateway import DataHubMCPGateway
from datahub_steward_squad.mcp_client import MCPStdioClient
from datahub_steward_squad.mcp_demo import run_mcp_demo, server_command
from datahub_steward_squad.orchestrator import run_squad

FIXTURE = "examples/retail_finance_graph.json"
REPO_ROOT = str(Path(__file__).resolve().parent.parent)


class MCPLoopTest(unittest.TestCase):
    def test_graph_is_reconstructed_from_mcp_reads(self) -> None:
        with MCPStdioClient(server_command(FIXTURE, enable_mutations=False), cwd=REPO_ROOT) as client:
            tool_names = {tool["name"] for tool in client.list_tools()}
            self.assertIn("search", tool_names)
            self.assertIn("get_lineage", tool_names)
            # Mutation tools stay hidden until explicitly enabled.
            self.assertNotIn("update_description", tool_names)

            gateway = DataHubMCPGateway(client)
            graph = gateway.build_graph()
            self.assertEqual(len(graph.assets), 7)
            self.assertTrue(graph.lineage)

    def test_mutation_tools_are_gated(self) -> None:
        with MCPStdioClient(server_command(FIXTURE, enable_mutations=False), cwd=REPO_ROOT) as client:
            with self.assertRaises(Exception):
                client.call_tool("update_description", {"urn": "x", "description": "y"})

    def test_end_to_end_writeback_lands(self) -> None:
        result = run_mcp_demo(
            fixture=FIXTURE,
            query="",
            focus_domain="Finance",
            engine="deterministic",
            apply=True,
            out=None,
            cwd=REPO_ROOT,
            log=lambda *a, **k: None,
        )
        self.assertGreater(result["proposals"], 0)
        applied = [item for item in result["applied"] if item["status"] == "applied"]
        self.assertTrue(applied)
        # At least one verified before/after change proves the mutation persisted.
        self.assertTrue(result["verification"])
        pii_changes = [c for c in result["verification"] if c["field"].endswith(".tags")]
        self.assertTrue(pii_changes)
        self.assertIn("urn:li:tag:PII", pii_changes[0]["after"])


if __name__ == "__main__":
    unittest.main()
