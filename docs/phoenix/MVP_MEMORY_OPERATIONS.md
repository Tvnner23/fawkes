# MVP Memory Processing Operations

This describes the working MVP boundary, not the final Phoenix memory ontology.

The immutable archive is evidence. Canonical messages, the processing ledger,
search indexes, assessments, and durable memory records are derived state. The
worker reads canonical user messages from the archive; it never edits archive
blobs or metadata.

The production flow is deliberately split:

`discover -> queued -> evaluating -> accepted/rejected/review -> consolidating -> consolidated`

Evaluation persists both the semantic assessment and the deterministic import
decision before any durable memory is changed. Only accepted work crosses the
persistence boundary. Each resulting memory records its Phoenix `instance_id`,
source message/archive IDs, and source work-item IDs. A retry can find a complete
record/event mutation and complete the ledger without duplicating memory. A
work-item ID alone does not establish completion. Pending local intents recover
before store reads; older partial records without sufficient event evidence go
to review and are not silently repaired or reported consolidated.

Use bounded batches:

```text
python src/fawkes.py memory status
python src/fawkes.py memory discover --limit 100 --include-legacy-unscoped
python src/fawkes.py memory process --limit 10 --yes
python src/fawkes.py memory apply --limit 10 --yes --include-legacy-unscoped
```

`process` and `apply` can make paid model calls and require `--yes`. The legacy
flag makes authorized legacy unscoped evidence eligible for discovery/retrieval;
it must not be used for another Phoenix. It does not silently assign ownership
to existing unscoped Memory records or authorize cross-instance mutation. Such
records require a separate explicit migration decision before scoped revision.

Review and recovery commands are:

```text
python src/fawkes.py memory show WORK_ITEM_ID
python src/fawkes.py memory decide WORK_ITEM_ID accept --note "reason"
python src/fawkes.py memory retry WORK_ITEM_ID
python src/fawkes.py memory recover-stale --minutes 30
python src/fawkes.py memory provenance MEMORY_ID
```

Provenance displays the memory, its mutation events, its processing decisions,
and the immutable archive IDs supporting it. Search indexes can be rebuilt from
canonical archive evidence. Memory records can be reproduced by replaying
accepted ledger assessments through the same persistence boundary; rebuilding
must always target fresh derived-state storage and must never rewrite evidence.

## Evolution boundary

The Archive is immutable evidence. Ledgers, assessments, indexes, memory
records, and runtime views are derived interpretations and should remain
rebuildable or migratable. Derived records carry schema, processor,
canonicalizer, or semantic-contract versions at their relevant boundaries.

Changing an interpretation contract must not silently reinterpret existing
state in place. Use a new version, preserve the prior assessment and provenance,
and rebuild or migrate into fresh derived state when practical. Existing memory
records without an explicit schema version are legacy version 0; readers must
continue to tolerate them until an audited migration is performed.

MVP mechanisms are not declarations of final Phoenix ontology. Keep instance
identity, immutable evidence, provenance, persistence, retrieval, and policy
boundaries separate from Fawkes-specific behavior and experimental features.
Choices that would constrain future Phoenix identity, relationships, privacy,
or development must be recorded as architectural decisions before becoming
irreversible dependencies.
# Source correction: explicit recovery and legacy review

When a retry finds historical work provenance without a bound mutation event,
the result is **review**, not fabricated completion. Later quarantine, merge,
or additional provenance does not repair that missing event. A legacy unscoped
Memory selected for an instance-owned mutation likewise requires an explicit
migration decision; it is not an automatically retried transient failure.
Ordinary legacy retrieval remains available under the existing explicit flag.
No real data migration or live provider processing is authorized by this note.
