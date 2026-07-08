# new_h1b vs transfers Signal Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the pooled USCIS "initial" denial signal into two independent blocks — `new_h1b` (New Employment + New Concurrent) and `transfers` (Change of Employer) — end to end: ETL schema, xlsx ingest, signal payload, landing card, tests, and a pre-build subset validation gate.

**Architecture:** The aggregates SQLite gets four USCIS columns replacing two (`uscis_new_*` NOT NULL, `uscis_transfer_*` nullable where NULL = breakout unavailable). `UscisColumns` carries four column tuples; empty transfer tuples mean the vintage has no breakout. USCIS ingest gains an xlsx path (the only real source files left are `Employer Information*.xlsx`). `build_signal` returns two `DenialBlock`s; the frozen-API payload nests them (clean break, no flat `denial_rate` alias — sign-off given).

**Tech Stack:** Python 3.12, FastAPI, SQLite (+FTS5), openpyxl read-only streaming, pytest, ruff.

**Spec:** `docs/superpowers/specs/2026-07-07-new-h1b-vs-transfers-design.md` (read it first).

## Global Constraints

- Repo is public: no personal data, tokens, or JobApps content in code/commits/fixtures.
- API surface frozen at six routes; this payload change has explicit sign-off (PLAN.md #10 amendment is part of this plan). No new routes.
- Grade, never score: tier/trend logic untouched.
- ETL never touches user tables; aggregates DB rebuilds from scratch (ADR-0001), no migration needed.
- Tests must NEVER write `data/h1b_data.db` — temp paths only (see skill-observations Observation 4).
- NULL means "this vintage can't say", never 0. `transfers: null` only when the breakout is unavailable.
- Denial thresholds per block, independently: rate null when approvals+denials < 10 (`DENIAL_MIN_PETITIONS`); caution at >= 0.15 (`DENIAL_CAUTION_RATE`).
- Every task ends ruff-clean: `.venv/Scripts/python.exe -m ruff check .`
- All commands run from `Projects/h1b-service`; python is `.venv/Scripts/python.exe`.
- Working branch: `chore/etl-download-blocker-doc` (already checked out).
- Do NOT run the full production build (~85 min); Ishan runs it himself (Task 8 hands him the command).
- USCIS number cells may be comma-formatted strings ("1,795"); ints in xlsx. `_sum_cells` already handles both via `str().replace(",", "")`.

---

### Task 1: Four-tuple `UscisColumns` (reverts the interim COE-merge)

The working tree has an uncommitted interim change that merged Change of Employer into a single `approval_columns` tuple. This task replaces it with the four-tuple design. Do not `git checkout` anything — overwrite the dataclass and maps in place.

**Files:**
- Modify: `etl/column_maps.py:17-85`
- Test: `tests/test_etl.py`

**Interfaces:**
- Produces: `UscisColumns(employer, fiscal_year, new_approval_columns, new_denial_columns, transfer_approval_columns, transfer_denial_columns)` — all four are `tuple[str, ...]`; empty transfer tuples = breakout unavailable. `USCIS_DATA_HUB`, `USCIS_STANDARD`, `USCIS_LOWER`, `resolve_uscis_columns(header) -> UscisColumns` (resolution order unchanged).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_etl.py`:

```python
def test_uscis_column_maps_split_new_vs_transfer():
    from etl.column_maps import USCIS_DATA_HUB, USCIS_STANDARD

    # new_h1b = fresh/cap only; Change of Employer must NOT be in the new tuples
    assert USCIS_DATA_HUB.new_approval_columns == (
        "New Employment Approval",
        "New Concurrent Approval",
    )
    assert USCIS_DATA_HUB.transfer_approval_columns == ("Change of Employer Approval",)
    assert USCIS_DATA_HUB.transfer_denial_columns == ("Change of Employer Denial",)
    # Legacy pre-summed export has no breakout
    assert USCIS_STANDARD.new_approval_columns == ("Initial Approval",)
    assert USCIS_STANDARD.transfer_approval_columns == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py::test_uscis_column_maps_split_new_vs_transfer -v`
Expected: FAIL with `AttributeError: ... no attribute 'new_approval_columns'`

- [ ] **Step 3: Rewrite `UscisColumns` and the three maps**

In `etl/column_maps.py`, replace the `UscisColumns` dataclass and the three USCIS map constants with:

```python
@dataclass(frozen=True)
class UscisColumns:
    employer: str
    fiscal_year: str
    # new_h1b = fresh/cap sponsorship: New Employment + New Concurrent.
    # Empirically identical to the legacy export's single "Initial" column
    # (FY2020: 122,894 = 121,874 + 1,020, exact).
    # transfers = Change of Employer: worker already on H-1B moving in.
    # Empty transfer tuples = this vintage has no breakout -> transfers NULL.
    new_approval_columns: tuple[str, ...]
    new_denial_columns: tuple[str, ...]
    transfer_approval_columns: tuple[str, ...]
    transfer_denial_columns: tuple[str, ...]
```

```python
# Real USCIS H-1B Employer Data Hub export with split petition-type columns.
# Excluded from both categories as same-employer renewals/tweaks:
# Continuation, Change with Same Employer, Amended. (Per the USCIS Data Hub
# glossary Part 2 Q2 petition-type definitions.)
USCIS_DATA_HUB = UscisColumns(
    employer="Employer (Petitioner) Name",
    fiscal_year="Fiscal Year",
    new_approval_columns=(
        "New Employment Approval",
        "New Concurrent Approval",
    ),
    new_denial_columns=(
        "New Employment Denial",
        "New Concurrent Denial",
    ),
    transfer_approval_columns=("Change of Employer Approval",),
    transfer_denial_columns=("Change of Employer Denial",),
)

# Old Data Hub export / synthetic fixture: single pre-summed Initial column
# (= New Employment + New Concurrent). No transfer breakout available.
USCIS_STANDARD = UscisColumns(
    employer="Employer",
    fiscal_year="Fiscal Year",
    new_approval_columns=("Initial Approval",),
    new_denial_columns=("Initial Denial",),
    transfer_approval_columns=(),
    transfer_denial_columns=(),
)

USCIS_LOWER = UscisColumns(
    employer="employer",
    fiscal_year="fiscal_year",
    new_approval_columns=("initial_approval",),
    new_denial_columns=("initial_denial",),
    transfer_approval_columns=(),
    transfer_denial_columns=(),
)
```

`resolve_uscis_columns` is unchanged.

- [ ] **Step 4: Run the new test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py::test_uscis_column_maps_split_new_vs_transfer -v`
Expected: PASS. Other ETL tests will now FAIL (`ingest_uscis_csv` still reads `cols.approval_columns`) — that is Task 2's job; do not fix here.

- [ ] **Step 5: Commit**

```bash
git add etl/column_maps.py tests/test_etl.py
git commit -m "feat(etl): split UscisColumns into new_h1b vs transfer tuples"
```

---

### Task 2: `YearBucket` split + CSV ingest accumulation

**Files:**
- Modify: `etl/build.py:24-30` (YearBucket), `etl/build.py:128-176` (`_uscis_indices`, `ingest_uscis_csv`)
- Test: `tests/test_etl.py`

**Interfaces:**
- Consumes: Task 1's four-tuple `UscisColumns`.
- Produces: `YearBucket` with `new_approvals: int = 0`, `new_denials: int = 0`, `transfer_approvals: int | None = None`, `transfer_denials: int | None = None` (old `initial_*` fields gone). `_uscis_indices(header, cols) -> (idx_emp, idx_fy, idx_new_app, idx_new_den, idx_tr_app, idx_tr_den)` where the last four are `list[int]`. `ingest_uscis_csv(path, buckets, filed_names=None)` — also records filed names when a dict is passed (used by Task 4 to kill the second read pass).

- [ ] **Step 1: Update the Data Hub schema test to assert the split**

In `tests/test_etl.py`, replace the body of `test_uscis_data_hub_real_schema` from the `buckets` line down (keep `_DATA_HUB_HEADER`, `_data_hub_row`, and the file-writing lines as they are):

```python
    buckets: dict = defaultdict(YearBucket)
    ingest_uscis_csv(csv_path, buckets)

    bucket = buckets[("ACME", 2026)]
    # new_h1b = 10 New Employment + 3 New Concurrent; NOT continuation (7), NOT COE
    assert bucket.new_approvals == 13
    assert bucket.new_denials == 2
    # transfers = Change of Employer only
    assert bucket.transfer_approvals == 5
    assert bucket.transfer_denials == 0
```

Also update the test's leading comment to say new sponsorship excludes Change of Employer. Then append a legacy-path test:

```python
def test_uscis_legacy_schema_has_no_transfer_breakout(tmp_path):
    lines = [
        "Employer,Fiscal Year,Initial Approval,Initial Denial",
        "ACME CORP,2025,40,4",
    ]
    csv_path = tmp_path / "uscis_legacy.csv"
    csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    buckets: dict = defaultdict(YearBucket)
    ingest_uscis_csv(csv_path, buckets)

    bucket = buckets[("ACME", 2025)]
    assert bucket.new_approvals == 40
    assert bucket.new_denials == 4
    # NULL, not 0: this vintage cannot say
    assert bucket.transfer_approvals is None
    assert bucket.transfer_denials is None
```

- [ ] **Step 2: Run to verify both fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -v -k "data_hub or legacy_schema"`
Expected: FAIL (`AttributeError` on `cols.approval_columns` inside ingest, or missing `new_approvals`).

- [ ] **Step 3: Implement in `etl/build.py`**

Replace `YearBucket`:

```python
@dataclass
class YearBucket:
    certified: int = 0
    salaries: list[float] = field(default_factory=list)
    titles: Counter[str] = field(default_factory=Counter)
    new_approvals: int = 0
    new_denials: int = 0
    # None = source vintage has no Change of Employer breakout (NULL in DB)
    transfer_approvals: int | None = None
    transfer_denials: int | None = None
```

Replace `_uscis_indices` and add `_accumulate_uscis`; rewrite `ingest_uscis_csv`:

```python
def _uscis_indices(header: tuple[str, ...], cols):
    """Column indices, tolerant of trailing/leading whitespace in headers
    (the real export has 'Fiscal Year   ')."""
    stripped = [h.strip() for h in header]

    def idx(name: str) -> int:
        return stripped.index(name)

    return (
        idx(cols.employer),
        idx(cols.fiscal_year),
        [idx(c) for c in cols.new_approval_columns],
        [idx(c) for c in cols.new_denial_columns],
        [idx(c) for c in cols.transfer_approval_columns],
        [idx(c) for c in cols.transfer_denial_columns],
    )


def _accumulate_uscis(
    bucket: YearBucket,
    row: list,
    idx_new_app: list[int],
    idx_new_den: list[int],
    idx_tr_app: list[int],
    idx_tr_den: list[int],
) -> None:
    bucket.new_approvals += _sum_cells(row, idx_new_app)
    bucket.new_denials += _sum_cells(row, idx_new_den)
    if idx_tr_app:  # breakout available in this vintage
        bucket.transfer_approvals = (bucket.transfer_approvals or 0) + _sum_cells(row, idx_tr_app)
        bucket.transfer_denials = (bucket.transfer_denials or 0) + _sum_cells(row, idx_tr_den)


def ingest_uscis_csv(
    path: Path,
    buckets: dict[tuple[str, int], YearBucket],
    filed_names: dict[str, set[str]] | None = None,
) -> None:
    fh, delim = _open_uscis(path)
    with fh:
        reader = csv.reader(fh, delimiter=delim)
        header = tuple(next(reader, []))
        cols = resolve_uscis_columns(header)
        idx_emp, idx_fy, idx_new_app, idx_new_den, idx_tr_app, idx_tr_den = _uscis_indices(
            header, cols
        )
        max_idx = max([idx_emp, idx_fy, *idx_new_app, *idx_new_den, *idx_tr_app, *idx_tr_den])

        for row in reader:
            if len(row) <= max_idx:
                continue
            filed = row[idx_emp].strip()
            if not filed:
                continue
            try:
                fy = int(str(row[idx_fy]).strip())
            except ValueError:
                continue
            canonical = canonicalize(filed)
            bucket = buckets.setdefault((canonical, fy), YearBucket())
            try:
                _accumulate_uscis(bucket, row, idx_new_app, idx_new_den, idx_tr_app, idx_tr_den)
            except ValueError:
                continue
            if filed_names is not None:
                filed_names[filed.upper()].add(canonical)
```

Note `_sum_cells` is unchanged. Do not touch `write_database` yet (it still references `bucket.initial_approvals` — Task 3).

- [ ] **Step 4: Run the two tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -v -k "data_hub or legacy_schema or column_maps or canonicalize"`
Expected: PASS (4 tests). The `built`-fixture ETL tests and the API suite still fail until Task 3 — expected.

- [ ] **Step 5: Commit**

```bash
git add etl/build.py tests/test_etl.py
git commit -m "feat(etl): accumulate new_h1b and transfer buckets separately in USCIS ingest"
```

---

### Task 3: Four-column aggregates schema + `db.py` reader

**Files:**
- Modify: `etl/build.py:210-267` (`write_database` schema + insert)
- Modify: `app/db.py:43-70` (`employer_aggregates`)
- Test: `tests/test_etl.py`

**Interfaces:**
- Consumes: Task 2's `YearBucket` fields.
- Produces: `aggregates` columns `uscis_new_approvals INTEGER NOT NULL DEFAULT 0`, `uscis_new_denials INTEGER NOT NULL DEFAULT 0`, `uscis_transfer_approvals INTEGER` (nullable), `uscis_transfer_denials INTEGER` (nullable). `AggregatesDB.employer_aggregates` dicts carry those four keys (transfer values may be `None`).

- [ ] **Step 1: Update the DB-shape test**

In `tests/test_etl.py`, replace `test_uscis_denial_joined` with:

```python
def test_uscis_split_columns_joined(built):
    conn = sqlite3.connect(built)
    row = conn.execute(
        """
        SELECT uscis_new_approvals, uscis_new_denials,
               uscis_transfer_approvals, uscis_transfer_denials
        FROM aggregates WHERE canonical_employer='DATADOG' AND fiscal_year=2025
        """
    ).fetchone()
    # Fixture CSV is legacy pre-summed: new gets the Initial numbers,
    # transfers stay NULL (breakout unavailable), never 0.
    assert row[0] == 50
    assert row[1] == 5
    assert row[2] is None
    assert row[3] is None
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py::test_uscis_split_columns_joined -v`
Expected: FAIL — either `AttributeError: 'YearBucket' object has no attribute 'initial_approvals'` during build, or `no such column: uscis_new_approvals`.

- [ ] **Step 3: Update `write_database`**

In the `CREATE TABLE aggregates` block, replace the two `uscis_initial_*` lines with:

```sql
uscis_new_approvals INTEGER NOT NULL DEFAULT 0,
uscis_new_denials INTEGER NOT NULL DEFAULT 0,
uscis_transfer_approvals INTEGER,
uscis_transfer_denials INTEGER,
```

Replace the aggregates INSERT with:

```python
        conn.execute(
            """
            INSERT INTO aggregates (
                canonical_employer, fiscal_year, certified_count,
                salary_median, salary_min, salary_max, top_titles,
                uscis_new_approvals, uscis_new_denials,
                uscis_transfer_approvals, uscis_transfer_denials
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canon,
                fy,
                bucket.certified,
                med,
                smin,
                smax,
                json.dumps(_top_titles(bucket.titles)),
                bucket.new_approvals,
                bucket.new_denials,
                bucket.transfer_approvals,
                bucket.transfer_denials,
            ),
        )
```

- [ ] **Step 4: Update `app/db.py` `employer_aggregates`**

Replace the SELECT column list and the dict fields:

```python
                SELECT fiscal_year, certified_count, salary_median, salary_min,
                       salary_max, top_titles, uscis_new_approvals,
                       uscis_new_denials, uscis_transfer_approvals,
                       uscis_transfer_denials
```

```python
                    "uscis_new_approvals": r["uscis_new_approvals"],
                    "uscis_new_denials": r["uscis_new_denials"],
                    "uscis_transfer_approvals": r["uscis_transfer_approvals"],
                    "uscis_transfer_denials": r["uscis_transfer_denials"],
```

- [ ] **Step 5: Run ETL tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -v`
Expected: all PASS. (`tests/test_signal.py` and API tests fail until Tasks 5–6 — expected.)

- [ ] **Step 6: Commit**

```bash
git add etl/build.py app/db.py tests/test_etl.py
git commit -m "feat(etl): four-column USCIS schema (new vs transfer, NULL = no breakout)"
```

---

### Task 4: USCIS xlsx ingest + manifest glob (single-pass filed names)

Critical: zero USCIS CSVs remain in `data/sources/` — real sources are the five `Employer Information*.xlsx`. Also fold filed-name capture into ingest and delete the CSV re-read pass in `build_from_paths`.

**Files:**
- Modify: `etl/build.py` (add `ingest_uscis_xlsx`; rewrite the USCIS loop in `build_from_paths:342-355`)
- Modify: `scripts/build_data.py:38`
- Test: `tests/test_etl.py`

**Interfaces:**
- Consumes: Task 2's `_uscis_indices`, `_accumulate_uscis`, `ingest_uscis_csv(path, buckets, filed_names)`.
- Produces: `ingest_uscis_xlsx(path, buckets, filed_names=None)` — same contract as the CSV ingest. `build_from_paths` dispatches USCIS paths by suffix (`.xlsx` vs anything else → CSV).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_etl.py` (add `from etl.build import ingest_uscis_xlsx` to the existing `etl.build` import line):

```python
def test_uscis_xlsx_ingest_multirow_summation(tmp_path):
    # Real consolidated files: one employer = many rows (per NAICS/city/ZIP),
    # numbers may be ints or comma-formatted strings.
    from openpyxl import Workbook

    wb = Workbook(write_only=True)
    ws = wb.create_sheet()
    ws.append([h.strip() if h != "Fiscal Year   " else h for h in _DATA_HUB_HEADER.split("\t")])
    base = ["1", 2025, "ACME CORP", "1234", "54 - Prof", "CITY", "CA", "90001"]
    #                 NewEmpA NewEmpD ContA ContD SameA SameD ConcA ConcD COEA COED AmA AmD
    ws.append(base + [10,     1,      7,    0,    0,    0,    2,    0,    4,   1,   0,  0])
    ws.append(base + ["1,000", 0,     0,    0,    0,    0,    0,    0,    6,   0,   0,  0])
    ws.append(["2", 2025, "", "9999", "54", "X", "CA", "0", 5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])  # blank name skipped
    path = tmp_path / "Employer Information_test.xlsx"
    wb.save(path)

    buckets: dict = defaultdict(YearBucket)
    filed: dict = defaultdict(set)
    ingest_uscis_xlsx(path, buckets, filed)

    bucket = buckets[("ACME", 2025)]
    assert bucket.new_approvals == 1012  # 10 + 2 + 1,000
    assert bucket.new_denials == 1
    assert bucket.transfer_approvals == 10  # 4 + 6
    assert bucket.transfer_denials == 1
    assert "ACME CORP" in filed
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py::test_uscis_xlsx_ingest_multirow_summation -v`
Expected: FAIL with `ImportError: cannot import name 'ingest_uscis_xlsx'`

- [ ] **Step 3: Implement `ingest_uscis_xlsx`**

Add to `etl/build.py` after `ingest_uscis_csv`:

```python
def ingest_uscis_xlsx(
    path: Path,
    buckets: dict[tuple[str, int], YearBucket],
    filed_names: dict[str, set[str]] | None = None,
) -> None:
    """Stream a consolidated USCIS Employer Data Hub xlsx (split petition-type
    schema). Same contract as ingest_uscis_csv."""
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = ws.iter_rows(values_only=True)
        header_row = next(rows, None)
        if not header_row:
            return
        header = tuple(str(c) if c is not None else "" for c in header_row)
        cols = resolve_uscis_columns(header)
        idx_emp, idx_fy, idx_new_app, idx_new_den, idx_tr_app, idx_tr_den = _uscis_indices(
            header, cols
        )
        max_idx = max([idx_emp, idx_fy, *idx_new_app, *idx_new_den, *idx_tr_app, *idx_tr_den])

        for raw in rows:
            if not raw or len(raw) <= max_idx:
                continue
            row = ["" if c is None else str(c) for c in raw]
            filed = row[idx_emp].strip()
            if not filed:
                continue
            try:
                fy = int(float(str(row[idx_fy]).strip()))
            except ValueError:
                continue
            canonical = canonicalize(filed)
            bucket = buckets.setdefault((canonical, fy), YearBucket())
            try:
                _accumulate_uscis(bucket, row, idx_new_app, idx_new_den, idx_tr_app, idx_tr_den)
            except ValueError:
                continue
            if filed_names is not None:
                filed_names[filed.upper()].add(canonical)
    finally:
        wb.close()
```

(`int(float(...))` because openpyxl may deliver the FY cell as `2025.0`; `_sum_cells` already strips commas from stringified number cells.)

- [ ] **Step 4: Rewrite the USCIS loop in `build_from_paths`**

Replace the entire `for uscis_path in uscis_paths:` block (ingest call plus the second filed-name read pass) with:

```python
    for uscis_path in uscis_paths:
        if uscis_path.suffix.lower() == ".xlsx":
            ingest_uscis_xlsx(uscis_path, buckets, filed_names)
        else:
            ingest_uscis_csv(uscis_path, buckets, filed_names)
```

- [ ] **Step 5: Update the manifest glob in `scripts/build_data.py`**

Replace `uscis = sorted(src.glob("*.csv"))` with:

```python
        uscis = sorted(src.glob("Employer Information*.xlsx")) + sorted(src.glob("*.csv"))
```

- [ ] **Step 6: Run full ETL tests + ruff**

Run: `.venv/Scripts/python.exe -m pytest tests/test_etl.py -v && .venv/Scripts/python.exe -m ruff check .`
Expected: all ETL tests PASS, ruff clean.

- [ ] **Step 7: Commit**

```bash
git add etl/build.py scripts/build_data.py tests/test_etl.py
git commit -m "feat(etl): ingest consolidated USCIS xlsx; single-pass filed-name capture"
```

---

### Task 5: Signal — `DenialBlock` pair replaces flat denial fields

**Files:**
- Modify: `app/signal.py:26-103`
- Test: `tests/test_signal.py`

**Interfaces:**
- Consumes: aggregate dicts with `uscis_new_approvals`, `uscis_new_denials`, `uscis_transfer_approvals` (may be None), `uscis_transfer_denials` (may be None).
- Produces: `DenialBlock(approvals: int, denials: int, denial_rate: float | None, caution: bool)` frozen dataclass. `SignalResult` fields `new_h1b: DenialBlock` and `transfers: DenialBlock | None` replace `denial_rate`/`denial_caution`. `compute_denial_rate` unchanged. `build_signal(rows, latest_complete_fy=None)` signature unchanged.

- [ ] **Step 1: Rewrite the integration test + add block cases**

In `tests/test_signal.py`, replace `test_build_signal_integration` with:

```python
def _row(fy, certified, new_app=0, new_den=0, tr_app=None, tr_den=None):
    return {
        "fiscal_year": fy,
        "certified_count": certified,
        "uscis_new_approvals": new_app,
        "uscis_new_denials": new_den,
        "uscis_transfer_approvals": tr_app,
        "uscis_transfer_denials": tr_den,
    }


def test_build_signal_split_blocks():
    rows = [
        _row(2025, 25, new_app=50, new_den=5, tr_app=30, tr_den=10),
        _row(2024, 15),
    ]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.tier == "ACTIVE"
    assert signal.trend == "rising"
    assert signal.new_h1b.approvals == 50
    assert signal.new_h1b.denial_rate == pytest.approx(0.0909, rel=1e-3)
    assert signal.new_h1b.caution is False
    assert signal.transfers is not None
    assert signal.transfers.denial_rate == pytest.approx(0.25, rel=1e-3)
    assert signal.transfers.caution is True


def test_build_signal_thresholds_independent_per_block():
    # 8 fresh decisions (below DENIAL_MIN_PETITIONS) but 40 transfer decisions
    rows = [_row(2025, 25, new_app=6, new_den=2, tr_app=38, tr_den=2)]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.denial_rate is None
    assert signal.new_h1b.caution is False
    assert signal.transfers.denial_rate == pytest.approx(0.05, rel=1e-3)


def test_build_signal_transfers_null_when_no_breakout():
    rows = [_row(2025, 25, new_app=50, new_den=5)]  # tr_* stay None
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.approvals == 50
    assert signal.transfers is None


def test_build_signal_no_uscis_row_for_latest_fy():
    # Employer has LCA history but no aggregates row in latest_complete_fy:
    # zero-count blocks, not a null transfers block.
    rows = [_row(2024, 30, new_app=10, new_den=0, tr_app=5, tr_den=0)]
    signal = build_signal(rows, latest_complete_fy=2025)
    assert signal.new_h1b.approvals == 0
    assert signal.new_h1b.denial_rate is None
    assert signal.transfers is not None
    assert signal.transfers.approvals == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_signal.py -v`
Expected: 4 new tests FAIL (`AttributeError: ... 'new_h1b'` / KeyError); parametrized tier/trend/denial-rate tests still PASS.

- [ ] **Step 3: Implement in `app/signal.py`**

Add `DenialBlock`, update `SignalResult`, rewrite the denial section of `build_signal`:

```python
@dataclass(frozen=True)
class DenialBlock:
    approvals: int
    denials: int
    denial_rate: float | None
    caution: bool


@dataclass(frozen=True)
class SignalResult:
    tier: SignalTier
    trend: Trend
    new_h1b: DenialBlock
    transfers: DenialBlock | None  # None = source vintage lacks the breakout
    certified_by_year: list[FiscalYearCount]
    latest_complete_fy: int


def _denial_block(approvals: int, denials: int) -> DenialBlock:
    rate, caution = compute_denial_rate(approvals, denials)
    return DenialBlock(approvals=approvals, denials=denials, denial_rate=rate, caution=caution)
```

In `build_signal`, replace the `approvals`/`denials`/`denial_rate` lines with:

```python
    latest_row = next((r for r in rows if int(r["fiscal_year"]) == lcfy), None)
    new_h1b = _denial_block(
        int(latest_row["uscis_new_approvals"]) if latest_row else 0,
        int(latest_row["uscis_new_denials"]) if latest_row else 0,
    )
    if latest_row is not None:
        tr_app = latest_row["uscis_transfer_approvals"]
        tr_den = latest_row["uscis_transfer_denials"]
    else:
        tr_app, tr_den = 0, 0  # no row = zero activity, breakout still exists
    if tr_app is None and tr_den is None:
        transfers = None  # this vintage cannot say — never report 0
    else:
        transfers = _denial_block(int(tr_app or 0), int(tr_den or 0))
```

And in the `SignalResult(...)` constructor replace `denial_rate=.../denial_caution=...` with `new_h1b=new_h1b, transfers=transfers`.

- [ ] **Step 4: Run signal tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_signal.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/signal.py tests/test_signal.py
git commit -m "feat(signal): new_h1b and transfers DenialBlocks replace flat denial rate"
```

---

### Task 6: API payload + landing card (frozen-API amendment, sign-off given)

Clean break: flat `denial_rate`/`denial_caution` leave the payload, no alias.

**Files:**
- Modify: `app/main.py:67-88` (`_signal_payload`)
- Modify: `app/landing.html:83-90` (`renderCard`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: Task 5's `SignalResult.new_h1b` / `.transfers`.
- Produces: `signal` JSON with `new_h1b: {approvals, denials, denial_rate, caution}` and `transfers: {same} | null`. `/v1/employer/{name}` rows already carry the four columns via Task 3's `employer_aggregates` — no route change.

- [ ] **Step 1: Write the failing API test**

Append to `tests/test_api.py`:

```python
def test_demo_signal_has_split_denial_blocks(client):
    r = client.get("/v1/demo")
    assert r.status_code == 200
    s = r.json()["signal"]
    assert "denial_rate" not in s  # clean break, no flat alias
    assert s["new_h1b"] == {
        "approvals": 50,
        "denials": 5,
        "denial_rate": pytest.approx(0.0909, rel=1e-3),
        "caution": False,
    }
    assert s["transfers"] is None  # legacy fixture CSV has no breakout


def test_employer_detail_exposes_split_uscis_columns(client, api_key):
    r = client.get(
        "/v1/employer/Datadog",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 200
    row_2025 = next(a for a in r.json()["aggregates"] if a["fiscal_year"] == 2025)
    assert row_2025["uscis_new_approvals"] == 50
    assert row_2025["uscis_transfer_approvals"] is None
    assert "uscis_initial_approvals" not in row_2025
```

(Ensure `import pytest` is present at the top of `tests/test_api.py`; add it if missing.)

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py -v -k "split"`
Expected: FAIL — `_signal_payload` still reads `signal.denial_rate` (AttributeError) or the shape assertions fail.

- [ ] **Step 3: Update `_signal_payload` in `app/main.py`**

```python
def _block_payload(block) -> dict | None:
    if block is None:
        return None
    return {
        "approvals": block.approvals,
        "denials": block.denials,
        "denial_rate": block.denial_rate,
        "caution": block.caution,
    }


def _signal_payload(canonical: str, matched_as: str | None = None) -> dict:
    rows = aggregates_db.employer_aggregates(canonical)
    signal = build_signal(rows, aggregates_db.latest_complete_fy())
    payload = {
        "canonical_employer": canonical,
        "matched": True,
        "signal": {
            "tier": signal.tier,
            "trend": signal.trend,
            "new_h1b": _block_payload(signal.new_h1b),
            "transfers": _block_payload(signal.transfers),
            "certified_by_year": [
                {"fiscal_year": c.fiscal_year, "certified": c.certified}
                for c in signal.certified_by_year
            ],
            "latest_complete_fy": signal.latest_complete_fy,
        },
    }
    if matched_as:
        payload["matched_as"] = matched_as
    return payload
```

- [ ] **Step 4: Update `renderCard` in `app/landing.html`**

Replace the `renderCard` function with:

```javascript
    function renderCard(data) {
      if (data.error) return `<p class="err">${data.error}: ${data.hint || ''}</p>`;
      const s = data.signal || data;
      const block = b => b
        ? `${b.denial_rate ?? 'n/a'}${b.caution ? ' ⚠' : ''} (${b.approvals} approved / ${b.denials} denied)`
        : 'n/a';
      return `<p><strong>Tier:</strong> ${s.tier}</p>
        <p><strong>Trend:</strong> ${s.trend ?? 'n/a'}</p>
        <p><strong>New H-1B (fresh/cap) denial rate:</strong> ${block(s.new_h1b)}</p>
        <p><strong>Transfers (already on H-1B) denial rate:</strong> ${block(s.transfers)}</p>
        <p><strong>Employer:</strong> ${data.canonical_employer || data.matched_as || '—'}</p>`;
    }
```

- [ ] **Step 5: Run the FULL suite + ruff**

Run: `.venv/Scripts/python.exe -m pytest -v && .venv/Scripts/python.exe -m ruff check .`
Expected: all PASS (2 skips: `test_real_etl`, `test_testmail_e2e` are environment-gated), ruff clean. This is the first all-green point since Task 1.

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/landing.html tests/test_api.py
git commit -m "feat(api): nested new_h1b/transfers signal payload + two-row landing card"
```

---

### Task 7: Subset validation gate (pre-build, Ishan's addition)

Independent recomputation over real files BEFORE the ~85-min build. USCIS xlsx parse in seconds; only one DOL quarter is read.

**Files:**
- Create: `scripts/validate_uscis_subset.py`
- No test file — this script IS the test; it exits nonzero on any failure.

**Interfaces:**
- Consumes: `ingest_uscis_xlsx`, `ingest_dol_xlsx`, `YearBucket` from `etl.build`; `canonicalize` from `etl.canonicalize`.
- Produces: console PASS/FAIL report; exit code 0 = gate open, 1 = stop.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""Pre-build validation gate: verify USCIS xlsx ingest against an independent
recomputation on real files, plus the FY2020 cross-vintage identity and a
one-quarter DOL join check. Exit 0 = safe to run the full build."""

from __future__ import annotations

import random
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from etl.build import YearBucket, ingest_dol_xlsx, ingest_uscis_xlsx  # noqa: E402
from etl.canonicalize import canonicalize  # noqa: E402

SRC = ROOT / "data" / "sources"
ANCHORS = ["GOOGLE", "AMAZONCOM SERVICES", "INFOSYS", "DELOITTE CONSULTING", "MICROSOFT"]
# Legacy FY2020 export's Initial Approval total = 121,874 NewEmp + 1,020 NewConc
FY2020_NEW_APPROVALS_TOTAL = 122_894
RANDOM_SAMPLE = 10
DOL_JOIN_FILE = "LCA_Disclosure_Data_FY2025_Q4.xlsx"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def independent_sums(path: Path) -> dict[tuple[str, int], tuple[int, int, int, int]]:
    """Second code path: raw openpyxl scan, positional column lookup by header
    name, no shared ingest helpers. Returns (new_app, new_den, tr_app, tr_den)."""
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows)]
    col = {name: header.index(name) for name in header}

    def num(cell) -> int:
        if cell is None:
            return 0
        return int(str(cell).replace(",", "").strip() or 0)

    sums: dict[tuple[str, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        name = str(row[col["Employer (Petitioner) Name"]] or "").strip()
        if not name:
            continue
        fy = int(float(str(row[col["Fiscal Year"]]).strip()))
        key = (canonicalize(name), fy)
        s = sums[key]
        s[0] += num(row[col["New Employment Approval"]]) + num(row[col["New Concurrent Approval"]])
        s[1] += num(row[col["New Employment Denial"]]) + num(row[col["New Concurrent Denial"]])
        s[2] += num(row[col["Change of Employer Approval"]])
        s[3] += num(row[col["Change of Employer Denial"]])
    wb.close()
    return {k: tuple(v) for k, v in sums.items()}


def main() -> int:
    uscis_files = sorted(SRC.glob("Employer Information*.xlsx"))
    if not uscis_files:
        print(f"No USCIS xlsx files in {SRC}")
        return 1

    print("== 1. Ingest vs independent recomputation ==")
    buckets: dict[tuple[str, int], YearBucket] = {}
    expected: dict[tuple[str, int], tuple[int, int, int, int]] = {}
    for f in uscis_files:
        print(f"  reading {f.name} ...")
        ingest_uscis_xlsx(f, buckets)
        expected.update(independent_sums(f))

    rng = random.Random(42)
    sample_keys = [k for k in expected if any(k[0].startswith(a) for a in ANCHORS)]
    sample_keys += rng.sample(sorted(expected.keys()), RANDOM_SAMPLE)
    for key in sample_keys:
        exp = expected[key]
        b = buckets.get(key)
        got = (
            (b.new_approvals, b.new_denials, b.transfer_approvals or 0, b.transfer_denials or 0)
            if b
            else (0, 0, 0, 0)
        )
        check(f"{key[0]} FY{key[1]}", got == exp, f"ingest={got} independent={exp}")

    print("== 2. FY2020 cross-vintage identity ==")
    fy2020_new = sum(b.new_approvals for (_, fy), b in buckets.items() if fy == 2020)
    check(
        "FY2020 new_h1b approvals == legacy Initial total",
        fy2020_new == FY2020_NEW_APPROVALS_TOTAL,
        f"got {fy2020_new:,}, expected {FY2020_NEW_APPROVALS_TOTAL:,}",
    )

    print("== 3. Transfer breakout populated ==")
    with_breakout = sum(1 for b in buckets.values() if b.transfer_approvals is not None)
    check(
        "every ingested bucket has a transfer breakout (no NULLs from real files)",
        with_breakout == len(buckets),
        f"{with_breakout:,}/{len(buckets):,}",
    )

    print("== 4. DOL join check (one quarter) ==")
    dol = SRC / DOL_JOIN_FILE
    if dol.exists():
        ingest_dol_xlsx(dol, defaultdict(YearBucket, buckets))  # merges on same keys
        dol_buckets: dict[tuple[str, int], YearBucket] = defaultdict(YearBucket)
        ingest_dol_xlsx(dol, dol_buckets)
        for anchor in ANCHORS:
            lca = sum(b.certified for (name, _), b in dol_buckets.items() if name.startswith(anchor))
            uscis = sum(
                b.new_approvals for (name, fy), b in buckets.items()
                if fy == 2025 and name.startswith(anchor)
            )
            check(f"{anchor}: LCA and USCIS on same canonical key", lca > 0 and uscis > 0,
                  f"lca={lca:,} uscis_new={uscis:,}")
    else:
        check(f"{DOL_JOIN_FILE} present", False, "file missing")

    print()
    if failures:
        print(f"GATE CLOSED — {len(failures)} failure(s): {failures}")
        return 1
    print("GATE OPEN — safe to run the full build.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Ruff-check the script**

Run: `.venv/Scripts/python.exe -m ruff check scripts/validate_uscis_subset.py`
Expected: clean (fix any line-length findings by wrapping).

- [ ] **Step 3: Run the gate**

Run: `.venv/Scripts/python.exe scripts/validate_uscis_subset.py`
Expected: `GATE OPEN` and exit 0. Takes ~1-3 min (five USCIS xlsx twice + one DOL quarter).

**If check 1 fails:** ingest bug (column index, comma parsing, summation) — fix in `etl/build.py`, re-run, do NOT proceed.
**If check 2 fails:** the new/transfer boundary is wrong — stop and re-verify petition-type column mapping against the FY2020 known totals (121,874 + 1,020).
**If check 4 fails on an anchor:** report the mismatch; a Deloitte-style entity-fragmentation miss on one anchor is a known limitation (swap in another anchor), but zero LCA for GOOGLE/AMAZON/MICROSOFT means a canonicalization regression — stop.

- [ ] **Step 4: Commit**

```bash
git add scripts/validate_uscis_subset.py
git commit -m "feat(etl): pre-build subset validation gate for USCIS split ingest"
```

---

### Task 8: Full rebuild (Ishan runs it) + post-build validation

**Files:** none created; `data/h1b_data.db` regenerated (gitignored).

- [ ] **Step 1: Hand Ishan the build command**

He runs it himself (established preference), foreground, in cmd.exe from `Projects\h1b-service`:

```
.venv\Scripts\python.exe scripts\build_data.py --source manifest --output data\h1b_data.db > data\build.log 2>&1
```

Expected: ~85 min (25 DOL quarters dominate). Wait for his confirmation; do not launch it yourself.

- [ ] **Step 2: Post-build validation queries**

Run (adjust nothing else):

```bash
.venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/h1b_data.db')
for name in ('GOOGLE', 'AMAZONCOM SERVICES', 'INFOSYS', 'MICROSOFT'):
    rows = conn.execute(
        'SELECT fiscal_year, certified_count, uscis_new_approvals, uscis_new_denials,'
        ' uscis_transfer_approvals, uscis_transfer_denials FROM aggregates'
        ' WHERE canonical_employer LIKE ? AND fiscal_year=2025', (name + '%',)).fetchall()
    print(name, rows[:3])
print('employers:', conn.execute('SELECT COUNT(*) FROM employers').fetchone()[0])
print('null transfers with uscis data:', conn.execute(
    'SELECT COUNT(*) FROM aggregates WHERE uscis_new_approvals > 0'
    ' AND uscis_transfer_approvals IS NULL').fetchone()[0])
"
```

Expected: anchors show 2025 rows with nonzero certified counts AND nonzero `uscis_new_approvals`; `null transfers with uscis data` = 0 (all real files carry the breakout); employer count ~165K.

- [ ] **Step 3: Live payload smoke test**

```bash
.venv/Scripts/python.exe -c "
import os
os.environ['H1B_TESTING'] = '1'
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as c:
    import json
    r = c.get('/v1/demo')
    print(json.dumps(r.json(), indent=2))
"
```

Expected: `signal.new_h1b` and `signal.transfers` both populated dicts with real denial rates (transfers NOT null — real data has the breakout). No `denial_rate` key at the signal top level. NOTE: this reads the real `data/h1b_data.db` via default config — it must exist (after Step 1) and `DEMO_EMPLOYER` defaults apply; if the demo employer lacks data, query `/v1/signal` is not possible without a key, so instead call `app.main._signal_payload` is NOT available pre-startup — keep to `/v1/demo` and if the default demo employer misses, set `os.environ['DEMO_EMPLOYER'] = 'GOOGLE'` before the import.

- [ ] **Step 4: Measure the name-join orphan rate (deferred analysis, now due)**

```bash
.venv/Scripts/python.exe -c "
import sqlite3
conn = sqlite3.connect('data/h1b_data.db')
total, orphans = conn.execute(
    'SELECT COUNT(*), SUM(CASE WHEN certified_count = 0 THEN 1 ELSE 0 END)'
    ' FROM aggregates WHERE uscis_new_approvals > 0 AND fiscal_year = 2025').fetchone()
print(f'FY2025 USCIS rows: {total:,}; without LCA match: {orphans:,} ({orphans/total:.1%})')
"
```

Record the number — it goes in the PLAN.md work log (Task 9). No fix in this plan; entity resolution is out of scope per the spec.

---

### Task 9: Docs — PLAN.md #10 amendment, CONTEXT.md glossary, work log

**Files:**
- Modify: `PLAN.md` (decision #4 denial wording at ~line 32-35, decision #10 route table at ~line 60, work log, known-limitation block at ~line 145-151)
- Modify: `CONTEXT.md` (glossary)

- [ ] **Step 1: Amend PLAN.md decision #4's denial sentence**

Replace the "Orthogonal fields, never folded into tier" wording (lines ~32-35) so it reads:

```
   - Orthogonal fields, never folded into tier: trend (rising|falling|flat,
     null when both years <10) and two USCIS denial blocks — new_h1b
     (New Employment + New Concurrent) and transfers (Change of Employer),
     each {approvals, denials, denial_rate (null when decisions <10),
     caution (>=15%)}; transfers is null when the source vintage lacks the
     breakout. Amended 2026-07-07 with sign-off (supersedes the single
     pooled denial_rate).
```

- [ ] **Step 2: Amend decision #10's `/v1/signal` row**

Change `trend + denial_rate` in the route table to `trend + new_h1b/transfers denial blocks`.

- [ ] **Step 3: Update the known-limitation block**

The "denial rate needs multi-year USCIS" limitation (~lines 145-151) is resolved: rewrite it to note USCIS FY2020–FY2026 consolidated files are loaded and both blocks populate from `latest_complete_fy`. Add a work-log entry: split implemented, subset gate results, full-build validation numbers, and the orphan rate measured in Task 8 Step 4.

- [ ] **Step 4: Add CONTEXT.md glossary terms**

Append to the glossary, matching its existing entry style:

```
- **New Sponsorship (new_h1b)** — USCIS petitions where the employer takes on
  a worker it did not previously sponsor at all: New Employment + New
  Concurrent. Equals the legacy export's "Initial" column exactly.
- **Transfer (transfers)** — Change of Employer petitions: the worker already
  holds H-1B status and moves to this employer. Signals willingness to hire
  existing H-1B holders even when an employer files few or no fresh/cap
  petitions. Null (not 0) when the source vintage has no breakout.
```

- [ ] **Step 5: Run full suite one last time**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check .`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add PLAN.md CONTEXT.md
git commit -m "docs: amend decision #10 for new_h1b/transfers split; glossary + work log"
```

---

## Execution order dependencies

Tasks 1→2→3 are strictly sequential (each leaves the suite partially red until Task 6 goes all-green; commit anyway — the red is scoped and expected, noted in each task). Task 4 needs 2. Task 5 needs 3. Task 6 needs 4+5. Task 7 needs 4 and gates Task 8. Task 9 last.
