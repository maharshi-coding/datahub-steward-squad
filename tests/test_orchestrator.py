import tempfile
import unittest
from pathlib import Path

from datahub_steward_squad.fixtures import load_graph
from datahub_steward_squad.orchestrator import run_squad
from datahub_steward_squad.render import write_outputs


FIXTURE = Path("examples/retail_finance_graph.json")


class OrchestratorTest(unittest.TestCase):
    def test_squad_finds_quality_and_pii_risks(self) -> None:
        graph = load_graph(FIXTURE)
        run = run_squad(graph, objective="test", query="revenue", focus_domain="Finance")

        self.assertTrue(run.selected_asset_urns)
        self.assertTrue(any(finding.severity == "critical" for finding in run.findings))
        self.assertTrue(any("appears sensitive" in finding.title for finding in run.findings))
        self.assertTrue(any(proposal.tool == "save_document" for proposal in run.proposals))
        self.assertIn("finance.fct_revenue", run.generated_sql)

    def test_outputs_are_written(self) -> None:
        graph = load_graph(FIXTURE)
        run = run_squad(graph, objective="test", query="revenue", focus_domain="Finance")
        with tempfile.TemporaryDirectory() as tmp:
            outputs = write_outputs(graph, run, Path(tmp))

            for path in outputs.values():
                self.assertTrue(path.exists())
                self.assertTrue(path.read_text(encoding="utf-8").strip())

            mcp_plan = outputs["mcp_plan"].read_text(encoding="utf-8")
            self.assertIn("datahub_mcp_writeback_plan", mcp_plan)
            self.assertTrue("update_description" in mcp_plan or "add_tags" in mcp_plan)


if __name__ == "__main__":
    unittest.main()

