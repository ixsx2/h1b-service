# Entity-resolution ceiling is marquee-correct, not a target orphan rate

The DOL↔USCIS join runs entirely on `canonicalize()` of the employer name
(the FEIN join is dead: USCIS ships only the last four Tax-ID digits). Names
spell differently across the two sources, so a residual set of USCIS employers
will always lack a DOL match. We decided the pilot's definition of "done" is
**marquee-correct**: the ~40 highest-stakes employers a user is likely to query
must cross-match correctly (enforced by the ship gate), the top orphans by
approval volume are curated into `aliases.csv`, and the residual orphan rate is
*published as an honesty metric, never chased as a target*.

The rejected alternative was driving the global orphan rate below a numeric
target (e.g. <5%). It is rejected because it is unbounded — roughly 30% of
orphans have no similar DOL string at all and cannot be fuzzy-matched — and
because pursuing a low number pressures toward the banned auto-merge, whose
~15-20% wrong-same rate would produce false merges. A false merge (joining two
distinct employers) is a confident wrong answer, strictly worse than an honest
orphan. Coverage of the names users actually type, not a global percentage, is
the success criterion.

## Consequences

- A future move to an external crosswalk (SEC EDGAR, OpenCorporates, GLEIF) to
  lower orphans is deferred behind engagement evidence, not perfectionism: only
  pursue it if post-launch query data shows users repeatedly hitting orphaned
  employers. See the entity-resolution spec "Out of scope".
- The published orphan rate is approval-weighted (see the entity-resolution
  spec); it is observability, explicitly not a gate.
