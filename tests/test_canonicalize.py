"""Layer-1 normalization rules — convergence and false-merge guards."""

from __future__ import annotations

import pytest

from etl.canonicalize import canonicalize

# Pairs that MUST converge (same employer, different source spelling)
CONVERGE = [
    pytest.param("AMAZON.COM SERVICES LLC", "AMAZON COM SERVICES LLC", id="dot-vs-space"),
    pytest.param("VISA U.S.A. INC", "VISA USA INC", id="dotted-acronym-vs-solid"),
    pytest.param("CITIBANK, N.A.", "CITIBANK N A", id="na-dotted-vs-spaced"),
    pytest.param(
        "ST. JUDE CHILDREN'S RESEARCH HOSPITAL",
        "ST JUDE CHILDRENS RESEARCH HOSPITAL",
        id="apostrophe",
    ),
    pytest.param("TEXAS A&M UNIVERSITY", "TEXAS A AND M UNIVERSITY", id="ampersand-vs-and"),
    pytest.param("JPMORGAN CHASE & CO.", "JPMORGAN CHASE AND", id="amp-co-vs-trailing-and"),
    pytest.param("A.T. KEARNEY, INC.", "A T KEARNEY", id="initials-collapse"),
    pytest.param("DELL PRODUCTS L.P.", "DELL PRODUCTS LP", id="lp-spaced-vs-solid"),
    pytest.param("MERCK SHARP & DOHME LLC", "MERCK SHARP AND DOHME", id="amp-mid-name"),
    pytest.param(
        "FIDELITY GROUP D/B/A FIDELITY INVESTMENTS",
        "FIDELITY GROUP D B A FIDELITY INVESTMENTS",
        id="dba-spellings",
    ),
    pytest.param("THE BOEING COMPANY", "BOEING COMPANY", id="leading-the"),
]


@pytest.mark.parametrize("a,b", CONVERGE)
def test_must_converge(a, b):
    assert canonicalize(a) == canonicalize(b), (
        f"{a!r} -> {canonicalize(a)!r} vs {b!r} -> {canonicalize(b)!r}"
    )


# Pairs that MUST stay distinct (different employers a blind rule would merge)
STAY_DISTINCT = [
    pytest.param("BANK OF AMERICA, N.A.", "BANK OF", id="no-geo-suffix-strip"),
    pytest.param("AMAZON.COM SERVICES LLC", "AMAZON WEB SERVICES INC", id="amazon-not-aws"),
    pytest.param("UNIVERSITY OF PENNSYLVANIA", "UNIVERSITY OF MONTANA", id="different-schools"),
    pytest.param("PC CONNECTION INC", "CONNECTION INC", id="pc-not-stripped-mid-name"),
    pytest.param("LP BUILDING SOLUTIONS LLC", "BUILDING SOLUTIONS LLC", id="lp-leading-kept"),
]


@pytest.mark.parametrize("a,b", STAY_DISTINCT)
def test_must_stay_distinct(a, b):
    assert canonicalize(a) != canonicalize(b), (
        f"FALSE MERGE: {a!r} and {b!r} both -> {canonicalize(a)!r}"
    )


# Exact expected outputs for individual rules
CASES = [
    pytest.param("FIDELITY GROUP D/B/A FIDELITY INVESTMENTS", "FIDELITY GROUP", id="dba-truncate"),
    pytest.param("DBA STAFFING LLC", "DBA STAFFING", id="dba-leading-kept"),
    pytest.param("SMITH MEDICAL P.C.", "SMITH MEDICAL", id="trailing-pc-stripped"),
    pytest.param("JONES & PARTNERS PLLC", "JONES AND PARTNERS", id="trailing-pllc"),
    pytest.param("JPMORGAN CHASE AND", "JPMORGAN CHASE", id="dangling-and-dropped"),
    pytest.param("Datadog, Inc.", "DATADOG", id="legacy-suffix-behavior"),
    pytest.param("N.V. Energy Corp.", "ENERGY", id="legacy-nv-behavior"),
    pytest.param("CAF BISTRO INC", "CAF BISTRO", id="mojibake-to-space"),
]


@pytest.mark.parametrize("raw,expected", CASES)
def test_exact_output(raw, expected):
    assert canonicalize(raw) == expected
