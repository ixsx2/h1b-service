"""API, auth, quota, and lookup integration tests."""

from __future__ import annotations

from app.email import captured_emails


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["data_db"] is True


def test_demo_returns_signal(client):
    r = client.get("/v1/demo")
    assert r.status_code == 200
    data = r.json()
    assert data["canonical_employer"] == "DATADOG"
    assert data["signal"]["tier"] == "ACTIVE"
    assert "X-Quota-Remaining" in r.headers


def test_signal_requires_key(client):
    r = client.get("/v1/signal", params={"company": "Datadog"})
    assert r.status_code == 401


def test_signal_exact_match(client, api_key):
    r = client.get(
        "/v1/signal",
        params={"company": "Datadog, Inc."},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is True
    assert data["signal"]["tier"] == "ACTIVE"


def test_signal_unmatched_not_tier_none(client, api_key):
    r = client.get(
        "/v1/signal",
        params={"company": "Totally Unknown ZZZ Corp"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is False
    assert "signal" not in data
    assert "tier" not in data


def test_otp_flow(client):
    email = "otp-flow@example.com"
    r = client.post("/auth/code", json={"email": email})
    assert r.status_code == 200
    assert len(captured_emails()) == 1
    code = captured_emails()[0]["code"]
    r = client.post("/auth/verify", json={"email": email, "code": code})
    assert r.status_code == 200
    assert "api_key" in r.json()


def test_otp_invalid_code(client):
    email = "bad-code@example.com"
    r = client.post("/auth/code", json={"email": email})
    assert r.status_code == 200
    r = client.post("/auth/verify", json={"email": email, "code": "000000"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_code"


def test_key_quota_header(client, api_key):
    r = client.get(
        "/v1/signal",
        params={"company": "DATADOG"},
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 200
    remaining = int(r.headers["X-Quota-Remaining"])
    assert 0 <= remaining < 500


def test_employer_detail(client, api_key):
    r = client.get(
        "/v1/employer/DATADOG",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["matched"] is True
    assert len(data["aggregates"]) >= 1


def test_landing_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "H-1B Sponsorship Signal" in r.text
