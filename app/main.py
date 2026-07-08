"""FastAPI application — six frozen routes."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Template
from pydantic import BaseModel, EmailStr

from app import auth, config, quotas
from app.db import AggregatesDB, UserDB
from app.lookup import lookup_employer
from app.signal import build_signal

aggregates_db: AggregatesDB
user_db: UserDB


def _init_dbs() -> None:
    global aggregates_db, user_db
    from importlib import reload

    import app.config as config_mod

    reload(config_mod)
    aggregates_db = AggregatesDB(config_mod.H1B_DATA_DB)
    user_db = UserDB(config_mod.DATABASE_URL)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _init_dbs()
    if not config.H1B_DATA_DB.exists():
        raise RuntimeError(f"Aggregates database missing: {config.H1B_DATA_DB}")
    user_db.init_schema()
    yield


app = FastAPI(title="H-1B Sponsorship Signal", version="0.1.0", lifespan=lifespan)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def _log(request: Request, endpoint: str, query: str | None, key_id: int | None) -> None:
    user_db.log_request(
        endpoint,
        query,
        key_id,
        request.headers.get("user-agent"),
        _client_ip(request),
    )


def _error(status: int, error: str, hint: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "hint": hint})


def _block_payload(block) -> dict | None:
    if block is None:
        return None
    return {
        "approvals": block.approvals,
        "denials": block.denials,
        "denial_rate": block.denial_rate,
        "caution": block.caution,
    }


def _signal_payload(canonical: str, matched_as: str | None = None) -> dict:
    rows = aggregates_db.employer_aggregates(canonical)
    signal = build_signal(rows, aggregates_db.latest_complete_fy())
    payload = {
        "canonical_employer": canonical,
        "matched": True,
        "signal": {
            "tier": signal.tier,
            "trend": signal.trend,
            "new_h1b": _block_payload(signal.new_h1b),
            "transfers": _block_payload(signal.transfers),
            "certified_by_year": [
                {"fiscal_year": c.fiscal_year, "certified": c.certified}
                for c in signal.certified_by_year
            ],
            "latest_complete_fy": signal.latest_complete_fy,
        },
    }
    if matched_as:
        payload["matched_as"] = matched_as
    return payload


@app.get("/", response_class=HTMLResponse)
def landing(request: Request) -> HTMLResponse:
    template = Template((Path(__file__).parent / "landing.html").read_text(encoding="utf-8"))
    base = str(request.base_url).rstrip("/")
    html = template.render(
        demo_employer=config.DEMO_EMPLOYER,
        base_url=base,
        simple_analytics=config.SIMPLE_ANALYTICS_ENABLED,
    )
    return HTMLResponse(html)


@app.get("/healthz")
def healthz() -> dict:
    data_ok = config.H1B_DATA_DB.exists()
    return {
        "status": "ok" if data_ok else "degraded",
        "data_db": data_ok,
    }


@app.get("/v1/demo")
def demo(request: Request) -> JSONResponse:
    ip = _client_ip(request)
    q = quotas.check_demo_quota(user_db, ip)
    if not q.allowed:
        return _error(
            429,
            "quota_exceeded",
            f"Demo limit {q.limit}/day per IP. Resets at {q.reset_at}.",
        )
    _log(request, "/v1/demo", config.DEMO_EMPLOYER, None)
    resp = JSONResponse(_signal_payload(config.DEMO_EMPLOYER))
    resp.headers["X-Quota-Remaining"] = str(q.remaining)
    return resp


class CodeRequest(BaseModel):
    email: EmailStr


class VerifyRequest(BaseModel):
    email: EmailStr
    code: str


@app.post("/auth/code")
def auth_code(body: CodeRequest, request: Request) -> JSONResponse:
    err = auth.request_otp(user_db, body.email, _client_ip(request))
    if err:
        status = 429 if err.error == "rate_limited" else 400
        return _error(status, err.error, err.hint)
    return JSONResponse({"ok": True})


@app.post("/auth/verify")
def auth_verify(body: VerifyRequest) -> JSONResponse:
    api_key, err = auth.verify_otp(user_db, body.email, body.code)
    if err:
        status = 429 if err.error == "rate_limited" else 400
        return _error(status, err.error, err.hint)
    return JSONResponse({"api_key": api_key})


def require_api_key(
    authorization: Annotated[str | None, Header()] = None,
) -> int:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "hint": "Bearer API key required."},
        )
    raw = authorization.split(" ", 1)[1].strip()
    key_id = auth.resolve_api_key(user_db, raw)
    if key_id is None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_key", "hint": "Unknown API key."},
        )
    return key_id


@app.get("/v1/signal")
def signal(
    request: Request,
    company: str = Query(..., min_length=1),
    key_id: int = Depends(require_api_key),
) -> JSONResponse:
    q = quotas.check_key_quota(user_db, key_id)
    if not q.allowed:
        return _error(
            429,
            "quota_exceeded",
            f"Key limit {q.limit}/day. Resets at {q.reset_at}.",
        )

    with aggregates_db.connect() as conn:
        result = lookup_employer(conn, company)

    if result.outcome == "unmatched":
        # matched: false is never cached
        _log(request, "/v1/signal", company, key_id)
        return JSONResponse({"matched": False, "company": company})

    if result.outcome == "candidates":
        _log(request, "/v1/signal", company, key_id)
        return JSONResponse({"matched": False, "candidates": result.candidates})

    canonical = result.canonical_employer
    assert canonical
    payload = _signal_payload(canonical, result.matched_as)
    _log(request, "/v1/signal", company, key_id)
    resp = JSONResponse(payload)
    resp.headers["X-Quota-Remaining"] = str(q.remaining)
    return resp


@app.get("/v1/employer/{name}")
def employer_detail(
    request: Request,
    name: str,
    key_id: int = Depends(require_api_key),
) -> JSONResponse:
    q = quotas.check_key_quota(user_db, key_id)
    if not q.allowed:
        return _error(
            429,
            "quota_exceeded",
            f"Key limit {q.limit}/day. Resets at {q.reset_at}.",
        )

    with aggregates_db.connect() as conn:
        result = lookup_employer(conn, name)

    if result.outcome == "unmatched":
        _log(request, f"/v1/employer/{name}", name, key_id)
        return JSONResponse({"matched": False, "company": name})

    if result.outcome == "candidates":
        _log(request, f"/v1/employer/{name}", name, key_id)
        return JSONResponse({"matched": False, "candidates": result.candidates})

    canonical = result.canonical_employer
    assert canonical
    rows = aggregates_db.employer_aggregates(canonical)
    payload = {
        "canonical_employer": canonical,
        "matched": True,
        "aggregates": rows,
    }
    if result.matched_as:
        payload["matched_as"] = result.matched_as
    _log(request, f"/v1/employer/{name}", name, key_id)
    resp = JSONResponse(payload)
    resp.headers["X-Quota-Remaining"] = str(q.remaining)
    return resp


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException):
    if isinstance(exc.detail, dict):
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": "error", "hint": str(exc.detail)},
    )
