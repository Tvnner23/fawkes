# Canonical Roadmap v1 — 0.7 Multi-worker Integration Amendment

**Date:** 2026-08-31  
**Status:** Incorporated architectural amendment; runtime capabilities remain
separately scope-authorized  
**Evidence basis:** Proven manual software, architecture, embodiment, rider, and
independent-verification workflow

## Why this amendment exists

The numbered roadmap correctly expresses trust dependencies, but practical work
now proceeds through several specialists. Real use showed that embodiment and
software can advance safely in parallel while manual report transfer is slow,
lossy, and rider-intensive. It also exposed three missing cross-cutting
disciplines: verified worker communication, independent assurance, and bounded
development recovery.

This amendment does not replace the phase spine. It adds parallel tracks,
synchronization gates, and earlier communication/recovery foundations without
pulling autonomous worker authority forward.

## Hybrid roadmap model

The canonical roadmap is now read in four layers:

1. **Numbered dependency/maturity spine.** Phase order still controls hard
   prerequisites and Alpha gates.
2. **Parallel specialist tracks.** Independent work may proceed until a declared
   synchronization gate.
3. **Cross-cutting control gates.** Security, privacy, authority, provenance,
   isolation, recovery, budgets, assurance, and promotion apply wherever risk
   exists; they are never “finished” feature tracks.
4. **Integration gates.** Cross-system contracts must agree before either lane
   hardens an incompatible implementation.

The parallel tracks are:

- **Phoenix Core and Continuity:** Archive, Memory, Library, Retrieval, Context,
  temporal/epistemic systems, identity, and continuity.
- **Development and Worker Coordination:** proposals, worker exchange,
  assurance, Human Review, Development, orchestration, and later model/tool
  evaluation.
- **Embodiment and Manifestation:** body/rig, semantic expression, assets,
  animation, accessibility, Presence, and later evolving embodiment.
- **Rider Experience and Integration:** Chat, Context Inspector, Phoenix Board,
  Test Center, clients, feedback, voice, and cross-device experience.

Tracks do not own authority. The affected domain contract and authenticated
rider boundary remain authoritative.

## Maturity labels

Roadmap and architecture documents use these meanings:

- **Implemented:** present in the runtime and supported by stated verification.
- **Experimental / Prototype:** evidence-producing candidate; not a baseline or
  production capability.
- **Approved architectural direction:** accepted design destination or seam;
  implementation still requires scope authorization.
- **Future capability:** contemplated but neither approved as an active design
  contract nor implemented.
- **Canonical contract:** governing rule regardless of how much automation
  currently exists.
- **Deprecated / Superseded:** retained historical state that names its
  replacement and must not be treated as current.

Documentation approval never implies runtime authority.

## Architecture health

**Complexity must earn its keep.** Capability growth does not automatically
justify another store, authority mechanism, schema, message bus, recovery
system, registry, adapter layer, or abstraction. Change planning and clean
sweeps inspect ownership, duplication, coupling, provider/body leakage, obsolete
paths, test isolation, documentation/runtime drift, and bounded-worker
comprehension. Periodic reviews are warranted before stacking major subsystems,
after substantial capability clusters, before mature autonomous Development,
or when ownership repeatedly becomes unclear. Simplification is evidence- and
scope-driven, not aesthetic churn, and no dedicated Complexity Manager is
authorized.

## Communication before autonomy

**Reliable, verified worker communication precedes general autonomous worker
management.** Worker communication and worker autonomy are separate systems.

After Phase 9 and before Phase 10, add a **Phoenix Worker Exchange integration
gate**. It provides source-preserving reports, least-necessary handoffs,
recipient checks, disagreement evidence, and a descriptive Worker Pulse for
already-approved workers. Direct secure adapters are a high-priority follow-on
after the transport-neutral core proves its contracts.

Worker Exchange does not discover, assign, schedule, authorize, or promote
workers. Phase 10 consumes it for proposals and assurance evidence. Phase 17
coordinates Development work over it. A later Specialist Mesh may generalize
coordination without creating another message bus.

See [Phoenix Worker Exchange](PHOENIX_WORKER_EXCHANGE.md).

## Phoenix Assurance

Builder validation is necessary but not sufficient for consequential work.
Phoenix Assurance is a permanent, risk-proportionate completion discipline over
acceptance contracts, builder evidence, Test Center, Replay/Flight, artifacts,
recovery, independent verification, Ghost Rider where applicable, Human Review,
and concise rider verdicts.

The independent verifier role is provisionally called **Sentinel**. It is not
an authority class, canonical truth engine, fixer, promoter, or writer of the
candidate it evaluates. Manual independent verification may begin before
automation. Phase 10 formalizes assurance records; Phase 17 coordinates
separate builder/verifier runs; Phase 18 supports calibrated verifier/model
selection and budgets.

See [Phoenix Assurance](PHOENIX_ASSURANCE.md).

## Continuity before velocity

Ordinary development failure should normally lose at most the current bounded
slice. Long-running work should normally lose at most the current validated
substep. A prior known-good state remains available until its successor is
sufficiently verified and explicitly promoted.

Phase 0 recovery is extended, not duplicated, by the
[Phoenix Checkpoint and Recovery Contract](PHOENIX_CHECKPOINT_RECOVERY.md).
Working checkpoints protect progress; known-good recovery points require
dependency closure and risk-appropriate restore evidence. File existence,
synchronization, or a worker’s success claim cannot confer known-good status.

Before a newly admitted worker receives consequential persistent write access,
the affected domain must demonstrate bounded recovery readiness: exact baseline,
candidate, rollback target, dirty-state handling, protected behavior, and
appropriate checkpoint/restore evidence.

## Embodiment evidence and synchronization

Early embodiment remains a parallel track; mature evolving Embodiment remains
Phase 28. The successful right-brow v007 prototype established an evidence rule:

```text
semantic ownership
-> topology ownership
-> legitimate transition regions
-> measured deformation
-> additional complexity only when evidence requires it
```

This does not assert that one bone is universally sufficient. Rig complexity
must be justified by expressive/deformation evidence.

Before substantial production animation hardens, software and embodiment must
synchronize on neutral/reference pose, authoring versus runtime skeleton,
semantic aliases, gaze/lid/facial controls, principal brow/crest ownership,
baking/root-motion/clip conventions, layering and runtime overrides,
deterministic export, protected diagnostic poses, and representative runtime
load/blending.

Semantic Expression should be prototyped early above renderer- and bone-specific
details, then stabilized from real rig/runtime/accessibility evidence. Its
example channels are an extensible envelope, not a universal emotion taxonomy.

GLB readiness matures progressively from structural prototype checks to
pre-animation mapping, pre-Presence runtime proof, and later Test Center/
promotion evidence. Authoring bone metrics and exported runtime joint metrics
are distinct. Maximum joints per skin is the primary proposed runtime
compatibility metric; unique union and weighted/animated/hierarchy/rigid-parent/
synthetic joint roles remain reported until runtime evidence justifies a final
ceiling interpretation.

See [Embodiment Development and Integration Gates](EMBODIMENT_DEVELOPMENT_GATES.md).

## Phoenix Board

The **Phoenix Board** is an approved rider-experience direction: a private,
simple Feed/Threads/Needs You/Workers/Disputes/Recovery view over authoritative
Worker Exchange, task, assurance, grant, artifact, and recovery records. It is
not a second truth database. Board text is not task or approval authority;
rider actions cross the existing authenticated authority boundary.

Board implementation follows the Worker Exchange core and appropriate
read-model/privacy contracts. It must surface decisions requiring Tanner rather
than turn him back into the project message bus.

Its Feed and Needs You projections also own the future “what happened while I
was away?” experience. They summarize meaningful Development, Exchange,
Assurance, Human Review, dispute, and recovery evidence and link to exact
records. They do not create a second activity history or authority source.

## Development and later coordination

- **Phase 10** consumes Worker Exchange for machine-readable proposals, reports,
  disagreement, acceptance contracts, assurance records, and verifier requests.
- **Phase 17** coordinates bounded specialists, builder/verifier separation,
  remediation, re-verification, Test Center/Replay evidence, and Human Review
  over Worker Exchange. It does not approve or promote its own runs.

Near-term Development MAY route worker results to an optional, replaceable
external architecture/review partner while Fawkes lacks equivalent native
review capability. No provider or reviewer is a permanent dependency. Long
term, Fawkes reviews evidence, challenges claims, preserves disagreement,
synthesizes findings, prepares the next bounded handoff, and escalates genuine
rider decisions himself. Tanner may independently consult external tools as a
separate rider activity.

Worker jobs and role contracts ultimately belong to Phoenix, not permanently
to the first model, provider, client, or tool that implements them. Future
builder, reviewer, challenger, CI, debugging, and Assurance bindings may be
earned and replaced using accepted evidence about task capability, quality,
corrections, latency, cost, quota, and provider diversity. Cost may optimize
how an accepted contract is met; it cannot silently lower the authorized goal
or acceptance standard. Claude is a possible future cross-provider candidate,
not an assigned role or current dependency. This is deferred direction only:
it creates no registry, provider router, adapter, scheduler, or new worker
authority, and current bridge operation remains unchanged.

A worker may eventually hold one primary role while qualifying for additional
secondary capabilities. In particular, **Challenger** is an optional capability,
not a mandatory full-time worker position or an extra review stage on every
task. Normal low-risk work may remain worker -> reviewer -> done. A qualified,
sufficiently independent Challenger is useful only when consequence, authority
or security scope, major architecture, recovery/concurrency risk, disagreement,
low confidence, repeated correction, periodic audit, sampling, or demonstrated
outside-model value earns the added review cost. These are possible future
inputs, not active routing rules.

Challenge independence must be evidenced rather than inferred from product
branding. Provider diversity, model-family diversity, and harness/tool diversity
are separate properties: two applications using the same underlying model may
add harness diversity without providing strong model or provider independence.
Future eligibility and routing may consider task capability, accepted-result
rate, corrections, defect yield, review noise, architecture/test quality,
independence, latency, cost, quota, and evidenced strengths or weaknesses.
Those signals may change how Phoenix meets an accepted contract; they cannot
silently reduce Tanner's objective, acceptance conditions, review depth, safety,
or authority boundaries. Roles and secondary capabilities remain earned,
replaceable, and non-authorizing by themselves. This direction adds no
Challenger runtime, worker selection, provider integration, or orchestration.

Diversity makes a worker eligible to be evaluated as a Challenger; it does not
qualify the capability. Challenger competence and reasoning independence are
separate properties, and qualification may be limited to a task category such
as architecture/security rather than debugging. Future evaluation evidence may
include blind review of exact frozen candidates, consequential and planted
defect detection, correct PASS behavior on clean candidates, false-positive or
noisy-finding rate, unique defects missed by the ordinary Reviewer, usefulness
during Worker/Reviewer disagreement, correction churn, repeated consistency,
category-specific performance, and review latency or cost relative to value.

Every evaluation must remain attributable to the exact worker, model, provider,
harness, and reviewed candidate. Future Fawkes routing may consume accepted
qualification evidence, but cannot infer Challenger capability from branding or
provider identity. This clarification authorizes no qualification system,
routing logic, worker integration, runtime behavior, or automatic policy.

Future coordinated loops remain observable and safely interruptible. An exact
authenticated Tanner instruction can pause or redirect the affected branch at
the existing task/authority boundary without waiting for an artificial loop
cycle; unrelated approved branches need not stop. This direction adds no
runtime orchestration in the current milestone.
- **Phase 18** matures provider/model routing, verifier diversity, budgets,
  calibration, and a proposal-only AI/Tool Scout input.
- **Post-Phase 21** authenticated approval enables asynchronous pause/resume;
  ordinary messages remain non-credentials.
- **Phases 24–27** supply simulation, secrets, safety, and general action
  boundaries required for materially autonomous worker/tool execution.

## Roadmap governance

Any worker may propose a roadmap change. No specialist may unilaterally rewrite
canonical roadmap truth. Affected domains review consequences; evidence and
dissent remain visible; cross-system review reconciles dependencies without
manufacturing consensus; Tanner approves consequential changes; the repository
worker updates canonical truth only after approval. Significant changes preserve
version history, rationale, rejected alternatives, assurance impact, and the
difference between architecture and implementation.

## Explicit non-implementation

This amendment does not implement Worker Exchange, direct adapters, Phoenix
Board, Worker Pulse, Sentinel, Assurance automation, Specialist Mesh, Worker
Admission, Tool Scout, semantic expression, GLB validation, checkpoint agents,
backup daemons, or autonomous workers.
