from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Column:
    name: str
    native_type: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Column":
        return cls(
            name=raw["name"],
            native_type=raw.get("native_type", raw.get("type", "unknown")),
            description=raw.get("description", ""),
            tags=list(raw.get("tags", [])),
            terms=list(raw.get("terms", [])),
        )


@dataclass
class AssertionResult:
    name: str
    kind: str
    status: str
    last_run_at: str = ""
    observed_value: str = ""
    expected: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AssertionResult":
        return cls(
            name=raw["name"],
            kind=raw.get("kind", "custom"),
            status=raw.get("status", "UNKNOWN").upper(),
            last_run_at=raw.get("last_run_at", ""),
            observed_value=str(raw.get("observed_value", "")),
            expected=str(raw.get("expected", "")),
            notes=raw.get("notes", ""),
        )


@dataclass
class Asset:
    urn: str
    name: str
    entity_type: str
    platform: str
    env: str = "PROD"
    domain: str = ""
    owner: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)
    columns: list[Column] = field(default_factory=list)
    assertions: list[AssertionResult] = field(default_factory=list)
    usage_30d: int = 0
    certified: bool = False
    lifecycle: str = "approved"
    properties: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Asset":
        return cls(
            urn=raw["urn"],
            name=raw["name"],
            entity_type=raw.get("entity_type", "dataset"),
            platform=raw.get("platform", "unknown"),
            env=raw.get("env", "PROD"),
            domain=raw.get("domain", ""),
            owner=raw.get("owner", ""),
            description=raw.get("description", ""),
            tags=list(raw.get("tags", [])),
            terms=list(raw.get("terms", [])),
            columns=[Column.from_dict(item) for item in raw.get("columns", [])],
            assertions=[AssertionResult.from_dict(item) for item in raw.get("assertions", [])],
            usage_30d=int(raw.get("usage_30d", 0)),
            certified=bool(raw.get("certified", False)),
            lifecycle=raw.get("lifecycle", "approved"),
            properties=dict(raw.get("properties", {})),
        )

    def has_tag_or_term(self, needle: str) -> bool:
        normalized = needle.lower()
        values = self.tags + self.terms
        return any(normalized in value.lower() for value in values)


@dataclass
class LineageEdge:
    upstream: str
    downstream: str
    edge_type: str = "TRANSFORMED"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LineageEdge":
        return cls(
            upstream=raw["upstream"],
            downstream=raw["downstream"],
            edge_type=raw.get("edge_type", "TRANSFORMED"),
        )


@dataclass
class DataHubGraph:
    assets: dict[str, Asset]
    lineage: list[LineageEdge]
    glossary: dict[str, str] = field(default_factory=dict)
    documents: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "DataHubGraph":
        assets = {item["urn"]: Asset.from_dict(item) for item in raw.get("assets", [])}
        return cls(
            assets=assets,
            lineage=[LineageEdge.from_dict(item) for item in raw.get("lineage", [])],
            glossary=dict(raw.get("glossary", {})),
            documents=list(raw.get("documents", [])),
        )

    def search(self, query: str = "", domain: str = "", entity_types: set[str] | None = None) -> list[Asset]:
        needle = query.lower().strip()
        results: list[Asset] = []
        for asset in self.assets.values():
            if domain and asset.domain.lower() != domain.lower():
                continue
            if entity_types and asset.entity_type not in entity_types:
                continue
            haystack = " ".join(
                [
                    asset.name,
                    asset.urn,
                    asset.description,
                    asset.domain,
                    asset.platform,
                    " ".join(asset.tags),
                    " ".join(asset.terms),
                    " ".join(column.name for column in asset.columns),
                ]
            ).lower()
            if not needle or needle in haystack:
                results.append(asset)
        return sorted(results, key=lambda item: (-item.usage_30d, item.name))

    def downstream(self, urn: str, depth: int = 2) -> list[Asset]:
        return self._walk(urn=urn, depth=depth, direction="downstream")

    def upstream(self, urn: str, depth: int = 2) -> list[Asset]:
        return self._walk(urn=urn, depth=depth, direction="upstream")

    def _walk(self, urn: str, depth: int, direction: str) -> list[Asset]:
        seen: set[str] = set()
        frontier = {urn}
        for _ in range(depth):
            next_frontier: set[str] = set()
            for edge in self.lineage:
                source = edge.upstream if direction == "downstream" else edge.downstream
                target = edge.downstream if direction == "downstream" else edge.upstream
                if source in frontier and target not in seen and target in self.assets:
                    next_frontier.add(target)
            seen.update(next_frontier)
            frontier = next_frontier
        return [self.assets[item] for item in seen if item in self.assets]


@dataclass
class Finding:
    id: str
    agent: str
    severity: str
    score: int
    asset_urn: str
    title: str
    evidence: list[str]
    recommendation: str
    suggested_tools: list[str] = field(default_factory=list)


@dataclass
class Proposal:
    id: str
    tool: str
    description: str
    arguments: dict[str, Any]
    finding_ids: list[str]
    requires_approval: bool = True


@dataclass
class TeamCard:
    id: str
    title: str
    owner: str
    state: str
    acceptance: list[str]
    merge_gate: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class SquadRun:
    objective: str
    query: str
    focus_domain: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    selected_asset_urns: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)
    generated_sql: str = ""
    steward_document: str = ""
    team_cards: list[TeamCard] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    engine: str = "deterministic"
    narrative: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
