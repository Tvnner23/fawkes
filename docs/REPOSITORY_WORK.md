# Repository work and cleanup

## Current objective

Finish the recorded repository-professionalization work, establish a verified
private GitHub backup, then resume the next ready authorized canonical roadmap
task. The [current pointer](phoenix/CURRENT_IMPLEMENTATION.md) owns present
status; the [layout](REPOSITORY_LAYOUT.md) owns navigation, not acceptance.

Contributor batch 1 is already accepted/integrated at
`74050de912f877f4fe3249284cf373b797ee7b11`; its original application failures
were condition ordering and filesystem modes, not missing contributor content.
Keep their historical outcomes. The private console is now complete at G22.

## Preserved work index

[repository-work-inventory.json](repository-work-inventory.json) is a derived,
source-bound index over the 126 unfinished paths present at the captured G22
baseline. Every entry records path, SHA-256, length, node type, mode and
modified/untracked state. Source presence, historical notes and inclusion as
review context do not independently accept those deltas. Missing acceptance
evidence is explicitly unknown, not silently promoted or discarded.

| Group | Paths | Next coherent treatment |
| --- | ---: | --- |
| App package marker | 1 | Preserve and review with the application dependency baseline |
| Operational helpers | 7 | Inspect side effects and matching tests; do not run import/provider/notification helpers as smoke tests |
| Archive, Library and Memory source | 43 | Separate preservation/reproducibility from actual semantic corrections; bind the matching tests and ownership contracts |
| Phoenix contracts/planning | 12 | Resolve canonical versus proposed lineage before adoption; retain original source |
| Root/client configuration | 3 | Review ignore rules and pinned build inputs without dependency upgrades |
| Runtime continuity/ownership | 15 | Trace the actual import/ownership boundary and relevant qualification before accepting a batch |
| Matching tests/fixtures | 45 | Carry with their source boundary; skipped live/provider gates remain skipped |

The inventory check detects a missing/duplicate entry, changed bytes or mode,
incorrect source count, missing navigation target and stale status-evidence
binding. Source classification and status/receipt bindings are compared to a
dated, digest-pinned [test source projection](../tests/fixtures/repository_cleanup_source_bindings.json).
Its values are revalidated from complete retained originals during qualification;
regenerating the inventory's own digest does not validate its provenance. This
fixture is not a new planning database or authority. An intentional accepted group change requires a reviewed inventory
update. Do not use the old path count as a reason to roll back newer work.

## Remaining cleanup, not another feature project

- Reconcile stale implementation/review-entry references without deleting the
  historical capture. Keep one present-state pointer.
- Make the necessary retained source baseline reproducible through separately
  reviewed logical groups. A HEAD-only checkout currently omits unfinished
  imports and build inputs; a successful local test is not proof HEAD reproduces it.
- Assess actual duplication or misplaced material before moving it. Keep
  generated/runtime/private state outside source history; do not delete it.
- Review outgoing history and current proposed source before private GitHub
  backup. Verify destination visibility and non-force ancestry first. No
  credentials, personal conversation/memory or runtime stores belong in that backup.

The first private backup completed on September 13: `origin/main` was read back
as G22 `e4fdddb7af525dbf32bb804ff6727313224ce430`. Its complete outgoing history
was screened before the non-force push. The status evidence binds the result;
the 126 unfinished paths were excluded. Later accepted commits still require
incremental screening and normal push. Screening is not a guarantee that every
possible secret can be detected.

The [September 8 assessment](phoenix/assessments/2026-09-08/Fawkes-Repository-Assessment.md)
is a dated source for reproducibility and remaining recovery/provenance risks,
not a current failing test or permission to rewrite those subsystems. Reproduce
an unresolved defect in current material before proposing a causal correction.
Broader Memory semantics and later roadmap features are not documentation cleanup.

## Recovery and evidence

Use [Contributing](../CONTRIBUTING.md) for exact review/application/integration.
Retain the original dirty-work preimages, immutable candidates and failed
records. The [status evidence](repository-status-evidence.json) provides
hash-bound local evidence locators; it is a navigation record, not an authority
registry or replacement receipt. Machine-local originals are intentionally not
published with private conversation bodies.

No blanket stage, clean, reset, stash, history rewrite or generic bypass of the
guarded Git owner is part of this cleanup. An accepted batch changes only its
reviewed paths; a mismatch requires reconciliation. The running Pi source and
rollback remain independent of this documentation candidate.
