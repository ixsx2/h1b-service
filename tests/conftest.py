"""Shared pytest fixtures."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.email import clear_captured_emails
from app.main import app
from etl.build import build_fixture_database

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def built_db(tmp_path_factory):
    """Build h1b_data.db from synthetic fixtures once per session.

    Writes to a pytest temp dir, NOT data/h1b_data.db — the test build must
    never clobber a real production build sitting at the default path.
    """
    gen = FIXTURES / "generate_fixtures.py"
    if gen.exists():
        import subprocess
        import sys

        subprocess.run([sys.executable, str(gen)], check=True)

    test_data_dir = tmp_path_factory.mktemp("h1b_test_data")
    db_path = test_data_dir / "h1b_data.db"
    users_path = test_data_dir / "users_test.db"
    os.environ["H1B_DATA_DB"] = str(db_path)
    os.environ["DATABASE_URL"] = f"sqlite:///{users_path}"
    os.environ["OTP_SECRET"] = "test-otp-secret"
    os.environ["DEMO_EMPLOYER"] = "DATADOG"
    os.environ["H1B_TESTING"] = "1"
    os.environ.pop("RESEND_API_KEY", None)

    build_fixture_database(FIXTURES, db_path)

    from app.main import _init_dbs

    _init_dbs()
    yield db_path


@pytest.fixture
def client(built_db):
    clear_captured_emails()
    # Reset the per-session temp users db (path set by built_db via DATABASE_URL).
    users_path = Path(os.environ["DATABASE_URL"].removeprefix("sqlite:///"))
    if users_path.exists():
        users_path.unlink()
    from app.main import _init_dbs

    _init_dbs()
    from app.db import UserDB

    UserDB().init_schema()
    with TestClient(app) as c:
        yield c
    clear_captured_emails()


@pytest.fixture
def api_key(client):
    """Signup flow returning a raw API key."""
    from app.email import captured_emails

    email = "test@example.com"
    r = client.post("/auth/code", json={"email": email})
    assert r.status_code == 200
    code = captured_emails()[-1]["code"]
    r = client.post("/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200
    return r.json()["api_key"]
