from __future__ import annotations

import json
from pathlib import Path

from .models import DataHubGraph


def load_graph(path: str | Path) -> DataHubGraph:
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return DataHubGraph.from_dict(raw)

