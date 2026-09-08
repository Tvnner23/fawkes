# Manual Federated Historical Search Contract

Status: Phase 4 bounded vertical slice implemented with synthetic acceptance.
No real Tanner/Fawkes inherited history has been imported or searched.

## Purpose

Manual History is an authenticated, explicitly rider-triggered inspection
surface over two distinct evidence domains:

1. `native_archive` — the current Phoenix's canonical Archive projection and
   immutable Archive source records;
2. `inherited_history` — the current Phoenix's inert Phase 3 staging projection
   and authoritative imported export artifact.

It is not a Context Composer, ordinary Chat retrieval path, Memory input, or
historical-absorption mechanism.

## Result contract

Every result has a stable result identity, Phoenix owner, explicit domain,
source domain, history era, authority class, provider/source identity,
conversation/message identities, native-boundary status, deterministic
navigation snippet, and an instance-validated evidence reference.

Inherited results additionally retain relationship provenance, identity
attribution, export identity/digest, source conversation/message/node identity,
and the immutable original-evidence locator. `boundary_unknown` and
`unassessed` remain unchanged. Search performs no identity classification and
cannot establish `proven_native`.

Native and inherited retrieval scores are never compared. Results are
round-robin interleaved while retaining their within-domain position and rank
basis. Retrieval rank therefore does not imply identity, autobiographical, or
truth authority.

## Summary for navigation; original text for truth

Phase 4 uses bounded deterministic excerpts, not AI summaries. Each excerpt is
marked `navigation_only` and non-authoritative. Selecting **Open Exact
Original** resolves the domain-specific evidence identifier on the server,
rechecks Phoenix ownership and source integrity, and returns exact source text
plus its original source record. The immutable Archive record or untouched
export remains authoritative.

## Invocation and failure behavior

The web History view and authenticated `/api/history/search` endpoint are the
manual invocation boundary. `/api/history/evidence/<domain>/<evidence-id>` is
the exact-source navigation boundary. Search is read-only and requires the
`history.search_manual` task-request permission contract.

Each requested domain reports `available`, `unavailable`, or `degraded`. A
missing or malformed domain projection does not cause another valid domain to
disappear. No-match is distinct from domain unavailability.

## Deliberate separation

`FawkesChatRuntime.build_context` has no dependency on the federated search or
inherited-history store. Manual results are not returned in Chat context and do
not write Archive, staged originals, Memory, Development, relationships,
personality, or continuity. Capability availability and Test Center acceptance
remain separate.

## Deferred roadmap scope

This bounded slice does not yet federate Memory, Library, or Development;
provide semantic/date/project filters; generate AI navigation summaries;
recover attachment navigation; validate the real corpus; or activate Context
Composer, historical absorption, continuity genesis, Replay, Ghost Rider, or
the Development Orchestrator. Those remain later explicit phases.
