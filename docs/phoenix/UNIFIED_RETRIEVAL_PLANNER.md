# Unified Retrieval Planner and Semantic Projection Foundation

Status: Phase 7 production planner path implemented and default-active;
automatic inherited-history retrieval remains disabled.

## Architectural boundary

The planner is a provider-neutral coordinator over explicit evidence-domain
adapters. It is not a unified database, truth store, vector index, or authority.
Each adapter declares its domain, version, authority class, required grants,
automatic-use policy, health, and optional derived projection descriptor.
Future evidence domains can implement the same interface without changing the
planner core.

Eligibility is evaluated before retrieval or ranking. Missing authorization,
disabled automatic use, unavailable/degraded adapters, Phoenix ownership
mismatch, incomplete provenance, malformed projections, stale projections, and
domain/authority mismatch produce explicit exclusions. Candidate scores or
rank cannot override those decisions.

## Evidence and identity

Candidate envelopes preserve their domain authority and an original-evidence
reference. The original remains authoritative; the candidate and projection
are rebuildable derivations.

Inherited-history envelopes additionally require and preserve:

- `history_era`
- `relationship_provenance`
- `identity_attribution`
- `native_boundary_status`
- provider/source provenance and `export_id`

The planner rejects an inherited candidate that claims `proven_native` and
does not normalize `boundary_unknown` or `unassessed`. It performs no identity,
continuity, contradiction, or truth resolution. Conflicting candidates remain
separate provenance-bearing evidence.

Automatic inherited-history retrieval remains disabled in production. The
adapter contract can represent it, but enabling it requires an explicit policy
and grant after real-corpus qualification.

## Budgeting and observability

The versioned v1 policy divides a bounded character budget deterministically
across eligible domains, then selects in domain-local rank rounds. This prevents
one noisy domain from consuming every allocation. Characters are explicitly a
conservative approximation, not exact provider tokens.

Plans explain requested and eligible domains, domain status, candidate counts
where adapters expose them, candidates, selected evidence, exclusions and
reasons, per-domain budget/use, warnings, policy version, and a deterministic
replay-input digest. Phase 6 flight records now preserve candidates, planner
warnings, allocation, exclusions, and deterministic replay inputs.

## Projection contract

`ProjectionDescriptor` provides deterministic projection identity from domain,
processor/version, method, source frontier, and optional model/version. It
declares projections derived and rebuildable, originals authoritative, and
reports `stale` whenever the indexed frontier differs from the current source
frontier. A semantic descriptor requires explicit model identity. No embedding
vendor or model is selected by this foundation, and no new durable projection
store is created.

## Side-effect boundary

Planning is read-only. It cannot write Memory, Archive, Library, inherited
staging, Development, personality, relationships, identity attribution, or the
native-history boundary. Replay remains detached and cannot mutate ordinary
state.

## Production served assembly

Explicit planner mode constructs the existing native Archive, Memory, and
Library two-stage adapters, applies production eligibility, allocates through
this planner, and passes the exact set to the permit boundary. Working-context
IDs are excluded before materialization and the actual response-provider route
is bound into allowed decisions. Planner evidence is not forwarded to a
separate research provider. Failure remains zero-evidence without legacy
fallback; explicit legacy mode remains the immediate rollback.

## Deferred Phase 7 work

- Qualified inherited-history automatic adapter and policy.
- Provider-neutral lexical/semantic projection implementations and rebuild
  lifecycle coordinated through the processing ledger.
- Broader semantic entity resolution and any truth/sufficiency adjudication.
- Exact model-token budgeting and later cross-source Context Composer allocation.
- Rider-visible body-free context inspection and exact-decision observational
  retrieval feedback are production-active through the Phase 9 Context Composer.

The first structured production composer integration is now implemented without
changing this planner's authority; see
[Production Context Composer](PRODUCTION_CONTEXT_COMPOSER.md).

The legacy compatibility boundary is defined by
[Legacy Archive and Memory Compatibility](LEGACY_EVIDENCE_COMPATIBILITY.md).
Remaining production adapters must separate local metadata enumeration and
eligibility from ranking and optional provider transmission. Wrapping today's
already-ranked results would violate eligibility-before-ranking.

Those two-stage Archive, Memory, and Library adapters are now implemented; see
[Two-stage Production Evidence Adapters](PRODUCTION_EVIDENCE_ADAPTERS.md).
Live Chat remains gated on pre-response-call evidence-level provider receipts
and rollback/equivalence integration.

The exact-set permit is consumed and re-verified by the live prompt builder in
explicit planner mode. Production builder wiring and authenticated served HTTP
acceptance and default activation are complete.
