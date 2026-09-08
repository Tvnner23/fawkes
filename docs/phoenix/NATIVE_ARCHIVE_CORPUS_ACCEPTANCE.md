# Native Archive Ambiguity Corpus Acceptance

Status: passed Phase 8 completion gate
Acceptance version: `native-archive-ambiguity-corpus-v1`

## Boundary

This gate qualifies existing Phase 8 native Archive retrieval behavior. It is
not a retrieval feature, canonical history source, or inherited-history test.
All 14 scenarios are deterministic, disposable, synthetic records scoped to
`acceptance-phoenix`; expected annotations live in a separate fixture and are
never supplied to candidate generation, eligibility, projection, preference,
or ambiguity policy.

Inputs and expected truth are respectively:

- `tests/fixtures/native_archive_acceptance_corpus.json`
- `tests/fixtures/native_archive_acceptance_expected.json`

`scripts/run_native_archive_corpus_acceptance.py` emits the machine-readable
result on stdout and a concise human summary on stderr.

## Thresholds fixed before assessment

- Material ambiguity recall: at least 90%.
- False-positive clarification rate: at most 10%.
- Safe joint-inclusion accuracy: 100%.
- Choice quality: 100%.
- Reference/traversal precision: at least 90%.
- Supported temporal interpretation accuracy: at least 95%.
- Fail-closed security/authority checks: 100%.
- Deterministic repeated results: 100%.

## Result

The final run passed every predeclared threshold:

- Material ambiguity recall: 4/4 (100%).
- False-positive clarification rate: 0/6 (0%).
- Safe joint inclusion: 1/1 (100%).
- Choice quality: 4/4 (100%).
- Reference/traversal precision: 12/12 intended generated references, 0
  unexpected references (100% precision).
- Temporal interpretation: 3/3 (100%).
- Fail-closed security/body-free/authority checks: 48/48 (100%).
- Deterministic repeated scenarios: 14/14 (100%).

The corpus covers repeated projects, similar vocabulary, overlapping native
references, explicit and relative dates, recent-conversation ambiguity,
earlier/thread navigation, verified two-hop references, safe joint inclusion,
restricted neighbors, empty results, explicit duplicate provenance,
contradictions, and stale projections.

## Defects found and corrected

The first run retained multiple direct lexical candidates across conversations
without declaring material reference ambiguity, producing 1/4 ambiguity recall
and 1/4 exact choice quality. It also allowed an out-of-window direct lexical
match to survive an explicit relative-time constraint. Final raw-count review
then found that a documented `the thing we discussed` reference kind did not set
the separate traversal-intent flag. The bounded correction:

- makes temporal constraints gate direct lexical candidate generation; and
- declares `multiple_direct_native_reference_matches` only when existing
  deterministic reference intent has direct matches in multiple conversations;
  and
- derives reference intent from either a conservative reference marker or an
  already-recognized documented reference kind.

No semantic resolver or broader vocabulary was added. Two fixture queries that
did not use the already documented reference phrasing were corrected instead of
tuning production vocabulary to the corpus. Generator
`native-archive-candidate-generator-v4`, native adapter v3, and capability
`continuity.native_projection` v1.7 record the production behavior.

All candidates still pass Phase 7 eligibility independently. The gate creates
no Archive, Memory, Library, Development, identity, relationship, continuity,
provider, research/tool, agent, or Ghost Rider authority. Automatic inherited
history remains disabled.
