#!/usr/bin/env python3
"""Print Heroku + GitHub secret setup commands for Phase 3 deploy."""

from __future__ import annotations

import secrets
import sys

APP_NAME = "h1b-signal-pilot"  # change before running heroku apps:create
REPO = "ixsx2/h1b-service"


def main() -> None:
    otp = secrets.token_hex(32)
    print("Phase 3 bootstrap — run locally after `heroku login`\n")
    print("1. Create app + Postgres:")
    print(f"   heroku apps:create {APP_NAME}")
    print("   heroku addons:create heroku-postgresql:essential-0 -a", APP_NAME)
    print()
    print("2. Heroku config:")
    print(f"   heroku config:set OTP_SECRET={otp} -a {APP_NAME}")
    print(f"   heroku config:set DEMO_EMPLOYER=DATADOG -a {APP_NAME}")
    print("   heroku config:set EMAIL_FROM=otp@YOURDOMAIN.dev -a", APP_NAME)
    print("   heroku config:set RESEND_API_KEY=re_... -a", APP_NAME)
    print("   heroku config:set SIMPLE_ANALYTICS=1 -a", APP_NAME)
    print()
    print("3. GitHub Actions secrets (Dashboard → Settings → Secrets):")
    print("   HEROKU_API_KEY  — heroku authorizations:create -d 'github-actions'")
    print(f"   HEROKU_APP_NAME — {APP_NAME}")
    print("   HEROKU_EMAIL    — your Heroku account email")
    print()
    print("4. Optional CI secrets: TESTMAIL_API_KEY, TESTMAIL_NAMESPACE")
    print()
    print("5. Connect repo deploy:")
    print(f"   heroku git:remote -a {APP_NAME}")
    print("   — or push via GitHub Actions deploy.yml after step 3")
    print()
    print(f"Repo: https://github.com/{REPO}")
    print("Docs: docs/deploy.md")


if __name__ == "__main__":
    main()
    sys.exit(0)
