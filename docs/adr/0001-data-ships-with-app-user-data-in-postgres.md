# Quarterly data ships with the app; user data lives in Postgres

The service stores two datasets with opposite lifecycles. The Employer-Year
Aggregates (`h1b_data.db`, SQLite) are read-only at runtime, fully rebuildable
from public DOL/USCIS files, and change only on the quarterly ETL — so they
ship inside the deploy artifact: each release is one immutable data vintage, a
deploy swaps all data atomically, and rolling back bad data is redeploying the
previous release. User data (accounts, API keys, OTP codes, request log) is
written constantly and irreplaceable, so it lives in Heroku Postgres, which
survives every deploy and dyno restart. The rule: replaceable data ships with
code; irreplaceable data lives in the database. A failed ETL run can therefore
never touch a user record.

Hosting is Heroku (GitHub Student Pack credit, $13/mo for 24 months = $0 out
of pocket). Heroku's ephemeral filesystem forbids writable local files across
its daily dyno restarts — which forces the user-data store to be Postgres
rather than a SQLite file, and conveniently makes the replaceable/irreplaceable
split impossible to violate by accident.

## Considered Options

- Railway + persistent volume, user data as a SQLite file: simplest code (one
  storage engine), but $5/mo of real money against a $0 Heroku credit; the
  Postgres swap is ~30 lines. Rejected on cost.
- Single database for aggregates and user data, refreshed in place by the ETL:
  rejected — a half-failed refresh serves partial data and every refresh risks
  the user tables.
- ETL running on the serving instance: rejected — parsing ~500MB DOL xlsx
  needs more memory than the web dyno should have, and a failed parse degrades
  the live service.
