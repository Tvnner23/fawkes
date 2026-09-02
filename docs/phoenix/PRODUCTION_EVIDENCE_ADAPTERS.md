# Two-stage Production Evidence Adapters

Status: Archive, Memory, and Library adapters implemented and verified in
default served planner Chat mode; explicit legacy rollback remains available.

The adapter contract enforces this order:

1. enumerate body-free local metadata and stable references;
2. derive legacy compatibility where permitted;
3. evaluate ownership, principal, privacy, capability, provenance, state, and
   provider policy;
4. materialize only eligible references locally;
5. rank only eligible materialized candidates;
6. allocate distinct-domain evidence through the Unified Planner.

Restricted, foreign, malformed, quarantined, revoked, suppressed, unauthorized,
provider-denied, and otherwise ineligible candidates never reach
materialization or ranking. Semantic rankers receive only candidates whose
provider decision permits transmission. Ranker failure falls back only to local
ranking over that already-eligible set; it cannot reopen denied evidence.

The native Archive adapter preserves message/archive references and canonical
authority. The Memory adapter preserves derived-Memory authority and source
Archive lineage. The Library adapter preserves source, extraction, segment,
privacy, owner, and immutable-original authority. Inherited history has no
production adapter and remains disabled.

After native candidates pass eligibility and ranking, the Archive adapter adds
the current rebuildable Phase 8 continuity projection. This annotation cannot
add candidates, reopen a denial, merge originals, or resolve identity/truth. A
stale projection is reported and not applied.

Before materialization, the Archive adapter now generates a bounded candidate
set from the independently eligible metadata pool using direct local lexical
terms, explicit ISO-date constraints, and one-hop conversation neighbors. No
generated candidate inherits its seed's eligibility. Generation terms are not
written to receipts or Flight diagnostics; deterministic reasons, IDs, limits,
and digests are recorded instead.

The native adapter then applies explicit representation preference before
materialization. Only a verified provenance edge to a stronger independently
eligible native representation may suppress a redundant context copy. The
decision cannot reopen policy denial, infer duplication from content, merge
Archive records, suppress contradictions, or grant provider authority.

Native adapter v2 also exposes verified body-free per-message native reference
metadata. Candidate generator v3 may traverse only targets already inside the
independently eligible pool, with deterministic two-hop/eight-edge bounds and
explicit ambiguity preservation. Traversal occurs before materialization and
cannot broaden Phase 7 authority.

The served builder constructs these three adapters only in explicit planner
mode, excludes working-context IDs before materialization, and binds the actual
provider route into allowed decisions. The prompt builder consumes and
re-verifies permits with deterministic legacy rollback and zero-evidence
degradation. Authenticated served HTTP acceptance and default activation are
verified.
