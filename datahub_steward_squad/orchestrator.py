from __future__ import annotations

from .agents import build_default_team
from .models import DataHubGraph, SquadRun
from .reasoning import apply_reasoning


def run_squad(
    graph: DataHubGraph,
    objective: str,
    query: str = "",
    focus_domain: str = "",
    engine: str = "auto",
    model: str | None = None,
) -> SquadRun:
    run = SquadRun(objective=objective, query=query, focus_domain=focus_domain)
    for agent in build_default_team():
        agent.run(graph, run)
    run.findings.sort(key=_finding_priority)
    apply_reasoning(graph, run, engine=engine, model=model)
    return run


_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _finding_priority(finding) -> tuple[int, int]:
    """Rank critical risks first, then by descending detection score."""

    return (_SEVERITY_RANK.get(finding.severity, 4), -finding.score)
