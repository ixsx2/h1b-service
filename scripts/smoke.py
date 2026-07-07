#!/usr/bin/env python3
"""Post-deploy funnel smoke: healthz → demo → OTP → signal."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def _request(
    method: str,
    url: str,
    data: dict | None = None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    body = None
    hdrs = {"User-Agent": "h1b-service-smoke/0.1", **(headers or {})}
    if data is not None:
        body = json.dumps(data).encode()
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def run(base_url: str, email: str, otp_code: str | None) -> None:
    base = base_url.rstrip("/")

    status, body = _request("GET", f"{base}/healthz")
    if status != 200 or body.get("status") != "ok":
        raise SystemExit(f"healthz failed: {status} {body}")

    status, body = _request("GET", f"{base}/v1/demo")
    if status != 200 or not body.get("signal"):
        raise SystemExit(f"demo failed: {status} {body}")

    status, body = _request("POST", f"{base}/auth/code", {"email": email})
    if status != 200:
        raise SystemExit(f"auth/code failed: {status} {body}")

    if not otp_code:
        print("auth/code OK — pass --otp-code to complete verify + signal steps")
        return

    status, body = _request("POST", f"{base}/auth/verify", {"email": email, "code": otp_code})
    if status != 200 or "api_key" not in body:
        raise SystemExit(f"auth/verify failed: {status} {body}")

    key = body["api_key"]
    company = urllib.parse.quote("Datadog")
    status, body = _request(
        "GET",
        f"{base}/v1/signal?company={company}",
        headers={"Authorization": f"Bearer {key}"},
    )
    if status != 200 or not body.get("matched"):
        raise SystemExit(f"signal failed: {status} {body}")

    print("Smoke OK: healthz → demo → OTP → signal")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("HEROKU_APP_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--email", default=os.environ.get("SMOKE_EMAIL", "smoke@example.com"))
    parser.add_argument("--otp-code", default=os.environ.get("SMOKE_OTP_CODE"))
    args = parser.parse_args()
    run(args.base_url, args.email, args.otp_code)


if __name__ == "__main__":
    main()
