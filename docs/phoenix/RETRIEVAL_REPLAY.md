# Retrieval Flight Recorder and Replay Lab

Status: Phase 6 bounded foundation implemented.

## Boundary

The recorder creates immutable, instance-scoped diagnostic evidence after a
live response has been durably archived and its context receipt exists. The
Archive and context receipt remain authoritative. Failure to write diagnostic
evidence cannot invalidate or erase an ordinary rider turn.

Each flight records the request and response identities, model, selected
capabilities, versioned retrieval policy, queries, policy exclusions, selected
Memory/Archive/Library/working-context references, context allocation,
continuity outcome, response text/digest, latency, bounded usage, and warnings.
Phase 8 flights additionally preserve native continuity projection identity,
processor/frontier versions, stable native evidence identities, ambiguity and
duplicate relationship IDs, declared contradiction groups, and stale/current
status without copying candidate bodies into planning diagnostics.
They also preserve the versioned query interpretation, explicit temporal
bounds, expansion reason counts, generated evidence IDs, breadth limits, and
candidate-generation digest. Local lexical-term projections and evidence bodies
are omitted.
Relative-time records additionally bind the persisted request timestamp,
request-local timestamp, IANA timezone or exact fallback source, interpretation
version, and exact UTC window. Replay never consults the current wall clock.
Source-representation records preserve policy version, input/output evidence
IDs and counts, verified relationship kind, preferred representation, Phase 7
eligibility-policy versions, reduction count, decision reasons, and digest.
They contain no evidence bodies and explicitly report that no canonical merge
or truth resolution occurred.
Native candidate generation v3 additionally records deterministic thread or
reference hop depth, relationship type/ID, seed evidence ID, exact traversal
limits, expansion count, and explicit ambiguity sets. These remain body-free
planning facts over independently eligible native references.
Rider ambiguity records add stable ambiguity and choice IDs, materiality/safe
inclusion reason, clarification-required outcome, Phoenix/rider/turn bindings,
planner and eligibility versions, retrieval-plan identity, and a deterministic
decision digest. They contain no evidence body and explicitly grant no retrieval
or disclosure authority.
Choice-consumption records add the originating decision and plan identities,
selected ambiguity/choice IDs, validation status, fresh eligibility-result
identity, fresh planner/policy versions, final evidence-set identity, explicit
non-selected sibling exclusions, and the new permit identity/status. A failed
choice records a stable reason and zero evidence rather than a substituted
interpretation.
The current recorder honestly labels candidate observability as
`selected_and_policy_exclusions_only`: existing retrievers do not yet expose a
complete pre-ranking candidate stream.

Replay receives a detached copy of immutable flight input and writes only a
derived comparison under the owning Phoenix. It reports exact evidence
addition/removal/order differences and deterministic response hashes. It does
not append Archive messages, alter context receipts, create Memory or
Development, or call a comparison a semantic-quality judgment.

A replay difference becomes a regression case only through an explicit
reviewer-attributed promotion. There is no automatic pass/fail inference from
evidence overlap or response text.

## Storage and recovery

Records live under `database/retrieval_replay/<instance_id>/` in separate
`flights`, `replays`, and `regressions` collections. Writes are atomic and
append-only by stable identity. The Phase 0 ownership audit and complete-state
backup include this instance-scoped root.

## Deferred work

- Complete candidate, ranking-stage, exclusion-reason, token-allocation, and
  per-component latency/cost instrumentation.
- Authenticated rider/developer Replay Lab UI and managed candidate registry.
- Independent semantic evaluators, calibration, and human comparison workflow.
- Real-corpus known-answer evaluation, which remains artifact/authorization
  gated with Phase 5 qualification.
- Broader semantic projections and the rider-facing Context Inspector remain
  later roadmap slices. Deterministic authorized-source composition allocation
  and its registered response-purpose identity are now preserved inside the
  body-free Phase 9 composition audit.

Flight/replay metadata can now preserve transmission manifest identity,
provider route, authorized/denied evidence IDs, stable reasons, policy/adapter
versions, allocation, and warnings without evidence bodies or live calls.
It also preserves the body-free Phase 9 composition package identity, source
digests/authority/trust decisions, ordering, budget observations, and manifest
linkage. Replay receives only the sanitized composition audit.
