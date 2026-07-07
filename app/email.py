"""Email delivery — Resend in production, in-memory capture for tests."""

from __future__ import annotations

import json
import urllib.request

from app.config import EMAIL_FROM, RESEND_API_KEY

# Captured OTP emails when RESEND_API_KEY is unset (tests / local dev)
_captured: list[dict[str, str]] = []


def captured_emails() -> list[dict[str, str]]:
    return list(_captured)


def clear_captured_emails() -> None:
    _captured.clear()


def send_otp_email(to: str, code: str) -> None:
    if not RESEND_API_KEY:
        _captured.append({"to": to, "code": code, "subject": "Your H-1B API code"})
        return

    payload = {
        "from": EMAIL_FROM,
        "to": [to],
        "subject": "Your H-1B API code",
        "text": f"Your verification code is {code}. It expires in 10 minutes.",
    }
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    urllib.request.urlopen(req, timeout=15)
