"""Tests for the live DataHub adapter (datahub_steward_squad.live).

These exercise the real-response adapter against RECORDED fixtures captured from
an actual ``mcp-server-datahub`` (see scripts/explore_live_mcp.py) plus a fake
MCP client, so they run in CI with no DataHub, no network, and no uvx — while
still asserting the exact shapes the live server returns.
"""

import json
import os
import unittest
from pathlib import Path

from datahub_steward_squad.live import (
    LiveConfigError,
    LiveDataHubMCPGateway,
    live_server_command,
    live_server_env,
    load_dotenv,
    parse_entity,
    translate_proposal,
)
from datahub_steward_squad.models import Proposal

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "live"
FCT = "urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.fct_revenue,PROD)"


def _load(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FakeLiveClient:
    """Stands in for MCPStdioClient, replaying recorded real-server responses."""

    def __init__(self):
        self.calls = []
        self._entities = {e["urn"]: e for e in _load("get_entities")}
        self._entities.update({e["urn"]: e for e in _load("get_entities_dim_customer")})

    def call_tool(self, name, arguments=None):
        arguments = arguments or {}
        self.calls.append((name, arguments))
        if name == "search":
            return _load("search")
        if name == "get_entities":
            urns = arguments.get("urns", [])
            return [self._entities[u] for u in urns if u in self._entities]
        if name == "get_lineage":
            if arguments.get("urn") != FCT:
                return {}
            return _load("get_lineage_upstream" if arguments.get("upstream") else "get_lineage_downstream")
        # Mutation tools: mimic the real {success, message} envelope.
        return {"success": True, "message": f"{name} ok"}


class ParseEntityTest(unittest.TestCase):
    def test_parse_real_entity_maps_all_fields(self):
        asset = parse_entity(_load("get_entities")[0])
        self.assertEqual(asset.urn, FCT)
        self.assertEqual(asset.name, "finance.fct_revenue")
        self.assertEqual(asset.entity_type, "dataset")
        self.assertEqual(asset.platform, "snowflake")  # from {"urn","name"} object
        self.assertEqual(asset.domain, "Finance")
        self.assertEqual(asset.owner, "urn:li:corpGroup:finance-analytics")
        self.assertEqual(asset.usage_30d, 423)  # flattened from customProperties list
        self.assertTrue(asset.certified)
        self.assertIn("Certified revenue", asset.description)

    def test_columns_and_field_terms(self):
        asset = parse_entity(_load("get_entities")[0])
        cols = {c.name: c for c in asset.columns}
        # customer_email is present and NOT classified -> squad should flag it.
        self.assertIn("customer_email", cols)
        self.assertEqual(cols["customer_email"].tags, [])
        # Field-level glossary terms arrive as plain name strings.
        self.assertEqual(cols["customer_id"].terms, ["Customer"])

    def test_edited_tags_are_merged(self):
        """add_tags writes editableSchemaMetadata, surfaced as 'editedTags'."""
        entity = {
            "urn": FCT,
            "properties": {"name": "t"},
            "schemaMetadata": {
                "fields": [
                    {"fieldPath": "email", "nativeDataType": "varchar", "editedTags": ["PII"]},
                    {"fieldPath": "id", "nativeDataType": "varchar", "tags": ["Key"], "editedTags": ["Key"]},
                ]
            },
        }
        cols = {c.name: c for c in parse_entity(entity).columns}
        self.assertEqual(cols["email"].tags, ["PII"])
        self.assertEqual(cols["id"].tags, ["Key"])  # deduped across tags + editedTags

    def test_entity_type_inferred_from_urn(self):
        dashboard = parse_entity({"urn": "urn:li:dashboard:(looker,x)", "properties": {"name": "x"}})
        self.assertEqual(dashboard.entity_type, "dashboard")


class TranslateProposalTest(unittest.TestCase):
    def test_update_description(self):
        tool, args = translate_proposal(
            Proposal(id="P1", tool="update_description", description="",
                     arguments={"urn": FCT, "description": "d", "mode": "replace"}, finding_ids=[])
        )
        self.assertEqual(tool, "update_description")
        self.assertEqual(args, {"entity_urn": FCT, "operation": "replace", "description": "d"})

    def test_add_tags_batches_and_renames(self):
        tool, args = translate_proposal(
            Proposal(id="P2", tool="add_tags", description="",
                     arguments={"urn": FCT, "field_path": "customer_email", "tags": ["urn:li:tag:PII"]},
                     finding_ids=[])
        )
        self.assertEqual(tool, "add_tags")
        self.assertEqual(args, {"tag_urns": ["urn:li:tag:PII"], "entity_urns": [FCT],
                                "column_paths": ["customer_email"]})

    def test_add_terms(self):
        tool, args = translate_proposal(
            Proposal(id="P3", tool="add_terms", description="",
                     arguments={"urn": FCT, "field_path": "x", "terms": ["urn:li:glossaryTerm:PII"]},
                     finding_ids=[])
        )
        self.assertEqual(tool, "add_terms")
        self.assertEqual(args["term_urns"], ["urn:li:glossaryTerm:PII"])
        self.assertEqual(args["entity_urns"], [FCT])

    def test_save_document_sets_required_document_type(self):
        tool, args = translate_proposal(
            Proposal(id="P4", tool="save_document", description="",
                     arguments={"title": "Brief", "content": "body", "parent_folder": "x"}, finding_ids=[])
        )
        self.assertEqual(tool, "save_document")
        self.assertEqual(args["document_type"], "Summary")
        self.assertEqual(args["title"], "Brief")
        self.assertNotIn("parent_folder", args)


class LiveGatewayTest(unittest.TestCase):
    def test_build_graph_from_recorded_responses(self):
        gateway = LiveDataHubMCPGateway(FakeLiveClient())
        graph = gateway.build_graph()
        self.assertIn(FCT, graph.assets)
        self.assertEqual(graph.assets[FCT].usage_30d, 423)
        # Upstream fixture yields dim_customer + raw.payments -> fct; downstream yields fct -> mart.
        edges = {(e.upstream, e.downstream) for e in graph.lineage}
        self.assertIn(("urn:li:dataset:(urn:li:dataPlatform:snowflake,finance.dim_customer,PROD)", FCT), edges)
        self.assertIn((FCT, "urn:li:dataset:(urn:li:dataPlatform:dbt,analytics.mart_revenue_by_region,PROD)"), edges)

    def test_read_asset_returns_asset_shaped_dict(self):
        gateway = LiveDataHubMCPGateway(FakeLiveClient())
        asset = gateway.read_asset(FCT)
        self.assertIsNotNone(asset)
        self.assertEqual(asset["urn"], FCT)
        self.assertIn("columns", asset)  # matches the mock read shape used by verification

    def test_apply_proposal_translates_to_real_tool(self):
        client = FakeLiveClient()
        gateway = LiveDataHubMCPGateway(client)
        proposal = Proposal(id="MCP-001", tool="add_tags", description="",
                            arguments={"urn": FCT, "field_path": "customer_email", "tags": ["urn:li:tag:PII"]},
                            finding_ids=[])
        results = gateway.apply_proposals([proposal], approved_ids={"MCP-001"})
        self.assertEqual(results[0]["status"], "applied")
        # The real server was called with the translated batch args, not the mock shape.
        add_tags_calls = [a for (n, a) in client.calls if n == "add_tags"]
        self.assertEqual(add_tags_calls[0]["entity_urns"], [FCT])
        self.assertEqual(add_tags_calls[0]["column_paths"], ["customer_email"])

    def test_approval_gate_skips_unapproved(self):
        gateway = LiveDataHubMCPGateway(FakeLiveClient())
        proposal = Proposal(id="MCP-009", tool="add_tags", description="",
                            arguments={"urn": FCT, "field_path": "x", "tags": ["urn:li:tag:PII"]}, finding_ids=[])
        results = gateway.apply_proposals([proposal], approved_ids=set())
        self.assertEqual(results[0]["status"], "skipped")


class LiveConfigTest(unittest.TestCase):
    def test_load_dotenv_sets_missing_vars(self):
        tmp = FIXTURES / "_tmp.env"
        tmp.write_text('DH_TEST_ONE=alpha\n# comment\nDH_TEST_TWO="beta"\n', encoding="utf-8")
        os.environ.pop("DH_TEST_ONE", None)
        os.environ.pop("DH_TEST_TWO", None)
        try:
            parsed = load_dotenv(tmp)
            self.assertEqual(parsed["DH_TEST_ONE"], "alpha")
            self.assertEqual(os.environ["DH_TEST_TWO"], "beta")  # quotes stripped
        finally:
            tmp.unlink()
            os.environ.pop("DH_TEST_ONE", None)
            os.environ.pop("DH_TEST_TWO", None)

    def test_live_server_env_requires_url(self):
        saved = os.environ.pop("DATAHUB_GMS_URL", None)
        try:
            with self.assertRaises(LiveConfigError):
                live_server_env(enable_mutations=True)
        finally:
            if saved is not None:
                os.environ["DATAHUB_GMS_URL"] = saved

    def test_live_server_env_builds_env(self):
        os.environ["DATAHUB_GMS_URL"] = "http://localhost:8080"
        os.environ["DATAHUB_GMS_TOKEN"] = "tok123"
        try:
            env = live_server_env(enable_mutations=True)
            self.assertEqual(env["DATAHUB_GMS_URL"], "http://localhost:8080")
            self.assertEqual(env["TOOLS_IS_MUTATION_ENABLED"], "true")
            self.assertEqual(env["DATAHUB_GMS_TOKEN"], "tok123")
            self.assertEqual(live_server_env(enable_mutations=False)["TOOLS_IS_MUTATION_ENABLED"], "false")
        finally:
            os.environ.pop("DATAHUB_GMS_TOKEN", None)

    def test_default_command_is_official_server(self):
        os.environ.pop("DATAHUB_MCP_COMMAND", None)
        self.assertEqual(live_server_command(), ["uvx", "mcp-server-datahub@latest"])


if __name__ == "__main__":
    unittest.main()
