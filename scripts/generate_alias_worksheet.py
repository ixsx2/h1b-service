#!/usr/bin/env python3
"""Layer-2 alias worksheet: suggest LCA-side matches for USCIS orphans.

Suggests, never merges. A human fills the `accept` column; `--apply` copies
accepted rows into etl/aliases.csv. Fuzzy scoring is stdlib difflib against the
full LCA name set (no first-token blocking): blocking misses divergent legal
names the orphan shares no leading word with. Bake-off-validated: high recall,
but ~15-20% of high-scoring suggestions are wrong-same — Amazon->AWS at 0.84,
and geographic qualifiers like UPenn->Indiana Univ of Pennsylvania — hence the
mandatory human review, and the golden regression suite that freezes known
distinct-entity pairs."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.aliases import ALIASES_PATH, load_aliases  # noqa: E402

DB = ROOT / "data" / "h1b_data.db"
WORKSHEET = ROOT / "data" / "alias_worksheet.csv"
MIN_RATIO = 0.72
ACCEPT_VALUES = {"y", "yes", "x", "1"}


def generate(limit: int) -> None:
    conn = sqlite3.connect(DB)
    latest = int(
        conn.execute("SELECT value FROM meta WHERE key='latest_complete_fy'").fetchone()[0]
    )
    orphans = conn.execute(
        "SELECT canonical_employer, uscis_new_approvals FROM aggregates"
        " WHERE fiscal_year=? AND uscis_new_approvals>0 AND certified_count=0"
        " ORDER BY uscis_new_approvals DESC LIMIT ?",
        (latest, limit),
    ).fetchall()
    lca_all = [name for (name,) in conn.execute(
        "SELECT canonical_employer FROM aggregates WHERE fiscal_year=? AND certified_count>0",
        (latest,),
    )]
    conn.close()

    existing = load_aliases()
    with WORKSHEET.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["orphan", "suggestion", "score", "approvals", "accept"])
        for canon, appr in orphans:
            if canon in existing:
                continue
            best, best_r = "", 0.0
            for lca in lca_all:
                r = SequenceMatcher(None, canon, lca).ratio()
                if r > best_r:
                    best, best_r = lca, r
            if best_r < MIN_RATIO:
                best, best_r = "", 0.0
            w.writerow([canon, best, f"{best_r:.2f}" if best else "", appr, ""])
    print(f"Worksheet -> {WORKSHEET} ({len(orphans)} orphans). Fill 'accept', then --apply.")


def apply_worksheet(path: Path) -> None:
    existing = load_aliases()
    added = 0
    with path.open(encoding="utf-8", newline="") as fh, ALIASES_PATH.open(
        "a", encoding="utf-8", newline=""
    ) as out:
        w = csv.writer(out)
        for row in csv.DictReader(fh):
            if row["accept"].strip().lower() not in ACCEPT_VALUES:
                continue
            src, dst = row["orphan"].strip(), row["suggestion"].strip()
            if not src or not dst or src in existing:
                continue
            w.writerow([src, dst])
            existing[src] = dst
            added += 1
    load_aliases()  # re-validate: raises on chains/self introduced by the round
    print(f"Added {added} alias(es) to {ALIASES_PATH}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--apply", type=Path, help="reviewed worksheet to append")
    args = ap.parse_args()
    if args.apply:
        apply_worksheet(args.apply)
    else:
        generate(args.limit)


if __name__ == "__main__":
    main()
