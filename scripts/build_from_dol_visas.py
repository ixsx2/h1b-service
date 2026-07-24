#!/usr/bin/env python3
"""Build h1b_data.db from the public dol-visas DuckDB mirror (LCA only).

Use when DOL xlsx files cannot be downloaded automatically (Akamai 403).
USCIS denial columns stay at zero — re-run `scripts/build_data.py --source
manifest` after dropping real DOL + USCIS files into data/sources/ for full data.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.aliases import load_aliases
from etl.build import YearBucket, apply_aliases, write_database  # noqa: E402
from etl.canonicalize import canonicalize  # noqa: E402
from etl.sources import last_n_complete_fiscal_years  # noqa: E402

HF_DB = (
    "https://huggingface.co/datasets/Nason/dol-visas-database/resolve/main/dol_visas.duckdb"
)


def _annualize_wage(amount: float, unit: str) -> float | None:
    if amount <= 0:
        return None
    u = (unit or "").strip().lower()
    if u in ("year", "yr"):
        return amount
    if u == "hour":
        return amount * 2080
    if u == "month":
        return amount * 12
    if u == "week":
        return amount * 52
    if u in ("bi-weekly", "biweekly"):
        return amount * 26
    return None


def build_from_dol_visas(output: Path, aliases_path: Path | None = None) -> None:
    import duckdb

    fys = last_n_complete_fiscal_years(5)
    fy_min, fy_max = min(fys), max(fys)
    print(f"Querying dol-visas DuckDB for certified LCAs FY{fy_min}–FY{fy_max}…")

    con = duckdb.connect()
    con.execute("INSTALL httpfs")
    con.execute("LOAD httpfs")
    con.execute(f"ATTACH '{HF_DB}' AS v (READ_ONLY)")

    rows = con.execute(
        """
        SELECT
            employer_name,
            fiscal_year,
            job_title,
            wage_rate_of_pay_from,
            wage_unit_of_pay
        FROM v.lca
        WHERE is_latest
          AND fiscal_year BETWEEN ? AND ?
          AND case_status IN ('CERTIFIED', 'CERTIFIED-EXPIRED')
        """,
        [fy_min, fy_max],
    ).fetchall()
    print(f"Fetched {len(rows):,} certified LCA rows")

    buckets: dict[tuple[str, int], YearBucket] = defaultdict(YearBucket)
    filed_names: dict[str, set[str]] = defaultdict(set)

    for employer, fy, title, wage, unit in rows:
        filed = str(employer or "").strip()
        if not filed:
            continue
        canon = canonicalize(filed)
        if not canon:
            continue
        key = (canon, int(fy))
        bucket = buckets[key]
        bucket.certified += 1
        if title:
            bucket.titles[str(title).strip().upper()] += 1
        annual = _annualize_wage(float(wage or 0), str(unit or ""))
        if annual:
            bucket.salaries.append(annual)
        filed_names[filed.upper()].add(canon)

    aliases = load_aliases(aliases_path)
    dead = apply_aliases(buckets, filed_names, aliases)
    if dead:
        print(f"WARNING: {len(dead)} dead alias(es)")

    write_database(output, buckets, filed_names)
    employers = len({c for c, _ in buckets})
    print(f"Wrote {output} — {employers:,} employers, {len(buckets):,} employer-year rows (LCA only, no USCIS)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build h1b_data.db from dol-visas HuggingFace mirror")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "h1b_data.db")
    parser.add_argument("--aliases", type=Path, default=ROOT / "etl" / "aliases.csv")
    args = parser.parse_args()
    build_from_dol_visas(args.output, args.aliases)


if __name__ == "__main__":
    main()
