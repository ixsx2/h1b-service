"""Canonical Employer normalization — copied from JobApps pipeline logic, expanded.

Layer 1 of entity resolution (see docs/superpowers/specs/
2026-07-08-entity-resolution-design.md): deterministic rules only. Anything
that could merge two genuinely distinct employers is NOT a rule here — it
goes through the human-reviewed etl/aliases.csv instead.
"""

from __future__ import annotations

import re

_SUFFIX_RE = re.compile(
    r"\b(incorporated|corporation|technologies|technology|inc|llc|corp|ltd|plc|gmbh|sa|nv|co|labs)\b\.?",
    re.IGNORECASE,
)
# Two-letter entity-form markers strip in TRAILING position only — mid-name
# they are usually meaningful (PC CONNECTION, LP BUILDING SOLUTIONS).
_TRAILING_SUFFIXES = frozenset({"PC", "PLLC", "LLP", "LP", "PA"})


def _collapse_single_letter_runs(tokens: list[str]) -> list[str]:
    """Merge runs of 2+ adjacent single-letter tokens: U S A -> USA, A T -> AT.

    Never crosses a multi-letter token, so AMAZON COM stays two tokens."""
    out: list[str] = []
    run: list[str] = []
    for tok in tokens:
        if len(tok) == 1 and tok.isalpha():
            run.append(tok)
            continue
        if run:
            out.append("".join(run))
            run = []
        out.append(tok)
    if run:
        out.append("".join(run))
    return out


def canonicalize(name: str) -> str:
    """Suffix-stripped, punctuation-normalized, uppercased legal name."""
    base = name.strip()
    if not base:
        return ""
    s = base.replace("'", "").replace("'", "")  # apostrophe: delete, not space
    s = s.replace("&", " AND ")
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)  # all punctuation + mojibake -> space
    s = s.upper()

    tokens = _collapse_single_letter_runs(s.split())

    # DBA clause: keep the legal filer before it; a leading DBA is kept whole.
    if "DBA" in tokens:
        idx = tokens.index("DBA")
        if idx > 0:
            tokens = tokens[:idx]

    s = _SUFFIX_RE.sub(" ", " ".join(tokens))
    tokens = s.split()

    if tokens and tokens[0] == "THE":
        tokens = tokens[1:]
    while tokens and (tokens[-1] in _TRAILING_SUFFIXES or tokens[-1] == "AND"):
        tokens.pop()
    return " ".join(tokens)


def name_variants(company: str) -> list[str]:
    """Original name first, then a suffix/punctuation-stripped variant."""
    base = company.strip()
    variants = [base]
    alt = canonicalize(base)
    if alt and alt.lower() != base.lower():
        variants.append(alt)
    return variants
