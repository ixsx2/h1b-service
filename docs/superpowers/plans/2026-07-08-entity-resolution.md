# Entity Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the DOL↔USCIS name-join gap (17–32% orphan approvals/FY) with two layers: deterministic `canonicalize()` rules and a human-curated alias map — no auto-merge, ship gated on a named-sponsor allowlist test.

**Architecture:** Layer 1 rewrites `canonicalize()` (punctuation→space, apostrophe-delete, single-letter-run collapse, `&`→` AND `, DBA truncate, trailing-only new suffixes, leading THE) so both sources converge deterministically. Layer 2 remaps post-canonical keys via committed `etl/aliases.csv`, applied by merging buckets after ingest. Guards: a collisions report (old-vs-new normalizer), a dead-alias warning, and `test_known_sponsors_join` as the ship gate.

**Tech Stack:** Python 3.12, SQLite, stdlib only (`re`, `csv`, `difflib` — no new deps), pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-07-08-entity-resolution-design.md` (read it first).

## Global Constraints

- Never auto-merge: every cross-entity merge is a deterministic rule or a human-reviewed `aliases.csv` row. False-merge is worse than an orphan.
- Explicitly NOT stripped (false-merge traps): trailing `USA`/`US`/`AMERICA`/`AMERICAS`, `HOLDINGS`, `GROUP`, geographic/word suffixes. `BANK OF AMERICA` must stay distinct from `BANK OF`.
- New suffixes `PC PLLC LLP LP PA` strip **trailing position only**.
- Apostrophe **deletes** (CHILDREN'S→CHILDRENS); dot becomes **space**; single-letter runs collapse (`U S A`→`USA`) so `VISA U.S.A.` = `VISA USA` keeps converging.
- `&` → ` AND ` (that direction), dangling trailing `AND` dropped.
- DBA truncate keeps the legal filer; if the clause starts the name, leave the name unchanged (never canonicalize to empty).
- `aliases.csv` holds **post-Layer-1 canonical keys** in both columns; single-hop only (a target must never itself be a source).
- Repo public: no personal data/tokens; ETL never touches user tables; aggregates DB rebuilds from scratch (ADR-0001), no migration.
- Tests never write `data/h1b_data.db` (temp paths only).
- Every task ends ruff-clean: `.venv/Scripts/python.exe -m ruff check .`
- All commands run from `Projects/h1b-service`; python is `.venv/Scripts/python.exe`.
- Working branch: `chore/etl-download-blocker-doc` (already checked out).
- Full rebuilds (~65–85 min) are run by Ishan, foreground, cmd.exe — never launch them yourself. Two rebuilds in this plan (after Layer 1, after aliases).
- Run `scripts/report_normalization_collisions.py` (Task 2) BEFORE rebuild #1 — it needs the current pre-Layer-1 `data/h1b_data.db` as the old-normalizer baseline.

---

### Task 1: Layer 1 — rewrite `canonicalize()` + rule/false-merge tests

**Files:**
- Modify: `etl/canonicalize.py`
- Test: `tests/test_canonicalize.py` (new; the two canonicalize asserts in `tests/test_etl.py::test_canonicalize_suffix_stripping` stay and must keep passing)

**Interfaces:**
- Consumes: nothing new.
- Produces: `canonicalize(name: str) -> str` (same signature; new behavior). `name_variants` unchanged. Both `app/lookup.py` and both ETL ingest paths already import `canonicalize` — they pick up the new behavior with no call-site change.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_canonicalize.py`:

```python
"""Layer-1 normalization rules — convergence and false-merge guards."""

from __future__ import annotations

import pytest

from etl.canonicalize import canonicalize

# Pairs that MUST converge (same employer, different source spelling)
CONVERGE = [
    pytest.param("AMAZON.COM SERVICES LLC", "AMAZON COM SERVICES LLC", id="dot-vs-space"),
    pytest.param("VISA U.S.A. INC", "VISA USA INC", id="dotted-acronym-vs-solid"),
    pytest.param("CITIBANK, N.A.", "CITIBANK N A", id="na-dotted-vs-spaced"),
    pytest.param(
        "ST. JUDE CHILDREN'S RESEARCH HOSPITAL",
        "ST JUDE CHILDRENS RESEARCH HOSPITAL",
        id="apostrophe",
    ),
    pytest.param("TEXAS A&M UNIVERSITY", "TEXAS A AND M UNIVERSITY", id="ampersand-vs-and"),
    pytest.param("JPMORGAN CHASE & CO.", "JPMORGAN CHASE AND", id="amp-co-vs-trailing-and"),
    pytest.param("A.T. KEARNEY, INC.", "A T KEARNEY", id="initials-collapse"),
    pytest.param("DELL PRODUCTS L.P.", "DELL PRODUCTS LP", id="lp-spaced-vs-solid"),
    pytest.param("MERCK SHARP & DOHME LLC", "MERCK SHARP AND DOHME", id="amp-mid-name"),
    pytest.param(
        "FIDELITY GROUP D/B/A FIDELITY INVESTMENTS",
        "FIDELITY GROUP D B A FIDELITY INVESTMENTS",
        id="dba-spellings",
    ),
    pytest.param("THE BOEING COMPANY", "BOEING COMPANY", id="leading-the"),
]


@pytest.mark.parametrize("a,b", CONVERGE)
def test_must_converge(a, b):
    assert canonicalize(a) == canonicalize(b), (
        f"{a!r} -> {canonicalize(a)!r} vs {b!r} -> {canonicalize(b)!r}"
    )


# Pairs that MUST stay distinct (different employers a blind rule would merge)
STAY_DISTINCT = [
    pytest.param("BANK OF AMERICA, N.A.", "BANK OF", id="no-geo-suffix-strip"),
    pytest.param("AMAZON.COM SERVICES LLC", "AMAZON WEB SERVICES INC", id="amazon-not-aws"),
    pytest.param("UNIVERSITY OF PENNSYLVANIA", "UNIVERSITY OF MONTANA", id="different-schools"),
    pytest.param("PC CONNECTION INC", "CONNECTION INC", id="pc-not-stripped-mid-name"),
    pytest.param("LP BUILDING SOLUTIONS LLC", "BUILDING SOLUTIONS LLC", id="lp-leading-kept"),
]


@pytest.mark.parametrize("a,b", STAY_DISTINCT)
def test_must_stay_distinct(a, b):
    assert canonicalize(a) != canonicalize(b), (
        f"FALSE MERGE: {a!r} and {b!r} both -> {canonicalize(a)!r}"
    )


# Exact expected outputs for individual rules
CASES = [
    pytest.param("FIDELITY GROUP D/B/A FIDELITY INVESTMENTS", "FIDELITY GROUP", id="dba-truncate"),
    pytest.param("DBA STAFFING LLC", "DBA STAFFING", id="dba-leading-kept"),
    pytest.param("SMITH MEDICAL P.C.", "SMITH MEDICAL", id="trailing-pc-stripped"),
    pytest.param("JONES & PARTNERS PLLC", "JONES AND PARTNERS", id="trailing-pllc"),
    pytest.param("JPMORGAN CHASE AND", "JPMORGAN CHASE", id="dangling-and-dropped"),
    pytest.param("Datadog, Inc.", "DATADOG", id="legacy-suffix-behavior"),
    pytest.param("N.V. Energy Corp.", "ENERGY", id="legacy-nv-behavior"),
    pytest.param("CAF� BISTRO INC", "CAF BISTRO", id="mojibake-to-space"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_exact_output(raw, expected):
    assert canonicalize(raw) == expected
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canonicalize.py -v`
Expected: multiple FAILs (dot-vs-space, apostrophe, ampersand, initials-collapse, dba-truncate, trailing-pc at minimum) against the current implementation.

- [ ] **Step 3: Rewrite `canonicalize()`**

Replace the body of `etl/canonicalize.py` (keep `name_variants` as-is):

```python
"""Canonical Employer normalization — copied from JobApps pipeline logic, expanded.

Layer 1 of entity resolution (see docs/superpowers/specs/
2026-07-08-entity-resolution-design.md): deterministic rules only. Anything
that could merge two genuinely distinct employers is NOT a rule here — it
goes through the human-reviewed etl/aliases.csv instead.
"""

from __future__ import annotations

import re

_SUFFIX_RE = re.compile(
    r"\b(incorporated|corporation|technologies|technology|inc|llc|corp|ltd|plc|gmbh|sa|nv|co|labs)\b\.?",
    re.IGNORECASE,
)
# Two-letter entity-form markers strip in TRAILING position only — mid-name
# they are usually meaningful (PC CONNECTION, LP BUILDING SOLUTIONS).
_TRAILING_SUFFIXES = frozenset({"PC", "PLLC", "LLP", "LP", "PA"})


def _collapse_single_letter_runs(tokens: list[str]) -> list[str]:
    """Merge runs of 2+ adjacent single-letter tokens: U S A -> USA, A T -> AT.

    Never crosses a multi-letter token, so AMAZON COM stays two tokens."""
    out: list[str] = []
    run: list[str] = []
    for tok in tokens:
        if len(tok) == 1 and tok.isalpha():
            run.append(tok)
            continue
        if run:
            out.append("".join(run))
            run = []
        out.append(tok)
    if run:
        out.append("".join(run))
    return out


def canonicalize(name: str) -> str:
    """Suffix-stripped, punctuation-normalized, uppercased legal name."""
    base = name.strip()
    if not base:
        return ""
    s = base.replace("'", "").replace("’", "")  # apostrophe: delete, not space
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)  # all punctuation + mojibake -> space
    s = s.upper()

    tokens = _collapse_single_letter_runs(s.split())

    # DBA clause: keep the legal filer before it; a leading DBA is kept whole.
    if "DBA" in tokens:
        idx = tokens.index("DBA")
        if idx > 0:
            tokens = tokens[:idx]

    s = _SUFFIX_RE.sub(" ", " ".join(tokens))
    tokens = s.split()

    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    while tokens and (tokens[-1] in _TRAILING_SUFFIXES or tokens[-1] == "AND"):
        tokens.pop()
    return " ".join(tokens)
```

- [ ] **Step 4: Run the new tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_canonicalize.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full suite (canonicalize feeds ingest, lookup, fixtures)**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check .`
Expected: all PASS (40+ passed, 2 env-gated skips). If a fixture test fails on a changed canonical key, fix the assertion only if the new key is correct per the rules above — do not weaken a rule to keep an old assertion.

- [ ] **Step 6: Commit**

```bash
git add etl/canonicalize.py tests/test_canonicalize.py
git commit -m "feat(etl): Layer-1 canonicalize rules (punct->space, collapse, AND, DBA, trailing suffixes)"
```

---

### Task 2: Collisions report (old vs new normalizer) — run BEFORE rebuild #1

Uses the current `data/h1b_data.db` (built with the OLD normalizer) as the baseline: its `filed_names` table pairs each raw filed name with its old canonical key. Recompute each filed name under the NEW `canonicalize()`; any new key receiving 2+ distinct old keys is a collision (a merge the rule change introduces). Most are the intended fixes; the report makes the unintended ones visible.

**Files:**
- Create: `scripts/report_normalization_collisions.py`
- No test — read-only diagnostic; correctness is eyeballed on real output.

**Interfaces:**
- Consumes: `canonicalize` (new), current `data/h1b_data.db` (`filed_names`, `aggregates`).
- Produces: `data/normalization_collisions.csv` with columns `new_canonical,old_canonicals,n_old_keys,total_new_approvals,total_certified`, sorted by `total_new_approvals` desc.

- [ ] **Step 1: Write the script**

```python
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
```

- [ ] **Step 2: Run it against the current (pre-Layer-1) build**

Run: `.venv/Scripts/python.exe scripts/report_normalization_collisions.py`
Expected: a few hundred–few thousand collisions; the top entries should be the *intended* fixes (Amazon dot/space, `&`/AND pairs, N A/NA acronyms, DBA truncations).

- [ ] **Step 3: Eyeball the top ~30 rows for false merges**

Look for two *different real companies* under one new key (the spec's trap classes). If found: the offending rule gets narrowed in Task 1 (add a STAY_DISTINCT test first, then fix), and this report re-runs. If clean: proceed.

- [ ] **Step 4: Ruff + commit**

```bash
.venv/Scripts/python.exe -m ruff check scripts/report_normalization_collisions.py
git add scripts/report_normalization_collisions.py
git commit -m "feat(etl): old-vs-new normalizer collisions report"
```

(`data/` is gitignored — the CSV output stays local, only the script commits.)

---

### Task 3: `aliases.csv` + loader + bucket-merge apply + dead-alias warning

**Files:**
- Create: `etl/aliases.csv` (header + provenance comment, no entries yet)
- Create: `etl/aliases.py`
- Modify: `etl/build.py` (apply step in `build_from_paths`, after all ingests, before `write_database`)
- Test: `tests/test_etl.py`

**Interfaces:**
- Consumes: `YearBucket` (fields: `certified`, `salaries`, `titles`, `new_approvals`, `new_denials`, `transfer_approvals`, `transfer_denials`).
- Produces: `load_aliases(path: Path | None = None) -> dict[str, str]` in `etl/aliases.py` (raises `ValueError` on chained/self aliases); `apply_aliases(buckets, filed_names, aliases) -> list[str]` in `etl/build.py` returning dead alias sources; `build_from_paths` gains keyword `aliases_path: Path | None = None` (None → default `etl/aliases.csv`).

- [ ] **Step 1: Create `etl/aliases.csv`**

```csv
# Curated entity aliases — Layer 2 of entity resolution.
# Both columns are POST-canonicalize() keys. Single-hop only: a target must
# never appear as a source. Every row is human-reviewed; provenance is the
# generate_alias_worksheet.py review round that produced it.
# See docs/superpowers/specs/2026-07-08-entity-resolution-design.md.
source_canonical,target_canonical
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_etl.py`:

```python
def test_alias_loader_rejects_chains(tmp_path):
    from etl.aliases import load_aliases

    p = tmp_path / "aliases.csv"
    p.write_text(
        "source_canonical,target_canonical\nA CO,B CO\nB CO,C CO\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_aliases(p)


def test_apply_aliases_merges_buckets_and_reports_dead(tmp_path):
    from etl.aliases import load_aliases
    from etl.build import apply_aliases

    p = tmp_path / "aliases.csv"
    p.write_text(
        "# comment\nsource_canonical,target_canonical\n"
        "ACME EAST,ACME\nNEVER OCCURS,ACME\n",
        encoding="utf-8",
    )
    aliases = load_aliases(p)

    src = YearBucket(certified=5, new_approvals=10, new_denials=1)
    src.transfer_approvals, src.transfer_denials = 4, 0
    dst = YearBucket(certified=20, new_approvals=7)
    buckets = {("ACME EAST", 2025): src, ("ACME", 2025): dst}
    filed = {"ACME EAST LLC": {"ACME EAST"}}

    dead = apply_aliases(buckets, filed, aliases)

    assert ("ACME EAST", 2025) not in buckets
    merged = buckets[("ACME", 2025)]
    assert merged.certified == 25
    assert merged.new_approvals == 17
    assert merged.new_denials == 1
    # dst had no breakout (None); src did -> merged carries src's numbers
    assert merged.transfer_approvals == 4
    assert filed["ACME EAST LLC"] == {"ACME"}
    assert dead == ["NEVER OCCURS"]
```

Note `import pytest` must exist at the top of `tests/test_etl.py` (it does).

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -v -k "alias"`
Expected: FAIL with `ModuleNotFoundError: No module named 'etl.aliases'`.

- [ ] **Step 4: Write `etl/aliases.py`**

```python
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
```

- [ ] **Step 5: Add `apply_aliases` to `etl/build.py` and wire it into `build_from_paths`**

Add after `ingest_uscis_xlsx` (import `load_aliases` from `etl.aliases` at the top of the file):

```python
def apply_aliases(
    buckets: dict[tuple[str, int], YearBucket],
    filed_names: dict[str, set[str]],
    aliases: dict[str, str],
) -> list[str]:
    """Remap bucket keys through the curated alias map; merge collided buckets.

    Returns alias sources that never occurred in the corpus (dead aliases)."""
    seen: set[str] = set()
    for canon, fy in list(buckets):
        target = aliases.get(canon)
        if target is None:
            continue
        seen.add(canon)
        src = buckets.pop((canon, fy))
        dst = buckets.setdefault((target, fy), YearBucket())
        dst.certified += src.certified
        dst.salaries.extend(src.salaries)
        dst.titles.update(src.titles)
        dst.new_approvals += src.new_approvals
        dst.new_denials += src.new_denials
        if src.transfer_approvals is not None:
            dst.transfer_approvals = (dst.transfer_approvals or 0) + src.transfer_approvals
            dst.transfer_denials = (dst.transfer_denials or 0) + (src.transfer_denials or 0)
    for filed, canon_set in filed_names.items():
        filed_names[filed] = {aliases.get(c, c) for c in canon_set}
    return sorted(s for s in aliases if s not in seen)
```

In `build_from_paths`, change the signature to
`def build_from_paths(dol_paths, uscis_paths, output, aliases_path=None):`
and insert between the USCIS ingest loop and `write_database(...)`:

```python
    aliases = load_aliases(aliases_path)
    dead = apply_aliases(buckets, filed_names, aliases)
    if dead:
        print(f"WARNING: {len(dead)} dead alias(es) — source never occurred: {dead}")
```

- [ ] **Step 6: Run tests + full suite + ruff**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check .`
Expected: all PASS (empty default aliases.csv = no behavior change for existing tests).

- [ ] **Step 7: Commit**

```bash
git add etl/aliases.csv etl/aliases.py etl/build.py tests/test_etl.py
git commit -m "feat(etl): curated alias map with bucket-merge apply and dead-alias warning"
```

---

### Task 4: Orphan-rate observability in `meta`

**Files:**
- Modify: `etl/build.py` (`write_database`, in the meta INSERT section)
- Test: `tests/test_etl.py`

**Interfaces:**
- Consumes: `buckets` at write time; `last_n_complete_fiscal_years(1)` (already imported).
- Produces: meta row `orphan_new_approval_rate` — fraction of latest-complete-FY `new_approvals` sitting on keys with `certified == 0`, rounded to 4 places; `'null'` string when the FY has zero new approvals. Observability only, never a gate.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_etl.py`:

```python
def test_orphan_rate_in_meta(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        "SELECT value FROM meta WHERE key='orphan_new_approval_rate'"
    ).fetchone()
    assert row is not None
    # Fixture: all USCIS rows join to LCA rows -> orphan rate 0.0
    assert row[0] == "0.0"
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py::test_orphan_rate_in_meta -v`
Expected: FAIL — `assert row is not None` (key missing).

- [ ] **Step 3: Implement in `write_database`**

Immediately before the existing meta INSERT, add:

```python
    latest_fy = last_n_complete_fiscal_years(1)[0]
    new_total = sum(b.new_approvals for (_, fy), b in buckets.items() if fy == latest_fy)
    new_orphan = sum(
        b.new_approvals
        for (_, fy), b in buckets.items()
        if fy == latest_fy and b.certified == 0
    )
    orphan_rate = str(round(new_orphan / new_total, 4)) if new_total else "null"
```

and extend the meta INSERT to three rows:

```python
    conn.execute(
        """
        INSERT INTO meta (key, value) VALUES ('latest_complete_fy', ?),
               ('built_fiscal_years', ?), ('orphan_new_approval_rate', ?)
        """,
        (
            str(latest_fy),
            json.dumps(sorted({fy for _, fy in buckets})),
            orphan_rate,
        ),
    )
```

(The existing `str(last_n_complete_fiscal_years(1)[0])` argument is replaced by the `latest_fy` variable.)

- [ ] **Step 4: Run tests + ruff, commit**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -q && .venv/Scripts/python.exe -m ruff check .`
Expected: all PASS.

```bash
git add etl/build.py tests/test_etl.py
git commit -m "feat(etl): log approval-weighted orphan rate to meta"
```

---

### Task 5: Rebuild #1 (Ishan runs) + re-measure

- [ ] **Step 1: Hand Ishan the build command**

cmd.exe, from `Projects\h1b-service` (~65–85 min):

```
.venv\Scripts\python.exe scripts\build_data.py --source manifest --output data\h1b_data.db > data\build.log 2>&1
```

Wait for his confirmation. Do not launch it yourself.

- [ ] **Step 2: Post-rebuild measurement**

```bash
.venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/h1b_data.db')
print('orphan rate:', conn.execute(\"SELECT value FROM meta WHERE key='orphan_new_approval_rate'\").fetchone()[0])
print('employers:', conn.execute('SELECT COUNT(*) FROM employers').fetchone()[0])
# Amazon must now be ONE key with both sides populated
for r in conn.execute(
    'SELECT canonical_employer, certified_count, uscis_new_approvals FROM aggregates'
    \" WHERE canonical_employer LIKE 'AMAZON COM%' AND fiscal_year=2025\"):
    print(r)
"
```

Expected: orphan rate well under the 0.211 baseline (Layer 1 classes were 58.6% of orphan approvals → expect roughly 0.08–0.10); employer count noticeably below 210,585 (cross-source keys merged); `AMAZON COM SERVICES` row shows certified ~15K AND new approvals ~3K on the same key.

- [ ] **Step 3: Record the numbers**

Note orphan rate, employer count, and the Amazon row for the Task 8 work log. If the orphan rate did NOT drop materially (still > 0.15), stop — a Layer-1 rule is not firing; debug against `tests/test_canonicalize.py` cases before continuing.

---

### Task 6: Alias worksheet generator + curation round

**Files:**
- Create: `scripts/generate_alias_worksheet.py`
- Modify: `etl/aliases.csv` (populated from the reviewed worksheet)
- No pytest — the suggester is tooling; its output is human-reviewed by design.

**Interfaces:**
- Consumes: post-rebuild-#1 `data/h1b_data.db`; `canonicalize` not needed (keys already canonical).
- Produces: `data/alias_worksheet.csv` (`orphan,suggestion,score,approvals,accept`); `--apply data/alias_worksheet.csv` appends rows with `accept` in {y, yes, x, 1} to `etl/aliases.csv`, skipping duplicates.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Layer-2 alias worksheet: suggest LCA-side matches for USCIS orphans.

Suggests, never merges. A human fills the `accept` column; `--apply` copies
accepted rows into etl/aliases.csv. Fuzzy scoring is stdlib difflib within
first-token blocks (bake-off-validated: high recall, but ~15-20% of
high-scoring suggestions are wrong-same — Amazon->AWS at 0.84 — hence the
mandatory human review)."""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
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
    lca_block: dict[str, list[str]] = defaultdict(list)
    for (name,) in conn.execute(
        "SELECT canonical_employer FROM aggregates WHERE fiscal_year=? AND certified_count>0",
        (latest,),
    ):
        lca_block[name.split(" ", 1)[0]].append(name)
    conn.close()

    existing = load_aliases()
    with WORKSHEET.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["orphan", "suggestion", "score", "approvals", "accept"])
        for canon, appr in orphans:
            if canon in existing:
                continue
            best, best_r = "", 0.0
            for cand in lca_block.get(canon.split(" ", 1)[0], []):
                r = SequenceMatcher(None, canon, cand).ratio()
                if r > best_r:
                    best, best_r = cand, r
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
```

- [ ] **Step 2: Ruff, generate, commit the tool**

```bash
.venv/Scripts/python.exe -m ruff check scripts/generate_alias_worksheet.py
.venv/Scripts/python.exe scripts/generate_alias_worksheet.py --limit 300
git add scripts/generate_alias_worksheet.py
git commit -m "feat(etl): fuzzy-block alias worksheet generator (suggest-only)"
```

- [ ] **Step 3: Human review round**

Present the worksheet's top rows to Ishan in-conversation (or he edits `data/alias_worksheet.csv` directly): mark `accept` = y only where the suggestion is the SAME employer. Explicitly reject wrong-same lookalikes (the Amazon→AWS class). Rows with no suggestion may get a hand-typed `suggestion` value (e.g. UMASS CHAN → the correct LCA key) before accepting.

- [ ] **Step 4: Apply accepted rows + commit aliases**

```bash
.venv/Scripts/python.exe scripts/generate_alias_worksheet.py --apply data/alias_worksheet.csv
.venv/Scripts/python.exe -m pytest tests/test_etl.py -q   # loader re-validates aliases.csv
git add etl/aliases.csv
git commit -m "data(etl): first curated alias round from reviewed worksheet"
```

---

### Task 7: Ship gate — `test_known_sponsors_join` + rebuild #2

**Files:**
- Create: `tests/test_known_sponsors.py`

**Interfaces:**
- Consumes: real `data/h1b_data.db` (post-rebuild-#2), `canonicalize`, `load_aliases`.
- Produces: the ship gate. Skipped automatically when the real DB is absent (CI).

- [ ] **Step 1: Write the gate test**

```python
"""Ship gate: marquee employers must join across DOL and USCIS.

Runs against the real data/h1b_data.db; skipped when absent (CI). Any
failure is a ship blocker per the entity-resolution spec — fix via a
Layer-1 rule (with tests) or a reviewed alias entry, never by weakening
the list without Ishan's sign-off."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from etl.aliases import load_aliases
from etl.canonicalize import canonicalize

REAL_DB = Path(__file__).resolve().parents[1] / "data" / "h1b_data.db"

pytestmark = pytest.mark.skipif(not REAL_DB.exists(), reason="real build not present")

SPONSORS = [
    # big tech
    "Amazon.com Services LLC", "Google LLC", "Microsoft Corporation",
    "Meta Platforms Inc", "Apple Inc", "NVIDIA Corporation", "Intel Corporation",
    "Oracle America Inc", "Salesforce Inc", "Adobe Inc",
    "International Business Machines Corporation", "Cisco Systems Inc",
    "Qualcomm Technologies Inc", "Uber Technologies Inc", "Intuit Inc",
    # consultancies / IT services
    "Deloitte Consulting LLP", "Ernst & Young U.S. LLP", "Accenture LLP",
    "Infosys Limited", "Tata Consultancy Services Limited", "Wipro Limited",
    "HCL America Inc", "Cognizant Technology Solutions US Corp",
    "Capgemini America Inc", "Tech Mahindra Americas Inc",
    "McKinsey & Company Inc United States",
    # banks / finance
    "JPMorgan Chase & Co", "Goldman Sachs & Co LLC", "Morgan Stanley & Co LLC",
    "Citibank N.A.", "Bank of America N.A.", "Wells Fargo Bank N.A.",
    "Capital One Services LLC",
    # universities / research / health (cap-exempt, high volume)
    "Stanford University", "Massachusetts Institute of Technology",
    "University of Michigan", "Johns Hopkins University", "Columbia University",
    "Mayo Clinic", "Cleveland Clinic",
]


def test_known_sponsors_join():
    aliases = load_aliases()
    conn = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    latest = int(
        conn.execute("SELECT value FROM meta WHERE key='latest_complete_fy'").fetchone()[0]
    )
    failures = []
    for name in SPONSORS:
        canon = canonicalize(name)
        canon = aliases.get(canon, canon)
        row = conn.execute(
            "SELECT certified_count, uscis_new_approvals FROM aggregates"
            " WHERE canonical_employer=? AND fiscal_year=?",
            (canon, latest),
        ).fetchone()
        if row is None or row[0] <= 0 or row[1] <= 0:
            failures.append((name, canon, row))
    conn.close()
    assert not failures, "\n".join(f"{n!r} -> {c!r}: {r}" for n, c, r in failures)
```

- [ ] **Step 2: Hand Ishan rebuild #2** (aliases now populated)

```
.venv\Scripts\python.exe scripts\build_data.py --source manifest --output data\h1b_data.db > data\build.log 2>&1
```

Wait for confirmation; watch the log for the dead-alias WARNING line (should be absent or explainable).

- [ ] **Step 3: Run the gate**

Run: `.venv/Scripts/python.exe -m pytest tests/test_known_sponsors.py -v`
Expected: PASS, or a failure list naming exactly which sponsors don't join and on which key.

- [ ] **Step 4: Iterate until green**

For each failure: diagnose which side is missing (query `aggregates` LIKE the name stem). Missing USCIS side → add a reviewed alias (repeat Task 6 Steps 3–4 for those names); missing LCA side at that key → check the canonical the DOL data actually landed on. Alias-only fixes do NOT need a rebuild — `apply_aliases` runs at build time, so alias changes need rebuild #2 re-run **only if aliases changed after it**; batch all alias fixes, then one final rebuild + gate run. Any sponsor removed from the list needs Ishan's explicit sign-off with a reason.

- [ ] **Step 5: Full suite + commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
git add tests/test_known_sponsors.py etl/aliases.csv
git commit -m "feat(tests): known-sponsors ship gate for entity resolution"
```

---

### Task 8: Docs — PLAN.md work log + CONTEXT.md term update

**Files:**
- Modify: `PLAN.md` (work log; update the "name-join orphan rate ~25%" known-limitation block)
- Modify: `CONTEXT.md` (Canonical Employer term)

- [ ] **Step 1: Update the PLAN.md known-limitation block**

Rewrite the "Known limitation — name-join orphan rate ~25%" bullet: entity resolution shipped (two layers, curated only); record the measured before/after orphan rates (0.211 → the Task 5/7 numbers), employer-count change, and that the residual orphans are documented long-tail (no similar LCA string; alias rounds continue as needed). Add a work-log entry with the collisions-report result and alias-round size.

- [ ] **Step 2: Update CONTEXT.md Canonical Employer**

Replace the term body with:

```
**Canonical Employer**:
The normalized identity of an employer: the output of the Layer-1
normalization rules (punctuation, &/AND, DBA, entity suffixes, single-letter
collapse) optionally remapped by the curated alias table (etl/aliases.csv).
All filings from both DOL and USCIS roll up to it. Original filed names map
to it via a lookup table.
_Avoid_: company, employer name (ambiguous — filed name or canonical?)
```

- [ ] **Step 3: Final suite + commit**

```bash
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
git add PLAN.md CONTEXT.md
git commit -m "docs: entity resolution shipped — work log, orphan-rate numbers, glossary"
```

---

## Execution order dependencies

Task 1 → Task 2 (collisions report needs the new canonicalize AND the old-build DB — run before rebuild #1). Tasks 3–4 are code-only, land before rebuild #1 so a single rebuild carries Layer 1 + alias plumbing + meta. Task 5 (rebuild #1, Ishan) gates Task 6 (worksheet needs post-Layer-1 orphans). Task 6 → Task 7 (rebuild #2 + gate). Task 8 last.
