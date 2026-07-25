from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Asset, DataHubGraph, Finding, Proposal, SquadRun, TeamCard


PII_COLUMN_PATTERNS = re.compile(
    r"(^|_)(email|e_mail|phone|mobile|ssn|social_security|dob|birth_date|address|ip_address)($|_)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AgentSpec:
    name: str
    role: str
    output: str


class StewardAgent:
    spec: AgentSpec

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        raise NotImplementedError

    def card(self, state: str, evidence: list[str]) -> TeamCard:
        return TeamCard(
            id=self.spec.name.lower().replace(" ", "-"),
            title=self.spec.role,
            owner=self.spec.name,
            state=state,
            acceptance=[self.spec.output],
            merge_gate="Evidence is present in run_summary.json and risk_report.md",
            evidence=evidence,
        )


class CatalogScoutAgent(StewardAgent):
    spec = AgentSpec(
        name="Catalog Scout",
        role="Find the target DataHub assets and obvious metadata coverage gaps",
        output="Selected assets include URNs, owners, domains, descriptions, and schema coverage notes",
    )

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        selected = graph.search(query=run.query, domain=run.focus_domain)
        if not selected and run.focus_domain:
            selected = graph.search(query=run.query)
        run.selected_asset_urns = [asset.urn for asset in selected]

        missing_owner = 0
        missing_description = 0
        for asset in selected:
            if not asset.owner:
                missing_owner += 1
                run.findings.append(
                    Finding(
                        id=f"CAT-{len(run.findings) + 1:03d}",
                        agent=self.spec.name,
                        severity="high" if asset.usage_30d > 100 else "medium",
                        score=14 + min(asset.usage_30d // 50, 6),
                        asset_urn=asset.urn,
                        title=f"{asset.name} has no DataHub owner",
                        evidence=[
                            f"Domain: {asset.domain or 'unknown'}",
                            f"Usage last 30 days: {asset.usage_30d}",
                            "Owner aspect is empty in the DataHub graph sample.",
                        ],
                        recommendation="Assign a steward owner before automated metadata changes are applied.",
                        suggested_tools=["search", "get_entities", "update_description"],
                    )
                )
            if asset.entity_type == "dataset" and not asset.description:
                missing_description += 1
                run.findings.append(
                    Finding(
                        id=f"CAT-{len(run.findings) + 1:03d}",
                        agent=self.spec.name,
                        severity="medium",
                        score=10,
                        asset_urn=asset.urn,
                        title=f"{asset.name} lacks an entity description",
                        evidence=[
                            "Description is empty.",
                            f"{len(asset.columns)} schema fields are available for synthesis.",
                        ],
                        recommendation="Generate a draft description from schema, lineage, and usage context.",
                        suggested_tools=["get_entities", "update_description"],
                    )
                )

        run.metrics["selected_assets"] = len(selected)
        run.metrics["missing_owner_assets"] = missing_owner
        run.metrics["missing_description_assets"] = missing_description
        run.team_cards.append(
            self.card(
                "review",
                [
                    f"Selected {len(selected)} asset(s)",
                    f"Owner gaps: {missing_owner}",
                    f"Description gaps: {missing_description}",
                ],
            )
        )


class LineageInvestigatorAgent(StewardAgent):
    spec = AgentSpec(
        name="Lineage Investigator",
        role="Trace upstream and downstream blast radius through DataHub lineage",
        output="Each risky asset has upstream/downstream context and an impact tier",
    )

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        high_impact = 0
        for urn in run.selected_asset_urns:
            asset = graph.assets[urn]
            downstream = graph.downstream(urn, depth=3)
            upstream = graph.upstream(urn, depth=2)
            critical_children = [
                item
                for item in downstream
                if item.entity_type in {"dashboard", "mlmodel", "datajob"} or item.usage_30d > 100
            ]
            if critical_children:
                high_impact += 1
                run.findings.append(
                    Finding(
                        id=f"LIN-{len(run.findings) + 1:03d}",
                        agent=self.spec.name,
                        severity="high",
                        score=18 + min(len(critical_children) * 4, 12),
                        asset_urn=asset.urn,
                        title=f"{asset.name} has downstream production blast radius",
                        evidence=[
                            f"Upstream dependencies: {len(upstream)}",
                            f"Downstream dependencies: {len(downstream)}",
                            "Critical downstream assets: "
                            + ", ".join(child.name for child in critical_children[:5]),
                        ],
                        recommendation="Review quality and governance before schema or freshness changes are shipped.",
                        suggested_tools=["get_lineage", "get_lineage_paths_between", "save_document"],
                    )
                )

        run.metrics["high_impact_assets"] = high_impact
        run.team_cards.append(
            self.card("review", [f"High-impact lineage assets: {high_impact}"])
        )


class QualitySentinelAgent(StewardAgent):
    spec = AgentSpec(
        name="Quality Sentinel",
        role="Find failing assertions, stale assets, and unclassified sensitive fields",
        output="Quality and policy findings are ranked by severity and DataHub evidence",
    )

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        failing_assertions = 0
        pii_gaps = 0
        for urn in run.selected_asset_urns:
            asset = graph.assets[urn]
            for assertion in asset.assertions:
                if assertion.status in {"FAIL", "FAILED", "ERROR"}:
                    failing_assertions += 1
                    severity = "critical" if asset.certified or asset.usage_30d > 150 else "high"
                    run.findings.append(
                        Finding(
                            id=f"QLT-{len(run.findings) + 1:03d}",
                            agent=self.spec.name,
                            severity=severity,
                            score=30 if severity == "critical" else 22,
                            asset_urn=asset.urn,
                            title=f"{asset.name} has failing {assertion.kind} assertion",
                            evidence=[
                                f"Assertion: {assertion.name}",
                                f"Observed: {assertion.observed_value or 'not provided'}",
                                f"Expected: {assertion.expected or 'not provided'}",
                                f"Last run: {assertion.last_run_at or 'unknown'}",
                                assertion.notes or "No assertion note supplied.",
                            ],
                            recommendation="Create an incident note, notify the owner, and attach a remediation plan.",
                            suggested_tools=["get_entities", "save_document", "update_description"],
                        )
                    )

            for column in asset.columns:
                looks_sensitive = bool(PII_COLUMN_PATTERNS.search(column.name))
                already_classified = any("PII" in tag.upper() for tag in column.tags + column.terms)
                if looks_sensitive and not already_classified:
                    pii_gaps += 1
                    run.findings.append(
                        Finding(
                            id=f"PII-{len(run.findings) + 1:03d}",
                            agent=self.spec.name,
                            severity="high",
                            score=24,
                            asset_urn=asset.urn,
                            title=f"{asset.name}.{column.name} appears sensitive but is not tagged",
                            evidence=[
                                f"Column type: {column.native_type}",
                                "Column name matches sensitive-data heuristic.",
                                "No PII tag or glossary term is attached.",
                            ],
                            recommendation="Propose a PII tag or glossary term on the schema field.",
                            suggested_tools=["list_schema_fields", "add_tags", "add_terms"],
                        )
                    )

        run.metrics["failing_assertions"] = failing_assertions
        run.metrics["pii_classification_gaps"] = pii_gaps
        run.team_cards.append(
            self.card(
                "review",
                [
                    f"Failing assertions: {failing_assertions}",
                    f"PII classification gaps: {pii_gaps}",
                ],
            )
        )


class StewardshipWriterAgent(StewardAgent):
    spec = AgentSpec(
        name="Stewardship Writer",
        role="Turn findings into governed DataHub MCP writeback proposals",
        output="MCP writeback plan contains approval-gated mutation tool calls",
    )

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        grouped: dict[str, list[Finding]] = {}
        for finding in run.findings:
            grouped.setdefault(finding.asset_urn, []).append(finding)

        proposal_count = 0
        for urn, findings in grouped.items():
            asset = graph.assets[urn]
            if any("description" in finding.title.lower() for finding in findings):
                proposal_count += 1
                run.proposals.append(
                    Proposal(
                        id=f"MCP-{proposal_count:03d}",
                        tool="update_description",
                        description=f"Draft a DataHub description for {asset.name}",
                        arguments={
                            "urn": urn,
                            "description": _draft_asset_description(graph, asset),
                            "mode": "replace",
                        },
                        finding_ids=[finding.id for finding in findings if "description" in finding.title.lower()],
                    )
                )
            if any(finding.id.startswith("PII-") for finding in findings):
                for column in _sensitive_columns(asset):
                    proposal_count += 1
                    run.proposals.append(
                        Proposal(
                            id=f"MCP-{proposal_count:03d}",
                            tool="add_tags",
                            description=f"Classify {asset.name}.{column.name} as PII",
                            arguments={
                                "urn": urn,
                                "field_path": column.name,
                                "tags": ["urn:li:tag:PII"],
                            },
                            finding_ids=[finding.id for finding in findings if finding.id.startswith("PII-")],
                        )
                    )

        document = _build_steward_document(graph, run)
        proposal_count += 1
        run.proposals.append(
            Proposal(
                id=f"MCP-{proposal_count:03d}",
                tool="save_document",
                description="Save the squad risk brief into DataHub context documents",
                arguments={
                    "title": "Steward Squad Risk Brief",
                    "content": document,
                    "parent_folder": "Agent Stewardship",
                },
                finding_ids=[finding.id for finding in run.findings[:12]],
            )
        )
        run.steward_document = document
        run.team_cards.append(
            self.card("review", [f"Generated {len(run.proposals)} approval-gated MCP proposal(s)"])
        )


class ReleaseCaptainAgent(StewardAgent):
    spec = AgentSpec(
        name="Release Captain",
        role="Package the run for judges: SQL guardrails, board state, and demo evidence",
        output="Generated artifacts are ready for README, demo video, and sample-output review",
    )

    def run(self, graph: DataHubGraph, run: SquadRun) -> None:
        run.generated_sql = _generate_quality_sql(graph, run)
        run.metrics["critical_findings"] = sum(1 for item in run.findings if item.severity == "critical")
        run.metrics["high_findings"] = sum(1 for item in run.findings if item.severity == "high")
        run.metrics["mcp_writeback_proposals"] = len(run.proposals)
        run.team_cards.append(
            self.card(
                "review",
                [
                    "Generated SQL guardrail artifact",
                    "Generated dashboard and sample output package",
                    f"Total findings: {len(run.findings)}",
                ],
            )
        )


def build_default_team() -> list[StewardAgent]:
    return [
        CatalogScoutAgent(),
        LineageInvestigatorAgent(),
        QualitySentinelAgent(),
        StewardshipWriterAgent(),
        ReleaseCaptainAgent(),
    ]


def _sensitive_columns(asset: Asset):
    for column in asset.columns:
        if PII_COLUMN_PATTERNS.search(column.name) and not any(
            "PII" in value.upper() for value in column.tags + column.terms
        ):
            yield column


def _draft_asset_description(graph: DataHubGraph, asset: Asset) -> str:
    upstream = ", ".join(item.name for item in graph.upstream(asset.urn, depth=1)) or "no upstream assets recorded"
    downstream = ", ".join(item.name for item in graph.downstream(asset.urn, depth=1)) or "no downstream assets recorded"
    owner = asset.owner or "an assigned steward"
    return (
        f"{asset.name} is a {asset.platform} {asset.entity_type} in the {asset.domain or 'unassigned'} "
        f"domain. It is owned by {owner}, receives data from {upstream}, and supports {downstream}. "
        "This description was drafted by DataHub Steward Squad from DataHub metadata context and should "
        "be reviewed by the owning data team before approval."
    )


def _build_steward_document(graph: DataHubGraph, run: SquadRun) -> str:
    top = sorted(run.findings, key=lambda item: item.score, reverse=True)[:8]
    lines = [
        "# Steward Squad Risk Brief",
        "",
        f"Objective: {run.objective}",
        f"Focus domain: {run.focus_domain or 'all'}",
        f"Assets inspected: {len(run.selected_asset_urns)}",
        "",
        "## Top Findings",
    ]
    for finding in top:
        asset = graph.assets.get(finding.asset_urn)
        lines.extend(
            [
                "",
                f"### {finding.severity.upper()}: {finding.title}",
                f"- URN: `{finding.asset_urn}`",
                f"- Asset: {asset.name if asset else 'unknown'}",
                f"- Score: {finding.score}",
                f"- Recommendation: {finding.recommendation}",
            ]
        )
    lines.extend(
        [
            "",
            "## Proposed Writeback",
            "Every mutation is approval-gated. Review the generated MCP plan before applying changes.",
        ]
    )
    return "\n".join(lines)


def _generate_quality_sql(graph: DataHubGraph, run: SquadRun) -> str:
    statements: list[str] = [
        "-- Generated by DataHub Steward Squad.",
        "-- These SQL checks are examples for reviewers; adapt warehouse syntax before production use.",
        "",
    ]
    for urn in run.selected_asset_urns:
        asset = graph.assets[urn]
        if asset.entity_type != "dataset":
            continue
        sensitive = list(_sensitive_columns(asset))
        failing = [item for item in asset.assertions if item.status in {"FAIL", "FAILED", "ERROR"}]
        if not sensitive and not failing:
            continue
        table_name = asset.properties.get("table", asset.name)
        if sensitive:
            for column in sensitive:
                statements.extend(
                    [
                        f"-- PII null-rate guardrail for {asset.name}.{column.name}",
                        f"select count(*) as row_count,",
                        f"       sum(case when {column.name} is null then 1 else 0 end) as null_count",
                        f"from {table_name};",
                        "",
                    ]
                )
        if failing:
            statements.extend(
                [
                    f"-- Freshness guardrail for {asset.name}",
                    "select max(_loaded_at) as latest_loaded_at",
                    f"from {table_name}",
                    "having max(_loaded_at) >= current_timestamp - interval '24 hours';",
                    "",
                ]
            )
    return "\n".join(statements).strip() + "\n"

