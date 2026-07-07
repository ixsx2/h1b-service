"""Testmail-backed OTP e2e — runs in CI when secrets are configured."""

from __future__ import annotations

import os
import re
import time
import urllib.parse
import urllib.request

import pytest
from fastapi.testclient import TestClient

from app.main import app

TESTMAIL_API_KEY = os.environ.get("TESTMAIL_API_KEY", "")
TESTMAIL_NAMESPACE = os.environ.get("TESTMAIL_NAMESPACE", "")

pytestmark = pytest.mark.skipif(
    not (TESTMAIL_API_KEY and TESTMAIL_NAMESPACE),
    reason="TESTMAIL_API_KEY and TESTMAIL_NAMESPACE required",
)


def _testmail_inbox(tag: str) -> str:
    return f"{tag}.{TESTMAIL_NAMESPACE}@inbox.testmail.app"


def _poll_otp(tag: str, timeout: float = 30.0) -> str:
    deadline = time.time() + timeout
    params = urllib.parse.urlencode(
        {
            "apikey": TESTMAIL_API_KEY,
            "namespace": TESTMAIL_NAMESPACE,
            "tag": tag,
            "livequery": "true",
        }
    )
    url = f"https://api.testmail.app/api/json?{params}"
    while time.time() < deadline:
        with urllib.request.urlopen(url, timeout=15) as resp:
            payload = resp.read().decode()
        import json

        data = json.loads(payload)
        for email in data.get("emails", []):
            text = email.get("text") or email.get("html") or ""
            match = re.search(r"\b(\d{6})\b", text)
            if match:
                return match.group(1)
        time.sleep(2)
    raise TimeoutError("No OTP email received from Testmail")


def test_testmail_otp_signal_flow(built_db):
    tag = f"ci-{int(time.time())}"
    email = _testmail_inbox(tag)

    with TestClient(app) as client:
        r = client.post("/auth/code", json={"email": email})
        assert r.status_code == 200, r.json()

        code = _poll_otp(tag)
        r = client.post("/auth/verify", json={"email": email, "code": code})
        assert r.status_code == 200, r.json()
        key = r.json()["api_key"]

        r = client.get(
            "/v1/signal",
            params={"company": "DATADOG"},
            headers={"Authorization": f"Bearer {key}"},
        )
        assert r.status_code == 200, r.json()
        assert r.json()["matched"] is True
