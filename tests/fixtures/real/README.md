# Real DOL / USCIS files (optional)

Place downloaded source files here to run `tests/test_real_etl.py`:

- `LCA_Disclosure_Data_FY2025_Q4.xlsx` (or other FY2025 quarters)
- `LCA_Disclosure_Data_FY2026_Q1.xlsx`
- USCIS Employer Data Hub CSV export (any `*.csv` name)

Download from:

- DOL: https://www.dol.gov/agencies/eta/foreign-labor/performance
- USCIS: https://www.uscis.gov/tools/reports-and-studies/h-1b-employer-data-hub/h-1b-employer-data-hub-files

Then:

```bash
python -m etl.build \
  --dol tests/fixtures/real/LCA_Disclosure_Data_FY2025_Q4.xlsx \
  --dol tests/fixtures/real/LCA_Disclosure_Data_FY2026_Q1.xlsx \
  --uscis tests/fixtures/real/employer_hub.csv \
  --output data/h1b_data.db

pytest tests/test_real_etl.py -v
```

Files are gitignored (large, public sources).
