"""Runtime configuration from environment."""

from __future__ import annotations

import os
from pathlib import Path


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


H1B_DATA_DB = Path(env("H1B_DATA_DB", "data/h1b_data.db"))
DATABASE_URL = env("DATABASE_URL", "sqlite:///data/users.db")
RESEND_API_KEY = env("RESEND_API_KEY", "")
EMAIL_FROM = env("EMAIL_FROM", "otp@localhost")
OTP_SECRET = env("OTP_SECRET", "dev-otp-secret-change-me")
DEMO_EMPLOYER = env("DEMO_EMPLOYER", "DATADOG")

KEY_QUOTA_PER_DAY = 500
DEMO_QUOTA_PER_DAY = 30
OTP_EXPIRY_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_RATE_PER_HOUR = 3
