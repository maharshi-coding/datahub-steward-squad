"""DataHub Steward Squad: ECC-style multi-agent DataHub metadata stewardship.

Public API:
    run_squad         -- run the worker team + Chief Steward reasoning over a graph
    run_mcp_demo      -- run the full read -> analyze -> writeback -> verify MCP loop
    load_graph        -- load a DataHub-shaped fixture graph
    write_outputs     -- render judge-facing artifacts
"""

from .fixtures import load_graph
from .mcp_demo import run_mcp_demo
from .orchestrator import run_squad
from .render import write_outputs

__version__ = "0.1.0"

__all__ = ["run_squad", "run_mcp_demo", "load_graph", "write_outputs", "__version__"]
