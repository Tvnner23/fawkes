# Production Context Composer

Phase 9 begins with `production-context-composer-v1`, a provider-neutral
structured package at the default planner Chat response boundary. It composes
only request-scoped inputs whose retrieval and provider authority were decided
upstream. It does not retrieve evidence, grant transmission, infer identity,
resolve contradictions, or mutate any canonical or developmental state.

## First production boundary

For planner Chat, the composer requires the retrieved evidence IDs to match the
exact authorized set from the existing transmission manifest. Each source
retains its domain, authority class, original evidence reference, privacy and
provider decision, stable identity, body digest, ordering, ambiguity,
uncertainty, and contradiction metadata where supplied. Memory, native Archive,
and Library remain distinct authorities.

Working conversation, approved research, media context, operational capability
context, and the current rider message also remain distinct package sections.
Retrieved, conversational, research, Library, Archive, Memory, and media content
are marked as data with no instruction authority. Only the current rider message
has rider-request authority; content cannot become system, developer, tool, or
disclosure authority by appearing in the package.

The intermediate package is content-addressed. Rendering verifies its identity,
so post-composition body or metadata tampering fails closed. The response
provider's exact-set permit is still reverified immediately before the real
provider call. If that verification fails, the runtime rebuilds and verifies a
new zero-retrieval package instead of editing a prompt string or falling through
to legacy retrieval. Explicit legacy mode remains the deterministic rollback.

## Audit and budgets

Context receipts and Retrieval Flight/Replay evidence carry a defensively
sanitized, body-free composition audit with package identity, source identities,
digests, authority/provenance/trust decisions, ordering, ambiguity and
contradiction metadata, provider-manifest linkage, budget observations, and
counts. Audit surfaces do not copy source, research, media, conversation, or
current-message bodies.

Budget reporting is deliberately honest. The composer consumes the Unified
Planner's already-authorized selection and conservative character budget; it
does not retrieve or rank additional evidence and does not claim exact provider
tokens.

## Registered purpose and final allocation

`composition-purpose-policy-v1` registers the existing/default
`response_model_context` profile version `1`. The profile is descriptive and
creates no authority. Unknown purpose/profile combinations fail closed. Future
profile names in roadmap examples are not registered merely by being named.

Before exact-set permit creation, `context-cross-source-allocation-v1` performs
a final deterministic whole-item allocation over provider-eligible evidence
only. When the selected set fits the upstream bound, it preserves the exact
input set and order, so ordinary Chat behavior is unchanged. If it exceeds the
bound, registered domains receive deterministic round-robin opportunities in
Memory, native Archive, then Library order; unknown future eligible domains are
ordered deterministically afterward. A noisy domain cannot starve every peer,
but the composer never retrieves weak evidence to manufacture diversity. A
single legitimate domain may use the available budget.

Contradiction-connected evidence is an atomic allocation unit: include all
members or omit the group, never select a truth winner. Bodies are never
truncated or rewritten. The resulting decision binds input, selected and
omitted evidence IDs, per-domain counts/characters, purpose/policy versions,
tie-break and contradiction policy, warnings, and a deterministic digest. Only
the post-allocation set receives the provider permit, and the package verifies
that exact allocation decision and permit set.

## Current limitations

Capability `context.compose` v1.1 is production-active. Structured composition,
registered response purpose, deterministic authorized-source allocation, exact
permit binding, and deterministic rendering are production-active.
`context.inspect` v1.0 is an authenticated, lazy rider projection over the
existing body-free context receipt and matching Flight record. It reports
purpose, source classes, selected/omitted identities, allocation observations,
contradiction/ambiguity/uncertainty indicators, exclusions/warnings, permit
status, and stable receipt/Replay references. It stores nothing new, never
reruns retrieval, and creates no authority. `context.feedback` v1.0 records one
of the registered versioned rider signals against the exact revalidated
receipt, package, allocation, permit, and Replay identity in the existing
Development feedback store. Records are body-free, immutable, idempotent, and
observational only. They cannot adjust ranking, eligibility, permissions,
Memory, identity, or policy. Phase 9 is complete;
richer intent-aware profiles require separate registration and authorization
review rather than free-form purpose strings.
Automatic inherited-history participation remains disabled. Research/tool
provider authority remains separate from response-provider authority.
