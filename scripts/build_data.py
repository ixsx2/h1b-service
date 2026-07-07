#!/usr/bin/env python3
"""Build h1b_data.db for deploy — fixtures by default, manifest when requested."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.build import build_fixture_database, build_from_paths  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "h1b_data.db")
    parser.add_argument(
        "--source",
        choices=("fixtures", "manifest"),
        default="fixtures",
        help="fixtures=tests/fixtures; manifest=data/sources after etl.download",
    )
    args = parser.parse_args()

    if args.source == "fixtures":
        fixtures = ROOT / "tests" / "fixtures"
        gen = fixtures / "generate_fixtures.py"
        if gen.exists():
            import subprocess

            subprocess.run([sys.executable, str(gen)], check=True)
        build_fixture_database(fixtures, args.output)
    else:
        src = ROOT / "data" / "sources"
        dol = sorted(src.glob("LCA_Disclosure_Data_FY*.xlsx"))
        uscis = sorted(src.glob("*.csv"))
        if not dol:
            raise SystemExit(f"No DOL xlsx files in {src}. Run: python -m etl.download")
        build_from_paths(dol, uscis, args.output)

    print(f"Built {args.output}")


if __name__ == "__main__":
    main()
