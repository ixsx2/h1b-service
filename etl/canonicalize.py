"""Canonical Employer normalization — copied from JobApps pipeline logic, expanded."""

from __future__ import annotations

import re

_SUFFIX_RE = re.compile(
    r"\b(incorporated|corporation|technologies|technology|inc|llc|corp|ltd|plc|gmbh|sa|nv|co|labs)\b\.?",
    re.IGNORECASE,
)


def canonicalize(name: str) -> str:
    """Suffix-stripped, punctuation-collapsed, uppercased legal name."""
    base = name.strip()
    if not base:
        return ""
    cleaned = _SUFFIX_RE.sub(" ", re.sub(r"\.", "", base).replace(",", " "))
    cleaned = " ".join(cleaned.split())
    return cleaned.upper()


def name_variants(company: str) -> list[str]:
    """Original name first, then a suffix/punctuation-stripped variant."""
    base = company.strip()
    variants = [base]
    alt = canonicalize(base)
    if alt and alt.lower() != base.lower():
        variants.append(alt)
    return variants
