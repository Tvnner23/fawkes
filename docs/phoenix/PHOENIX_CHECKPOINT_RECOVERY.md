# Phoenix Checkpoint and Recovery Contract

**Contract ID:** `phoenix.checkpoint_recovery`\
**Version:** 1.0\
**Status:** Canonical Phase 0 extension; broad development automation not implemented

## Purpose and authority

This contract extends the existing Phase 0 ownership, integrity, backup, and
isolated-restore foundation into active Development, Worker Exchange, Assurance,
embodiment, migrations, and future tools. It does not create another backup
authority or store.

**Continuity before velocity:** ordinary failure should normally lose at most
the current bounded slice. Long-running work should normally lose at most the
current validated substep. A worker must not accumulate multiple completed,
independently useful units inside one unrecoverable candidate.

Synchronization, Git, a file copy, or checkpoint existence is not sufficient
recovery evidence. No checkpoint becomes known-good, baseline, canonical, or
promoted merely because it exists.

## Working checkpoint versus known-good recovery point

A **working checkpoint** cheaply preserves incomplete or defective work before
risk and after useful substeps. It records exact state, parent/baseline, worker,
scope, dirty/unsaved condition, dependencies, and known defects. Retention may
roll according to domain policy. It is never authoritative merely by capture.

A **known-good recovery point** is immutable, Phoenix/domain scoped, linked to
an explicit parent/rollback lineage, dependency-closure verified, isolated-
restore tested at the required assurance tier, and linked to acceptance and
assurance state. It may become the current baseline only through the affected
domain's explicit promotion boundary. Prior known-good state remains available
until its successor is stable.

Lifecycle vocabularies remain versioned per domain rather than being inferred
from filenames. Descriptive concepts include working, experimental,
failed-preserved, candidate, verified-known-good, current-baseline,
retained-rollback, superseded, and deprecated-but-recoverable; this list is not
a closed storage enum.

## Recovery envelope

A recovery record preserves or references:

- checkpoint/recovery identity, owner Phoenix, domain, reality scope, state,
  creation time, actor/worker, approved scope, and policy version;
- exact parent, baseline, candidate, rollback, branch/worktree/session, dirty
  state, and promotion references;
- source/artifact IDs, paths/locators, byte sizes, content/revision digests,
  provenance, and dependency inventory;
- relevant repository state including important uncommitted changes;
- authoritative runtime stores and rebuildable-projection declarations;
- configuration and dependency/environment/tool versions;
- protected behaviors, known-good expectations, known defects/exceptions,
  acceptance contract, builder evidence, assurance, and rider review;
- restore environment, latest restore result, limitations, and externally held
  dependencies that cannot be captured.

Secrets remain outside ordinary snapshots and use protected opaque references;
future credential recovery depends on the Secrets Broker. Derived artifacts may
be regenerated only when deterministic regeneration and dependencies are
proved. Promoted external artifacts are normally retained by digest because
tool/exporter changes can alter future regeneration.

## Dependency closure and failure domains

Risk-appropriate recovery covers repository/uncommitted state, durable runtime
databases, Archive/Memory/Library structure, configuration, capability/authority
configuration, Development/Worker Exchange/Assurance records, Presence assets,
editable embodiment sources, GLBs, animation/material/texture assets,
provenance, migrations, environment manifests, and unavailable external state.

Architecture must address overwrite, corruption, partial copy, synchronization
conflict, propagation of corruption, missing/stale linked resources, tool drift,
nondeterministic regeneration, storage exhaustion, broken-state checkpointing,
dirty unsaved work, excessive copies, and backups sharing one failure domain.
Direction includes atomic save/copy/verify, immutable known-good points, content
digests/addressing, lifecycle metadata, deduplication, quotas/health warnings,
rolling retention for working state, independent storage failure domains, and
periodic restore drills. No single mechanism is sufficient by itself.

## Event-driven cadence

Checkpoints are driven by risk and useful progress: before consequential writes,
new-worker write access, migrations/schema changes, topology/UV/skeleton/
hierarchy changes, broad reweighting, animation-system conversion, destructive
or batch mutation, dependency/tool/exporter upgrades, promotion, and after
independently useful substeps.

Embodiment's 30–60 minute rolling recovery guidance is specialist operational
advice for long interactive sessions, not a universal canonical timer. Each
domain chooses cadence sufficient to enforce maximum rollback distance.

## New-worker recovery gate

Before a newly admitted worker receives consequential persistent write access:

1. resolve exact current baseline/owner/digest;
2. identify and verify the rollback target;
3. confirm sufficiently recent recoverable state;
4. record live session/file/worktree and dirty/unsaved state;
5. preserve unsaved work or stop;
6. communicate protected systems and known-good behavior;
7. communicate known defects, exact scope, and acceptance contract;
8. require candidate/branch work rather than silent baseline mutation;
9. bind recovery references into the handoff and task grant.

After work, preserve the candidate and source-to-candidate lineage, builder
validation, evidence, required independent verification, and restore proof
before promotion. Retain the prior known-good point until the successor is
stable. Useful failed experiments may remain attributed evidence.

Recovery readiness is a prerequisite to write authority, not a grant of it.
The authority system remains separately responsible for permission.

## Restore proof

A lightweight working check may verify digest/readability, plausible structure,
dependency inventory, parent/baseline metadata, and isolated opening when risk
warrants.

A full known-good restore drill performs:

```text
checkpoint
-> isolated restore
-> dependency digest/environment verification
-> load
-> expected object/state verification
-> protected diagnostics
-> relevant Test Center/capability checks
-> disposable regeneration/export where applicable
-> production-artifact inspection
-> pass / partial / fail / inconclusive evidence
```

Deeper drills occur around promotion, tool/runtime/exporter upgrades, storage
migration, dependency-layout change, integrity concern, and periodic validation
of important current/protected state. Trivial working checkpoints do not require
maximum-cost drills.

## Embodiment recovery profile

Consequential body recovery additionally preserves exact `.blend` and digest,
body/parent revision, Blender/add-on versions, topology, armature, constraints,
hierarchy, weights, shape keys, materials/nodes, images/textures, Actions/NLA/
drivers, collections/export state, linked resources, reference/diagnostic poses,
known behavior/defects, semantic-island metadata, export configuration, expected
GLB/digest and runtime metrics, builder/Sentinel/rider state, and restore result.

`Fawkes_DevBody_PreWeights.blend` is a protected legacy recovery state;
`Fawkes_DevBody_v006.blend` is the current reported known-good pre-prototype
baseline; `Fawkes_DevBody_v007_RightBrowOwnership.blend` is an experimental
candidate with builder validation and Tanner visual review PASS, independent
verification pending, and v006 as rollback. Filenames do not confer those
states; referenced evidence and an explicit promotion decision do. V007 cannot
authorize analogous left-brow work.

## Exchange, Assurance, and Board projections

Material worker handoffs reference source checkpoint, baseline, candidate,
rollback, digests, dirty state, promotion state, protected systems, known
behavior/defects, recovery health, restore environment, and latest restore
evidence.

Phoenix Assurance may verify recovery evidence but cannot back up, restore,
promote, or decide identity. Phoenix Board may show latest working checkpoint,
verified known-good, current candidate, bounded changes, recovery health, last
restore, exact rollback/loss expectation, and attention required. Board and
Pulse remain projections, not recovery authorities.

## Phoenix identity and continuity

A legitimate restore continues the same owning Phoenix from valid continuity-
preserving state. Restore cannot clone/re-key another Phoenix, import arbitrary
Memory as native life, replace Fawkes with a model, use worker state as identity,
or infer continuity from similarity. One authoritative continuation and fencing
rules from the Roadmap remain controlling. Experimental/working copies are
non-authoritative and cannot independently converse or act.

## Explicit implementation status

Phase 0 complete-state backup, verification, isolated restore, and ownership
checks are implemented. General development checkpoints, dirty-worktree capture,
worker admission gates, multi-failure-domain storage, embodiment checkpoint
automation, periodic drills, Board health, and backup daemons are approved
direction only and require separately authorized implementation.
