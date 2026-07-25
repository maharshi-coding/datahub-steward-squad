import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from datahub_steward_squad.fixtures import load_graph
from datahub_steward_squad.llm import LLMUnavailable
from datahub_steward_squad.orchestrator import run_squad
from datahub_steward_squad.reasoning import apply_reasoning

FIXTURE = Path("examples/retail_finance_graph.json")


class FakeLLMClient:
    """Stubs the LLMClient interface without any network calls."""

    def __init__(self, response: str, model: str = "fake-model") -> None:
        self._response = response
        self.config = SimpleNamespace(model=model)
        self.calls = 0

    def complete(self, system: str, prompt: str) -> str:
        self.calls += 1
        return self._response


class ReasoningTest(unittest.TestCase):
    def _fresh_run(self):
        graph = load_graph(FIXTURE)
        run = run_squad(graph, objective="test", query="revenue", focus_domain="Finance", engine="deterministic")
        return graph, run

    def test_deterministic_narrative_is_grounded(self) -> None:
        graph, run = self._fresh_run()
        self.assertEqual(run.engine, "deterministic")
        self.assertIn("headline", run.narrative)
        self.assertTrue(run.narrative["prioritized_actions"])
        # Every referenced finding id must exist in the actual findings.
        finding_ids = {finding.id for finding in run.findings}
        for action in run.narrative["prioritized_actions"]:
            for fid in action["finding_ids"]:
                self.assertIn(fid, finding_ids)

    def test_llm_engine_uses_client(self) -> None:
        graph, run = self._fresh_run()
        response = json.dumps(
            {
                "headline": "Certified revenue table is failing quality checks.",
                "executive_summary": "One critical assertion failure with downstream blast radius.",
                "prioritized_actions": [
                    {"rank": 1, "title": "Fix revenue assertion", "why": "board reporting", "urgency": "now",
                     "asset_urn": "urn:li:dataset:x", "finding_ids": ["QLT-001"]}
                ],
                "reviewer_note": "Check evidence first.",
            }
        )
        client = FakeLLMClient(response)
        apply_reasoning(graph, run, engine="llm", client=client)
        self.assertEqual(client.calls, 1)
        self.assertEqual(run.engine, "llm")
        self.assertEqual(run.narrative["generated_by"], "fake-model")
        self.assertIn("Certified revenue", run.narrative["headline"])

    def test_llm_bad_json_falls_back_in_auto(self) -> None:
        graph, run = self._fresh_run()
        client = FakeLLMClient("not json at all")
        apply_reasoning(graph, run, engine="auto", client=client)
        self.assertEqual(run.engine, "deterministic")
        self.assertIn("fallback_reason", run.narrative)

    def test_llm_engine_requires_client(self) -> None:
        graph, run = self._fresh_run()
        # No API key in the environment -> engine='llm' must raise, never call out.
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(LLMUnavailable):
                apply_reasoning(graph, run, engine="llm", client=None)


if __name__ == "__main__":
    unittest.main()
