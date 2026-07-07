"""E2E OTP → key → signal flow with mock email capture."""

from __future__ import annotations

from app.email import captured_emails


def test_full_funnel(client):
    """Visit landing → request code → verify → signal call."""
    landing = client.get("/")
    assert landing.status_code == 200

    demo = client.get("/v1/demo")
    assert demo.status_code == 200
    assert demo.json()["signal"]["tier"] == "ACTIVE"

    email = "e2e@example.com"
    code_resp = client.post("/auth/code", json={"email": email})
    assert code_resp.status_code == 200

    code = captured_emails()[-1]["code"]
    verify = client.post("/auth/verify", json={"email": email, "code": code})
    assert verify.status_code == 200
    key = verify.json()["api_key"]

    signal = client.get(
        "/v1/signal",
        params={"company": "Datadog"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert signal.status_code == 200
    body = signal.json()
    assert body["matched"] is True
    assert body["signal"]["tier"] in ("ACTIVE", "ESTABLISHED", "RARE", "NONE")
