#!/usr/bin/env python3
"""
Emit a Graphviz DOT directed graph of ORM foreign keys.

Edge meaning:  referenced_table -> referencing_table
(so the arrowhead points at the child row that holds the FK column).

Usage:
  uv run python scripts/schema_fk_graph.py > schema_fk.dot
  dot -Tsvg schema_fk.dot -o schema_fk.svg
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _cluster_order() -> list[str]:
    return ["roots", "people", "event_core", "structure", "entries", "timing", "other"]


def _cluster(table: str) -> str:
    if table in {"countries", "seasons", "entrants", "groups", "manufacturers"}:
        return "roots"
    if table == "persons":
        return "people"
    if table in {"events", "event_classes", "etl_run_log"}:
        return "event_core"
    if table in {
        "rallies",
        "start_lists",
        "itineraries",
        "itinerary_legs",
        "itinerary_sections",
        "stages",
        "controls",
    }:
        return "structure"
    if table in {
        "entries",
        "rally_event_classes",
        "entry_event_classes",
        "start_list_items",
    }:
        return "entries"
    if table in {"rally_standings", "split_times", "stage_times", "shakedown_times"}:
        return "timing"
    return "other"


_CLUSTER_LABEL = {
    "roots": "Dimensions (no WRC FK parents)",
    "people": "People",
    "event_core": "Event anchor",
    "structure": "Itinerary and stages",
    "entries": "Entries and class links",
    "timing": "Timing results",
    "other": "Other",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write DOT here (default: stdout)",
    )
    args = parser.parse_args()

    import openwrc.models.db  # noqa: F401 — register models
    from openwrc.models.db.base import Base

    lines: list[str] = [
        "// Generated from SQLAlchemy Base.metadata foreign keys.",
        "// Arrow: referenced_table -> referencing_table (FK lives on head node).",
        "digraph schema_fk {",
        "  graph [rankdir=TB; fontsize=10; labelloc=t];",
        '  node [shape=box; fontname="Helvetica"];',
        '  edge [fontname="Helvetica"; fontsize=8];',
        "",
    ]

    tables = list(Base.metadata.sorted_tables)
    by_cluster: dict[str, list[str]] = {}
    for t in tables:
        by_cluster.setdefault(_cluster(t.name), []).append(t.name)

    order = _cluster_order()
    for ckey in sorted(
        by_cluster.keys(), key=lambda k: (order.index(k) if k in order else len(order))
    ):
        label = _CLUSTER_LABEL.get(ckey, ckey)
        lines.append(f"  subgraph cluster_{ckey} {{")
        lines.append(f'    label="{label}"; style=dashed; color=gray50;')
        for name in sorted(by_cluster[ckey]):
            lines.append(f'    "{name}";')
        lines.append("  }")
        lines.append("")

    for t in tables:
        for fk in t.foreign_keys:
            parent = fk.column.table.name
            child = t.name
            col = fk.parent.key
            refcol = fk.column.key
            lines.append(f'  "{parent}" -> "{child}" [label="{col}→{refcol}"];')

    lines.append("}")
    text = "\n".join(lines) + "\n"

    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
