#!/usr/bin/env python3
"""Report canonical-key collisions introduced by the new canonicalize().

Baseline = the current data/h1b_data.db built with the OLD normalizer.
A collision = one NEW canonical key receiving filed names that the OLD
normalizer kept as 2+ distinct keys. Most are the intended merges (that is
the point of Layer 1); the report exists so the unintended ones are visible
and can be eyeballed before the rebuild is trusted. Run BEFORE rebuilding."""

from __future__ import annotations

import csv
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.canonicalize import canonicalize  # noqa: E402

DB = ROOT / "data" / "h1b_data.db"
OUT = ROOT / "data" / "normalization_collisions.csv"


def main() -> int:
    if not DB.exists():
        print(f"Baseline DB missing: {DB} — run against a pre-Layer-1 build.")
        return 1
    conn = sqlite3.connect(DB)

    # old canonical -> corpus-wide volume (for ranking)
    volume: dict[str, tuple[int, int]] = {}
    for canon, appr, cert in conn.execute(
        "SELECT canonical_employer, SUM(uscis_new_approvals), SUM(certified_count)"
        " FROM aggregates GROUP BY canonical_employer"
    ):
        volume[canon] = (appr or 0, cert or 0)

    new_to_old: dict[str, set[str]] = defaultdict(set)
    for filed, old_canon in conn.execute(
        "SELECT filed_name, canonical_employer FROM filed_names"
    ):
        new_to_old[canonicalize(filed)].add(old_canon)
    conn.close()

    rows = []
    for new_key, old_keys in new_to_old.items():
        if len(old_keys) < 2:
            continue
        appr = sum(volume.get(k, (0, 0))[0] for k in old_keys)
        cert = sum(volume.get(k, (0, 0))[1] for k in old_keys)
        rows.append((new_key, " | ".join(sorted(old_keys)), len(old_keys), appr, cert))
    rows.sort(key=lambda r: r[3], reverse=True)

    with OUT.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            ["new_canonical", "old_canonicals", "n_old_keys",
             "total_new_approvals", "total_certified"]
        )
        w.writerows(rows)

    print(f"{len(rows):,} collisions -> {OUT}")
    print("Top 20 by USCIS new approvals:")
    for r in rows[:20]:
        print(f"  {r[3]:>7,} appr  {r[0]!r}  <=  {r[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
