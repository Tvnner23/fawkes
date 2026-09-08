# Native Archive Continuity Projection

Status: bounded Phase 8 foundation implemented and active for eligible native
Archive evidence on the production planner path.

The `native-continuity-projection` v1 processor runs only after Phase 7 has
established Phoenix ownership, rider/private-context eligibility, provenance,
state, capability, and response-provider transmission eligibility. It does not
enumerate inherited history and cannot broaden the eligible evidence set.

For eligible native evidence it derives:

- a stable identity from Phoenix, conversation, message, and source Archive;
- deterministic recorded-time ordering;
- previous/next references within the original conversation;
- conservative capitalized lexical mentions explicitly marked unresolved;
- ambiguity sets when the same lexical mention appears in multiple selected
  conversations under a referential query;
- exact or conservative near-duplicate relationship groups without deleting,
  merging, or selecting a canonical winner;
- preservation of explicitly supplied contradiction-group identities without
  truth resolution.

The projection is rebuildable and content-frontier-addressed. If its built
frontier differs from current body-free Archive metadata, it reports `stale`
and is not applied. Originals remain authoritative. Its plan/receipt/Flight
metadata contains identities, counts, relationship-group IDs, versions, and
digests rather than evidence bodies.

## Query-aware candidate generation

The second bounded Phase 8 slice adds
`native-archive-candidate-generator-v3` before materialization and final Unified
Planner allocation. Archive Stage A emits a local body-free lexical-term
projection alongside stable provenance metadata. The centralized Phase 7 policy
independently evaluates every metadata envelope first. Only the resulting
eligible pool may be considered for:

- direct lexical metadata matches;
- explicit ISO-date constraints (`on`, `before`, `after`, or `between`);
- one-hop previous/next expansion within a directly or temporally matched
  candidate's original conversation.

Every generated relation has a deterministic relationship ID and reason.
Repeated generation paths collapse only the candidate-list reference while
retaining every reason; canonical records are never deduplicated or merged.
Stable round-robin caps currently allow at most four candidates per conversation
and twenty-four overall before domain ranking, preventing one thread from
starving other conversations. Ambiguous cross-conversation matches remain
separate and are annotated by the projection rather than resolved.

Candidate generation audit records interpretation/version, temporal bounds,
counts, evidence IDs, reasons, limits, and a replay digest, never lexical terms
or evidence bodies. Expanded neighbors cannot inherit seed authorization:
restricted, foreign, malformed, provider-denied, or otherwise ineligible
metadata is removed before expansion and cannot be materialized.

## Request-time and relative-time interpretation

The third bounded Phase 8 slice binds `native-continuity-query-v2` to the
persisted user-message timestamp before retrieval. Calendar interpretation uses
the configured IANA rider timezone (`FAWKES_TIMEZONE`). Missing timezone state
uses a deterministic UTC fallback; an invalid zone also fails to UTC and records
that distinct fallback reason. Naive or malformed request timestamps cannot
authorize a relative window.

Supported conservative windows are `today`, `yesterday`, `tomorrow`, `this
week`, `last week`, `this month`, `last month`, bounded `N days/weeks/months
ago`, `recently` (the preceding seven days), and `earlier` (the preceding thirty
days). Calendar boundaries are constructed in rider-local time and then stored
as exact UTC instants, preserving DST transitions. Explicit ISO dates use the
same timezone rule. Replay metadata records the original request timestamp,
local timestamp, timezone/source, exact UTC bounds, interpretation version, and
digest.

Conservative reference kinds now include conversation/discussion references,
professor/course/project/person labels, previous/next message, nearby context,
and earlier/later within a conversation. Topic-bearing references still require
lexical support. A generic conversation reference with no direct match may
generate one recent eligible anchor per conversation inside the documented
thirty-day window; multiple conversations form an explicit ambiguity set rather
than a guessed winner. Directional references expand only the requested side of
the eligible seed. Existing per-conversation/global caps remain in force.

## Bounded thread and native-reference navigation

The fifth bounded Phase 8 slice extends this same eligible-only generator.
Explicit navigation intent may walk at most two recorded-order hops within a
native conversation. It may also traverse up to eight body-free, explicitly
`verified` `thread_previous`, `thread_next`, `thread_related`, or `reference_to`
edges supplied by native Archive metadata. There is no parallel retriever.

Only targets already present in the independently Phase 7-eligible native pool
can be traversed. Missing, malformed, unverified, denied, foreign, or
provider-ineligible targets cannot enter the graph or piggyback on a seed.
Multiple verified targets remain an explicit ambiguity set. Cycles are bounded
by hop/edge limits and candidate-reference deduplication; canonical records and
contradiction groups remain distinct.

Candidate reasons retain hop depth, relationship type, seed identity, and a
stable relationship ID. Replay/Flight records these body-free facts with exact
limits and a deterministic generation digest. Final evidence still passes
source preference, planner allocation, exact-set permit creation, and immediate
provider-boundary re-verification.

## Source-original representation preference

The fourth bounded Phase 8 slice adds
`native-source-representation-preference-v1` after every metadata envelope has
independently passed Phase 7 policy and after candidate generation, but before
materialization and Unified Planner budgeting. It recognizes only the explicit
Archive metadata envelope:

```json
{
  "representation_provenance": {
    "schema_version": 1,
    "representation_class": "source_original | derived_copy | duplicate_copy",
    "relationships": [{
      "relationship": "duplicate_of | derived_from",
      "qualification_status": "verified",
      "target": {"archive_id": "...", "message_id": "..."}
    }]
  }
}
```

A copy is omitted from this request's context only when every hop has exactly
one verified edge and the chain resolves to a stronger representation already
present in the independently eligible native metadata pool. The strongest
qualified source-original may be added to the generated set using its own
eligibility decision. If any target was denied, missing, malformed, ambiguous,
cyclic, not stronger, or connected to declared contradiction metadata, the copy
is preserved. Text similarity never creates a lineage edge.

This is context redundancy control, not canonical deduplication: all Archive
records remain distinct and unchanged. Preference audit records stable evidence
and relationship IDs, policy versions, decision reasons, input/output counts,
budget reduction, and a deterministic digest without evidence bodies. The exact
post-preference set must still obtain and pass the normal response-provider
permit.

This is intentionally not an entity resolver, knowledge graph, contradiction
solver, semantic index, or continuity-identity classifier. Automatic inherited
history remains disabled. Broader entity/reference candidate generation and
natural-language phrasing beyond the documented windows remain later work.

## Rider-facing ambiguity clarification

The sixth bounded Phase 8 slice adds `native-retrieval-ambiguity-v1` after
eligible candidate generation and Unified Planner selection. Body-free eligible
choice descriptors provide stable ambiguity/choice IDs and natural date-based
labels without exposing raw internal IDs to the rider. Materially distinct
conversation or verified-reference interpretations cause served Chat to return
a concise deterministic clarification before permit creation or any response
provider call. Evidence is omitted rather than guessed.

An explicitly safe joint temporal-anchor basis may proceed only when every
plausible eligible interpretation fits the selected bounded plan. Ambiguity and
contradiction metadata remain intact. The decision binds Phoenix, rider,
originating request/correlation, planner and eligibility versions, and retrieval
plan identity; its digest is verified before use. Choice validation selects only
the intended ambiguity set and grants no retrieval or disclosure authority.
Wrong-turn, foreign, mismatched, or tampered choices fail closed.

Receipts and Flight/Replay retain the decision, choices, result, reason, policy
versions, and hashes without evidence bodies. This slice deliberately does not
create a general conversational state framework. A future bounded served choice
consumer may use the validation contract while still rerunning normal Phase 7
eligibility and exact-set permit enforcement.

## Served clarification-choice consumption

The seventh bounded Phase 8 slice consumes a structured rider choice only when
the immediately preceding assistant clarification and its immutable context
receipt match the active Phoenix and conversation. The payload must repeat the
decision ID, retrieval-plan identity, ambiguity/choice IDs, and original query;
the query digest, decision digest, rider/Phoenix scope, originating turn,
planner version, and eligibility version are revalidated before planning.

The production coordinator then runs again over current source state, including
fresh Phase 7 ownership, privacy, provenance, availability, capability, and
response-provider policy. The chosen evidence must survive the new plan. Only
the resolved ambiguity set is constrained; unrelated evidence remains subject
to ordinary allocation. A missing or newly denied choice fails to zero retrieval
and never substitutes a sibling. The final set receives a new content-addressed
permit and the existing immediate provider-boundary verification.

Consumption audit is body-free and records the originating decision/choice,
fresh eligibility identity, fresh plan/version information, final evidence-set
identity, exclusion reasons, and fresh permit outcome. The choice grants no
authority and creates no general conversation-state store.

## Ordinary rider-client interaction

The eighth bounded Phase 8 slice renders required clarification choices inside
the ordinary authenticated Chat conversation. Choices use accessible native
buttons with visible keyboard focus and explicit pressed, pending, consumed,
and failure states. Rider-facing labels come only from the served decision;
opaque evidence, ambiguity, choice, decision, plan, and permit identities remain
closure-bound and are not displayed as prose or DOM attributes.

Selection submits the existing `retrieval_clarification` object with the exact
originating assistant response, decision, old plan, ambiguity set, choice, and
original query. It cannot manufacture choices or authority. Duplicate clicks
are suppressed, successful controls remain visible but disabled, and stale or
conversation-mismatched decisions fail terminally with a truthful prompt to ask
again. Transient transport failure is explicitly shown and may be retried; no
sibling is chosen. The backend remains authoritative for fresh eligibility,
fresh planning, fresh permits, and final provider-boundary verification.

## Representative corpus qualification

The final Phase 8 gate runs `native-archive-ambiguity-corpus-v1` over 14
deterministic disposable synthetic scenarios. Expected annotations are separate
from runtime inputs. All fixed thresholds pass: 4/4 ambiguity recall, 0/6 false
positives, 1/1 safe joint inclusion, 4/4 choice quality, 100% traversal
precision with all 12/12 annotated references, 3/3 temporal accuracy, 48/48
fail-closed checks, and 14/14 repeated
determinism.

The initial run found that temporal windows did not constrain direct lexical
matches and that direct matches in multiple conversations under existing
reference intent were retained without a material ambiguity set. Raw-count
review also found that a recognized documented reference kind did not activate
traversal intent. Candidate generator v4 corrects those conditions only. Native production adapter v3
and capability `continuity.native_projection` v1.7 identify the qualified
behavior. No semantic resolver, truth selection, or broader reference vocabulary
was introduced. See
[Native Archive Ambiguity Corpus Acceptance](NATIVE_ARCHIVE_CORPUS_ACCEPTANCE.md).

Phase 8 is complete. Automatic inherited-history participation remains disabled.
