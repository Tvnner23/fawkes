# Phase 0 Trust Foundation

Phase 0 establishes ownership, integrity, provider privacy, recovery, and
runtime-health contracts. It does not migrate historical data, retain temporary
media, ingest ChatGPT history, or implement Phase 1 Library UX.

## Ownership audit

`audit_phoenix_state()` is a read-only projection over the existing durable
stores. It distinguishes:

- `owned`: an embedded `instance_id` matches the record scope;
- `foreign_owned`: another Phoenix's valid record, never included in the
  selected Phoenix's backup;
- `legacy_path_scoped`: an older leaf schema omitted `instance_id` but lives
  below a scoped instance directory;
- `legacy_unscoped`: historical material with no attributable Phoenix owner;
- `ownership_mismatch` and `invalid`: blocking integrity findings.

Legacy findings are reports, not assignments or migrations. New operational
Memory, conversation, Development, work-item, preference, receipt, research,
Library, and source-artifact writes require or embed instance scope. Explicit
legacy import/test paths remain separate compatibility mechanisms.

## Complete scoped-state recovery

A complete Phoenix snapshot includes byte-exact instance-owned Archive source
files, Memory and Development records, Library originals/metadata, settings,
context/capability/provider/research/Test Center receipts, filtered conversation
and instance registries, and a filtered copy of the Memory work ledger.

Canonical Archive search databases and manifests are rebuildable projections;
the manifest identifies them rather than treating them as source truth. Every
included file has a path, byte size, and SHA-256 digest. Verification rejects
missing, added, or altered files. Restore requires an empty isolated root and
refuses a different Phoenix identity.

Legacy-unscoped records are counted and excluded. Exclusion avoids silently
claiming ambiguous evidence or leaking it into another Phoenix's portable
state. Until controlled historical attribution/absorption occurs, a scoped
backup is complete for owned Phoenix state but deliberately not an ownership
decision about the legacy corpus.

No backup contains environment variables, application tokens, provider keys,
or credential material. Backup encryption is represented as a future
key-provider dependency; the current recovery API is server/development-only
and has no normal Chat action.

## Provider Privacy Gateway

External Chat reasoning, optional research planning, public-web research,
image/PDF analysis, audio transcription, presentation planning within a turn,
and background Memory triage are covered at their operational capability
boundaries. Each transmission has one stable identity and append-only
`authorized` plus `completed` or `failed` receipts. Receipts retain digests,
purpose, capability/provider class, privacy, authorization source,
transformations, correlation, and failure code—never request payloads,
credentials, or secrets.

## Dynamic health

Runtime capability health is separate from Test Center acceptance evidence.
Supported states are `live`, `partial`, `degraded`, `failed`, `rate_limited`,
`permission_blocked`, `disabled`, `untested`, `environmentally_unverifiable`,
and compatibility `unavailable`. A passing acceptance test cannot overwrite a
degraded runtime health state. Recent research and media outcomes update their
runtime health without granting or changing permissions.

## Active-development recovery extension

The implemented complete-state backup and isolated-restore foundation remains
authoritative. [Phoenix Checkpoint and Recovery](PHOENIX_CHECKPOINT_RECOVERY.md)
extends its architecture to working checkpoints, immutable known-good recovery
points, maximum rollback distance, worker-write recovery readiness, dependency
closure, and tiered restore proof. Those broader Development, Exchange,
embodiment, and Board automations are approved direction only; they do not
create another recovery store or reopen Phase 0.
