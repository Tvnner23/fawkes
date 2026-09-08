# Inherited History Staging Contract

Status: Phase 3 foundation implemented; pre-Phase-5 readiness hardening uses
staging schema v2 / ChatGPT processor v1.1. No real rider export has been
imported.

## Purpose and authority

The staging layer preserves an explicitly authorized provider export as
inspectable source evidence. It is deliberately inert. Importing evidence does
not create Memory, Development or relationship truth, personality influence,
an autobiographical claim, a native-history boundary, or a continuity lineage.

The untouched export ZIP is the authoritative artifact. Its SHA-256 digest and
provider/export identity determine stable export identity. Conversation,
branch/node, and message identities remain linked to exact source identifiers.
The SQLite index is an instance-scoped inspection projection; it never replaces
the original ZIP.

## Provider-neutral boundary

`ExportAdapter` is the narrow provider-neutral parser contract.
`ChatGPTExportAdapter` is the first adapter and accepts a bounded ChatGPT export
ZIP containing exactly one `conversations.json`. Archive size, member count,
member size, structure, and JSON are validated before staging. Invalid exports
fail honestly; valid records in a partially malformed export are staged with
explicit warnings.

The projection retains every valid branch node, including message-less root or
deleted nodes, independently from searchable messages. Source conversation
array position, source node identity, and source message identity jointly keep
duplicate/irregular source IDs distinct rather than silently merging them.

## Historical provenance

Every staged export, conversation, message, and search result carries:

- `history_era: inherited_history`;
- provider, format, export ID, and original digest;
- `relationship_provenance: founding_developmental`;
- `identity_attribution: unassessed` by default;
- `native_boundary_status: boundary_unknown` by default;
- processor identity/version and an exact original-evidence locator;
- explicit unassessed derivation/uncertainty metadata.

The importer recognizes the vocabulary for identity attribution and native
boundary status but never assigns `proven_native`. First-person or third-person
wording is not classified during import. Original ambiguity remains evidence.

## Ownership, processing, and recovery

Artifacts and projections live beneath
`database/inherited_history/<phoenix_instance_id>/`. Work is coordinated through
the per-Phoenix Universal Processing Ledger using export-digest idempotency.
Malformed source validation is terminal for that exact artifact; interrupted
durable writes are retryable. Re-importing a completed export returns the same
manifest without duplicating records.

Phase 0 ownership audit checks both path-scoped JSON and staging-database owner
metadata. Complete-state backup copies originals, manifests, projection, and
processing evidence for only the selected Phoenix; isolated restore remains
empty-target and hash verified.

The official `stage_authorized_export` boundary requires both the registered
`history.import_stage` permission and explicit confirmation. The internal store
also requires a matching Phoenix/principal authorization record; it has no
default or inferred rider identity. Raw bytes are kept out of capability
receipts.

For an accepted, size-bounded artifact, the original ZIP and an immutable
artifact-received receipt are written before JSON parsing. Consequently a
malformed but accepted ZIP remains inspectable and recoverable even when its
processing work terminates. Unexpected parser/runtime failures become
retryable rather than leaving work falsely `running`. Failed atomic temporary
writes are cleaned up; immutable completed artifacts are never overwritten.
An uncatchable process/power interruption may legitimately leave a `running`
ledger item. Recovery then requires `resume_confirmed_interruption=True` through
the same authorized boundary after an operator has verified the old worker is
not alive; the recovery is appended to ledger evidence and is never inferred.

Compressed exports above 512 MiB and `conversations.json` members above 256 MiB
are rejected by current bounded policy. Parsing remains whole-document and is
not yet streaming. A real import must therefore perform the documented size,
free-disk, and available-memory preflight; an export outside those bounds must
wait for a streaming adapter rather than bypassing limits.

## Retrieval boundary

The current Archive/continuity retriever reads only canonical native Archive
sources and does not inspect this staging root. Staged search is an explicit,
bounded inspection function that always returns era/native-boundary provenance.
Federated manual search is Phase 4. Staged history must not enter an
authoritative Context Composer until that composer preserves domain, era,
authority, provenance, and uncertainty at every boundary.

## Not activated

This phase does not import Tanner's export, recover attachments, generate AI
summaries, semantically classify identity, absorb history, create Memory,
rewrite relationships/personality, establish continuity genesis, or activate
Replay, Ghost Rider, or the Development Orchestrator.
