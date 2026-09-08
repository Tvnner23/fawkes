# Historical Corpus Validation Contract

Status: Phase 5 deterministic foundation implemented with disposable synthetic
exports. No Tanner/Fawkes export has been staged or validated.

`history.validate_corpus` is an explicitly requested, read-only qualification
capability. It reparses the byte-preserved original through the registered
provider adapter and reconciles it with the instance-scoped staging projection:

- original SHA-256 digest;
- conversation identities and metadata;
- all branch nodes, including nodes without messages;
- message/node identities, roles, chronology fields, and exact text;
- parser warnings and manifest counts;
- inherited-history provenance invariants; and
- bounded known-query results with exact-original navigation.

The report is derived evidence. The immutable original remains authoritative.
The validator never writes Archive, Memory, Development, relationship state,
personality, or continuity. It cannot assign `proven_native`, classify founding
identity, or place inherited history into ordinary Chat/Context Composer input.

The current validator intentionally reparses the whole bounded export. Phase 5
readiness limits therefore still apply: a real export must pass artifact, RAM,
and disk preflight and must not exceed the supported whole-document bounds.
Actual corpus qualification requires the rider-authorized artifact and comparison
against the source account/export expectations; synthetic acceptance does not
claim the real corpus is complete.
