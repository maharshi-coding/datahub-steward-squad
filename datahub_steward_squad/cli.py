from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .fixtures import load_graph
from .llm import LLMUnavailable
from .orchestrator import run_squad
from .render import write_outputs


def _llm_unavailable(error: LLMUnavailable) -> int:
    """Print a clean, actionable message for an --engine llm failure (no traceback)."""

    print(f"\nClaude engine unavailable: {error}", file=sys.stderr)
    print(
        "Fix one of these, then retry:\n"
        "  - Add API credits: https://console.anthropic.com/settings/billing\n"
        "  - Check the key:   echo \"len=${#ANTHROPIC_API_KEY}\"\n"
        "  - Or fall back:    re-run with --engine auto (uses the deterministic engine if Claude is unavailable)",
        file=sys.stderr,
    )
    return 1


DEFAULT_OBJECTIVE = (
    "Detect DataHub metadata risks in a Finance data product, reason over lineage and quality, "
    "and prepare governed MCP writeback proposals."
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="datahub-steward-squad",
        description="Run an ECC-style DataHub steward agent team.",
    )
    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser("run", help="Run the steward squad over a DataHub fixture graph")
    run.add_argument(
        "--fixture",
        default="examples/retail_finance_graph.json",
        help="Path to a DataHub-shaped metadata graph fixture.",
    )
    run.add_argument("--out", default="examples/outputs/latest", help="Output directory for generated artifacts.")
    run.add_argument("--query", default="revenue", help="Catalog query to investigate.")
    run.add_argument("--focus-domain", default="Finance", help="DataHub domain to focus on.")
    run.add_argument("--objective", default=DEFAULT_OBJECTIVE, help="Plain-language objective for this run.")
    run.add_argument(
        "--engine",
        default="auto",
        choices=["auto", "llm", "deterministic"],
        help=(
            "Reasoning engine for the Chief Steward brief. "
            "auto: use Claude when ANTHROPIC_API_KEY is set, else deterministic. "
            "llm: require Claude. deterministic: never call an LLM."
        ),
    )
    run.add_argument(
        "--model",
        default=None,
        help="Override the Claude model id (default: STEWARD_LLM_MODEL or claude-sonnet-5).",
    )

    inspect = subcommands.add_parser("inspect-fixture", help="Print a quick inventory of a fixture graph")
    inspect.add_argument("--fixture", default="examples/retail_finance_graph.json")

    mcp = subcommands.add_parser(
        "mcp-demo",
        help="Run the full DataHub MCP loop (read -> analyze -> writeback -> verify). "
        "Use --live against a real DataHub; default is the bundled offline mock.",
    )
    mcp.add_argument("--fixture", default="examples/retail_finance_graph.json")
    mcp.add_argument("--out", default="examples/outputs/latest", help="Output directory for artifacts.")
    mcp.add_argument("--query", default="revenue")
    mcp.add_argument("--focus-domain", default="Finance")
    mcp.add_argument("--engine", default="auto", choices=["auto", "llm", "deterministic"])
    mcp.add_argument("--model", default=None)
    mcp.add_argument(
        "--live",
        action="store_true",
        help="Run against a REAL DataHub via the official 'uvx mcp-server-datahub'. "
        "Reads DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN / TOOLS_IS_MUTATION_ENABLED from env or .env. "
        "Without --live, uses the zero-credential bundled mock server.",
    )
    mcp.add_argument(
        "--apply",
        action="store_true",
        help="Approve and apply the writeback proposals via MCP mutation tools, then verify by re-reading.",
    )
    mcp.add_argument(
        "--approve",
        default=None,
        help="Comma-separated proposal ids to approve (default with --apply: all). Example: MCP-001,MCP-003",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "mcp-demo":
        from .mcp_demo import run_mcp_demo

        approved_ids = None
        if args.approve:
            approved_ids = {item.strip() for item in args.approve.split(",") if item.strip()}
        target = "a live DataHub" if args.live else "the bundled offline mock server"
        print(f"Starting DataHub MCP loop against {target}...")
        try:
            result = run_mcp_demo(
                fixture=args.fixture,
                query=args.query,
                focus_domain=args.focus_domain,
                engine=args.engine,
                model=args.model,
                apply=args.apply,
                approved_ids=approved_ids,
                out=args.out,
                live=args.live,
            )
        except LLMUnavailable as error:
            return _llm_unavailable(error)
        except Exception as error:  # live-mode config/connection errors: no traceback
            if args.live:
                print(f"\nLive DataHub MCP loop failed: {error}", file=sys.stderr)
                print(
                    "Check that DataHub is running (datahub docker quickstart), that "
                    "DATAHUB_GMS_URL is set (see .env.example), and that 'uvx' is installed.\n"
                    "The offline demo always works: python -m datahub_steward_squad mcp-demo --apply",
                    file=sys.stderr,
                )
                return 1
            raise
        print("")
        print("MCP loop complete.")
        if not args.apply:
            print("Dry run: proposals were generated but not applied. Re-run with --apply to write back.")
        return 0

    if args.command == "inspect-fixture":
        graph = load_graph(args.fixture)
        dataset_count = sum(1 for asset in graph.assets.values() if asset.entity_type == "dataset")
        print(f"Assets: {len(graph.assets)}")
        print(f"Datasets: {dataset_count}")
        print(f"Lineage edges: {len(graph.lineage)}")
        print(f"Glossary terms: {len(graph.glossary)}")
        return 0

    if args.command in {None, "run"}:
        graph = load_graph(args.fixture)
        try:
            run = run_squad(
                graph=graph,
                objective=args.objective,
                query=args.query,
                focus_domain=args.focus_domain,
                engine=args.engine,
                model=args.model,
            )
        except LLMUnavailable as error:
            return _llm_unavailable(error)
        outputs = write_outputs(graph, run, Path(args.out))
        print("DataHub Steward Squad run complete.")
        print(f"Engine: {run.engine} ({run.narrative.get('generated_by', 'deterministic')})")
        print(f"Findings: {len(run.findings)}")
        print(f"MCP proposals: {len(run.proposals)}")
        for name, path in outputs.items():
            print(f"{name}: {path}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

