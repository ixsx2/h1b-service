"""Layer-2 curated alias map: post-canonicalize key -> target key."""

from __future__ import annotations

import csv
from pathlib import Path

ALIASES_PATH = Path(__file__).parent / "aliases.csv"


def load_aliases(path: Path | None = None) -> dict[str, str]:
    p = path or ALIASES_PATH
    aliases: dict[str, str] = {}
    if not p.exists():
        return aliases
    with p.open(encoding="utf-8", newline="") as fh:
        for row in csv.reader(fh):
            if not row or row[0].lstrip().startswith("#") or row[0] == "source_canonical":
                continue
            src, dst = row[0].strip(), row[1].strip()
            if src and dst:
                aliases[src] = dst
    for src, dst in aliases.items():
        if src == dst:
            raise ValueError(f"Self-alias: {src!r}")
        if dst in aliases:
            raise ValueError(f"Chained alias: {src!r} -> {dst!r} -> {aliases[dst]!r}")
    return aliases
