#!/usr/bin/env python3
"""Build h1b_data.db from data/sources/ (real DOL + USCIS files)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.build import build_from_paths  # noqa: E402


def main() -> None:
    src = ROOT / "data" / "sources"
    dol = sorted(
        p for p in src.glob("LCA_Disclosure_Data_FY*.xlsx") if "Dislclosure" not in p.name
    )
    uscis = sorted(src.glob("Employer Information*.xlsx"))
    out = ROOT / "data" / "h1b_data.db"

    if not dol:
        raise SystemExit(f"No DOL xlsx files in {src}")
    if not uscis:
        raise SystemExit(f"No USCIS xlsx files in {src}")

    print(f"DOL files: {len(dol)}")
    print(f"USCIS files: {len(uscis)}")
    print(f"Output: {out}")
    sys.stdout.flush()

    build_from_paths(dol, uscis, out)
    print(f"Built {out}")


if __name__ == "__main__":
    main()
