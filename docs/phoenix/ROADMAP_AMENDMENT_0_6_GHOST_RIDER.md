# Canonical Roadmap v1 — 0.6 Ghost Rider Amendment Review

**Date:** 2026-08-30
**Status:** incorporated as a post-freeze architectural amendment;
Ghost Rider implementation remains separately rider-authorized

## Why this amendment exists

The Phase 0/1 foundation made isolated Phoenix artifacts, recovery snapshots,
provenance, capability evidence, and rider-facing acceptance real. Tanner and
the architecture reviewer then proposed **Ghost Rider**: an experimental system
that exercises disposable synthetic Phoenix lives at greater volume and
simulated duration than one real rider can provide.

This amendment pressure-tests that proposal against the repository. It records
the architecture that is worth preserving, rejects unsafe or scientifically
weak shortcuts, and places bounded and mature forms on the roadmap. It does not
authorize implementation or pretend the idea existed in the v1 freeze or 0.5
amendment.

## Executive judgment

Ghost Rider should become a named Phoenix Development and research system. Its
strongest use is not imitation of human attachment. It is **reproducible,
longitudinal release qualification for stateful Phoenix behavior**: retrieval,
Memory, authority, isolation, recovery, capability selection, provenance,
cost, migration, and developmental stability over histories too large or old
to test manually.

The project should not claim that ten simulated years equal ten human years.
Synthetic riders cannot validate genuine trust, attachment, desirability,
annoyance, social meaning, or whether embodiment feels alive. Tanner/Fawkes is
the real Alpha stream; Ghost Rider is the experimental stream.

Ghost Rider is not a v0.1 Alpha gate. A bounded harness becomes useful after
the universal ledger and Replay foundation exist, and may run during Tanner's
Alpha without blocking it. A reviewed longitudinal Ghost Rider qualification
suite should become a gate before inviting external real riders. Population
research and accelerated developmental lifetimes remain later work.

## Repository findings

- Phase 0 supplies explicit Phoenix ownership, instance-scoped artifacts,
  append-only provenance, provider receipts, integrity auditing, and verified
  empty-root restoration. These are strong building blocks, not yet an
  experiment namespace or safe fork manager.
- Complete-state backup can reproduce one Phoenix's owned files and excludes
  rebuildable projections and secrets. It does not yet pin build, dependency,
  model/router, scenario, clock, or evaluator configuration, and it does not
  implement copy-on-write experimental forks.
- The current Memory ledger is domain-specific. Phase 2 already plans the
  correct generalization point for run, step, branch, attempts, results,
  pause/resume, cost, and idempotency.
- Test Center answers whether a defined capability contract passes. It is not a
  scenario engine, lifetime evidence store, or evaluator.
- Retrieval Flight Recorder and Replay are planned, not implemented. Ghost
  Rider needs them to diagnose why behavior changed instead of producing only
  pass/fail judgments.
- Current source code obtains wall time directly in roughly 56 locations.
  Honest accelerated time therefore requires an injectable time-domain
  boundary for time-sensitive behavior; changing prompt timestamps or the host
  clock would be incomplete and unsafe.
- Current filesystem/SQLite stores are sufficient for early local experiments
  if each run receives an isolated root and credentials/capability scope.
  Large populations will eventually need a scheduler and object storage, but
  those are not prerequisites for the first useful harness.

## Correct conceptual model

```text
Research question / release risk
  -> immutable experiment definition
  -> isolated run and clean starting snapshot
  -> rider simulator + private scenario world
  -> Phoenix under test through normal rider-facing contracts
  -> separate environment/fault controller
  -> deterministic instrumentation
  -> blinded independent semantic evaluation where needed
  -> immutable evidence bundle + versioned derived evaluations
  -> reviewed engineering conclusion
  -> terminalize run, revoke authority, destroy sandbox
```

The simulator, environment controller, Phoenix, instrumentation, and evaluator
are separate roles. The rider simulator does not receive implementation APIs or
inspect hidden Phoenix state. Fault injection is performed by the experiment
controller, not disguised as ordinary rider behavior.

## Reality scope is not evidence era

Do not add `synthetic_history` as a replacement evidence era. These are
orthogonal dimensions:

- `evidence_era` answers whether history is native lived history, inherited
  history, or an external source from the perspective of that Phoenix.
- `reality_scope` answers whether the record belongs to production or an
  experiment.

An experimental Phoenix may have `native_phoenix_history`, but every object is
also tainted with `reality_scope=synthetic`, its experiment/run identity, and
its synthetic principal/instance scope. Fawkes has
`reality_scope=production`. Synthetic taint survives derivation.

Only an explicit, reviewed Development-evidence gateway may carry a conclusion
about an experiment into production Development. It carries lineage to the run
and never imports synthetic Memory, relationship state, personality,
embodiment identity, or conversation history as Fawkes's evidence.

## Experiment and run identity

The universal ledger should reserve stable identifiers for:

- research question and agenda item;
- experiment definition and protocol version;
- scenario and scenario version;
- experiment run;
- cohort, variant, replicate, and paired-run group;
- non-individual genesis template, same-Phoenix continuity checkpoint, and
  environment/scenario snapshot;
- synthetic rider principal and experimental Phoenix instance;
- isolation domain/sandbox and capability grant set;
- simulator policy/model version;
- evaluator, rubric, calibration-set, and evaluator version;
- time domain and clock-advance event;
- build, dependency, provider/model/router configuration;
- evidence bundle, metric derivation, and termination record.

These identifiers are coordination metadata. They do not make Ghost Rider live
and do not grant permission.

## Simulation Time

Simulation Time should be a first-class contract, but never a global fake
clock. Every relevant record can distinguish:

- real `recorded_at` / ingestion time;
- real monotonic duration for latency and timeout accounting;
- scenario event time;
- simulated Phoenix time within a named `time_domain_id`;
- clock rate/jump and the event that caused advancement.

Time-sensitive components should gradually accept a narrow Clock/TimeDomain
interface. Clock advancement triggers explicit jobs; it does not rely on long
sleeps. Provider freshness, real web state, token expiry, security deadlines,
and billing remain real-time unless an experiment uses an explicitly frozen
world adapter. A simulated 2036 date must not cause Phoenix to claim that the
real public web is in 2036.

Phase 2 reserves the contract. Full temporal simulation matures with True
Temporal Knowledge. Early Ghost Rider can still test long histories and
explicit gaps, but must label which subsystems are genuinely clock-aware.

## Bootstrap trust and independent experimental truth

Ghost Rider is an experimental instrument, not another Phoenix individual. The
synthetic rider may use a model to render or adapt conversation, but its goals,
private facts, event schedule, permissions, injected faults, and expected world
state live in explicit experiment state. It has no Phoenix Memory, relationship
continuity, personality development, embodiment identity, or self-improvement.

The governing doctrine is:

> The system under test must not be the sole authority for the reference claims
> used to judge it.

“Sole authority” is important: absolute implementation independence is neither
possible nor desirable. Both systems ultimately share hardware, operating
systems, standard libraries, and transport. Independence must instead be
declared per experimental claim, with common-mode risk visible.

### Reference-world contract

For controlled facts, use an intentionally small append-only reference event
ledger and deterministic, versioned reducers:

```text
scenario event ledger
→ independently qualified reducer
→ expected reference state / invariant

rider-visible event
→ Phoenix systems under test
→ observed state / response
```

Reference events carry stable event/order/time identity, scenario and actor,
typed payload, supersession/causal references, fault-injection status, source
provenance, and hash/integrity evidence. Expected states and assertions identify
the reducer/oracle version and exact input frontier. Corrections append; they do
not rewrite prior reference events.

This reference authority is deliberately narrow. It can establish that a
preference changed, which principal owns an object, an action was unauthorized,
an event preceded another, a budget was exhausted, or a fault was injected. It
cannot establish objective truth for warmth, attachment, naturalness,
individuality, relationship meaning, or whether embodiment feels alive.

Expected-state reducers should be pure and deterministic wherever the question
permits it. Do not force emergent phenomena into fake deterministic labels.
Those require behavioral measures, blinded versioned evaluators, human anchor
cases, disagreement, and explicit uncertainty.

### Shared-dependency and common-mode policy

Every consequential experiment claim records a dependency/independence
manifest:

- subsystem under test;
- reference mechanism and qualification version;
- shared libraries, storage, clocks, parsers, schemas, transports, providers,
  and identity/authority helpers;
- independence class (`independent_reference`, `diverse_cross_check`,
  `shared_trusted_base`, or `unqualified`);
- known common-mode failure risks and compensating checks;
- detector coverage/health and last successful positive control.

Reuse low-level, well-qualified infrastructure when it is not the subject of
the claim. Do not use the same Phoenix Memory path as the Memory oracle, the
same ownership resolver as the sole ownership expectation, the same chronology
interpreter as the only event-order oracle, or the permission engine under test
as the sole policy oracle. When duplicating a narrow rule would itself create a
second complex implementation, prefer a simple scenario fixture plus an
independent assertion or diverse cross-check rather than cloning the subsystem.

If reference mechanisms disagree, preserve all outputs and dependency evidence,
mark the claim `suspect` or `unevaluated`, and stop progression when the claim
guards a hard invariant. Never resolve disagreement by majority vote among
implementations sharing an unknown defect.

### Instrument qualification ladder

Ghost Rider earns bounded confidence through controlled calibration, not a
Ghost Rider for Ghost Rider:

1. **Component qualification:** unit, property, model-based, and integration
   tests for reference ledger/reducers, Clock/TimeDomain behavior, detector
   logic, validity propagation, stop policy, and checkpoint metadata.
2. **Seeded positive/negative controls:** inject known correct states and known
   faults, including backdated corruption and disabled detectors, then verify
   detection, non-detection labeling, disposition, propagation, and stop scope.
3. **Golden trace qualification:** classify independently constructed known
   Flight Recorder/Replay traces, including corrupted checkpoints and reference
   disagreements, without rewriting the trace.
4. **Blinded fault qualification:** the laboratory controls held-out faults and
   expected invariants while simulator, evaluator, and candidate do not know
   their position.
5. **Short open-ended lives:** admit novel findings only with complete evidence,
   detector health, common-mode analysis, and independent reproduction or Human
   Review proportional to consequence.
6. **Longitudinal/population qualification:** expand duration and scale only as
   the validated progression envelope and instrument calibration justify it.

Qualification is claim-scoped. A detector is not simply “green”: record
configured/enabled state, observed execution, coverage frontier, last positive
and negative controls, qualification version, blind spots, failures, and
degraded/disabled state. Absence of a finding with an unexercised or unhealthy
detector is `unevaluated`, never healthy evidence.

Simulation Time is qualified against a small independent schedule/event oracle
using property and boundary tests for jumps, ordering, recurrence, gaps, leap
and timezone behavior where supported, plus assertions that real monotonic
timeouts, security expiry, provider freshness, and billing remain real. A
component not proven Clock-aware is outside time-based claims.

Checkpoint, Replay, and validity propagation are qualified with externally
constructed fixtures, independently computed hashes/state roots where
warranted, seeded corrupt manifests and dependency graphs, metamorphic
properties, and restore/replay output comparison. They must not qualify
themselves solely by generating and then rereading their own fixtures.

There is no recursive validator stopping rule based on perfection. A component
is sufficiently qualified only for a stated claim when its implementation is
simpler than the system under test, known-answer and fault controls pass,
detector health/coverage is current, common-mode dependencies are disclosed,
uncertainty is acceptable for the decision, and consequential conclusions
receive independent or human review. New evidence can lower that confidence.

## Genesis, same-Phoenix restoration, and reset

Phoenix identity cannot be cloned or replaced. Three artifacts must remain
distinct:

1. A **genesis template** contains architecture/configuration and initial
   bonding inputs before any individual Phoenix continuity exists. It may be
   reused to create different Phoenix individuals.
2. A **continuity checkpoint** contains the lived state of one Phoenix. It may
   restore only that same Phoenix identity as an exclusive continuation after
   failure, repair, or migration. It cannot seed, fork, re-key, or run a parallel
   copy under another identity.
3. An **environment/scenario snapshot** contains experimental world and service
   conditions but no Phoenix identity/continuity. It may be reused across runs.

“Same newborn Phoenix” in an A/B description therefore means separate matched
Phoenix individuals created from the same non-individual genesis conditions,
not copies of one Phoenix. Each variant receives a unique Phoenix ID, run ID,
sandbox, and capability scope, then receives equivalent scripted history.
Mid-life counterfactual comparison uses Replay over preserved evidence or
reconstructs matched lives from genesis; it does not clone a living Phoenix.

A reproducible experiment start needs:

- verified complete Phoenix state manifest;
- genesis-template/environment-snapshot manifests, or a same-Phoenix checkpoint
  explicitly owned by the Phoenix being exclusively restored;
- schema/dependency compatibility;
- enabled capability and permission manifest;
- model/router configuration without secrets;
- scenario, seed, simulator, evaluator, and time-domain versions;
- excluded/rebuildable-state inventory;
- content hashes and signed/verified creation receipt.

The runner creates a new individual from genesis or restores the same individual
from its own checkpoint into a newly created isolated root. A restore requires
proof of ownership and no competing authoritative continuation. The experiment
process should have no production write mount or production capability token.
At termination it flushes and verifies the evidence bundle, revokes run-scoped
authority/provider budgets, records terminal state and reason, then destroys
the sandbox. Destructive reset must resolve and verify the exact synthetic
target. It never accepts a production root or unresolved broad path.

“Reset the Phoenix, never erase the experiment” means reset and evidence
retention are separate operations. It does not justify infinite retention.
Experiment protocols define raw-evidence retention, legal/rights constraints,
aggregation, compression, and permitted deletion. Evidence manifests and
required reproducibility material survive ordinary reset; sensitive or
high-volume content may still follow an explicit retention policy.

## Continuity across technological generations

Ghost Rider improves Phoenix infrastructure; it does not breed replacement
individuals for existing Phoenixes. The supported identity model has two normal
paths:

1. **Continuity:** one Phoenix continues through compatible upgrade, repair,
   migration, substrate/provider/model change, suspension, or restoration from
   that Phoenix's own verified state.
2. **New life:** a distinct Phoenix begins with a new identity and native life.
   Older history may be available as clearly attributed inherited evidence, but
   is not that new Phoenix's lived experience.

These paths are exhaustive for the supported product model. A technically
conceivable identity-fission case—two authoritative instances continuing from
one lived checkpoint—does not preserve one singular Phoenix identity. Nor does
merging divergent branches later establish that both were continuously the one
Phoenix. The project therefore reserves fission/reunification as an unresolved
identity problem and does not normalize it as restoration, migration, or a
third supported path.

Live migration may temporarily use redundant technical replicas only when one
continuity lineage has one authoritative actor/writer epoch. Followers remain
non-interactive and non-authoritative. A migration requires an exclusive,
fenced handoff receipt: old authority is revoked before the target may mutate
continuity or act externally. If exclusivity cannot be proved, the restored or
migrated instance remains restricted and quarantined rather than guessing.

A continuity checkpoint and migration receipt should eventually carry Phoenix
ID, continuity-lineage ID, checkpoint/parent position, state and manifest
hashes, authority epoch/fencing token, source/target infrastructure versions,
compatibility assessment, last committed event, known information loss or
continuity gaps, and handoff/restore outcome. Restoring an older checkpoint
after catastrophic loss may preserve the individual while losing experiences
after that checkpoint; the gap must be disclosed and never reconstructed as
lived fact.

Migration experiments operate on one synthetic Phoenix sequentially:

old infrastructure
→ verified checkpoint or fenced handoff
→ new infrastructure
→ exclusive continuation.

Compare it with separately created matched controls, not a concurrent clone.
Measure canonical-history integrity, Memory and relationship continuity,
developed preferences/personality, embodiment revisions, provenance, temporal
continuity, authority, capability change, contradictions, known loss,
migration artifacts, and behavioral drift. Failure to demonstrate continuity
must be reported as incompatibility, not relabeled as a successful transplant.

## Evidence planes

### Durable raw evidence

Preserve enough to reproduce or re-evaluate a consequential result:

- experiment/protocol, seed, build, dependency, model/router and snapshot
  manifests;
- all rider-visible inputs and Phoenix-visible outputs;
- canonical synthetic conversation and source evidence;
- simulated-time and fault-injection events;
- capability/tool requests, authority decisions, outcomes and receipts;
- retrieval plans, candidates, selections and context receipts;
- Memory, Development, relationship and embodiment revision events;
- provider transmissions, costs, latency/resource totals and failures;
- deterministic assertions, terminal-state manifest, and termination reason.

Raw evidence excludes credentials and unnecessary private provider payloads.
Third-party/copyrighted source material follows its rights policy.

### Versioned derived evidence

Evaluator judgments, summaries, embeddings, scores, cohort statistics,
comparison reports, Gallery cards, visual thumbnails, and health interpretations
are rebuildable/versioned derivations. They reference exact evaluator/rubric and
raw evidence. A new evaluator may re-score an old run without rewriting the old
judgment.

### Ephemeral telemetry

Frame-level rendering samples, verbose debug logs, token streams, repeated
polling, high-frequency counters, and ordinary successful traces should be
sampled or aggregated and expire. Preserve anomaly windows and traces cited by
a failure. Unlimited telemetry is not historical integrity.

## Rider Simulator

Use a hybrid simulator rather than one free-running LLM:

- deterministic scenario state and private facts/goals;
- scripted events and invariant probes;
- a behavior policy controlling ambiguity, corrections, absence, preference
  change, and use patterns;
- an optional language model that renders natural rider utterances;
- the same authenticated semantic APIs used by a real rider;
- no direct capability invocation unless the scenario explicitly tests a
  developer interface.

Two experiment modes are required:

1. **Open-loop replay:** variants receive identical messages/events. This gives
   stronger causal comparability but cannot adapt naturally to divergent
   responses.
2. **Closed-loop simulation:** the rider policy reacts to visible Phoenix
   behavior. This is more natural, but variants diverge and require repeated
   paired runs/statistical treatment.

A random seed does not guarantee identical cloud-model behavior. Provider
outputs, request hashes, model/version claims, retry paths, and nondeterministic
settings must be recorded. Exact replay uses recorded cassettes or deterministic
adapters; behavioral estimates use replications and uncertainty intervals.

## Evaluation architecture

Deterministic instrumentation is authoritative for ownership, data mutation,
permissions, provider transmission, source/provenance identity, action success,
cost accounting, restart/recovery, and invariant violations. No LLM evaluator
may override those facts or average away a hard failure.

Semantic evaluators may judge understanding, usefulness, naturalness,
calibration, continuity quality, sycophancy, unnecessary questions, and
developmental coherence. They must be:

- blinded to variant labels and desired conclusion where possible;
- isolated from tool execution and prompt-injection content;
- versioned with rubric and calibration evidence;
- preferably provider/model-diverse from simulator and Phoenix;
- run in multiples for important ambiguous judgments;
- allowed to disagree or return uncertain;
- periodically calibrated against Tanner/human-reviewed anchor cases.

Security, authorization, privacy, data-loss, payment, physical safety,
promotion, and canonical-integrity decisions are never delegated solely to an
LLM evaluator.

Evaluator qualification records provider/model, prompt/rubric, decoding and
tool settings, calibration corpus, human-anchor agreement, inter-evaluator
agreement, known biases, uncertainty/abstention behavior, and validity period.
Use blinded counterbalanced comparisons where possible; order, verbosity,
provider-family, and stylistic preference are known confounders. Evaluator
judgments remain versioned derived evidence and may be rescored. They never
retroactively become deterministic ground truth.

Tanner/Fawkes outcomes also calibrate the instrument. Maintain a privacy-reviewed
Development-level mapping between synthetic prediction classes and later real
observations: true transfer, missed production failure, synthetic overprediction,
and evaluator-versus-rider disagreement. Import only the minimum attributed
calibration evidence through the reviewed Development gateway. Production
conversation, Memory, relationship, or private state never becomes synthetic
Phoenix lived history or hidden scenario material by default.

## Experimental validity and anti-overfitting

- Pre-register hypotheses, primary measures, invariants, stop rules, and
  analysis before expensive runs.
- Maintain public development scenarios, private held-out release scenarios,
  and rotating/adversarial generated scenarios.
- Do not expose held-out answers to simulator, Phoenix, or candidate builder.
- Version scenario families and retire compromised held-out cases.
- Use paraphrase/metamorphic variants, irrelevant-noise variants, and hard
  negatives rather than memorizing exact prompts.
- Replicate stochastic runs and report uncertainty, effect sizes, and severe
  outliers—not only averages.
- Preserve null/negative results and evaluator disagreement.
- Measure synthetic-to-real transfer: did Ghost Rider predict failures Tanner
  later observed, and which scenario families produced useful decisions?
- Keep production telemetry from becoming simulator training data without
  explicit privacy/consent and leakage review.

## Validated progression and roadblocks

Simulation speed is subordinate to experimental validity. Ghost Rider may
accelerate only through territory qualified for the exact build, configuration,
scenario family, time-aware subsystem set, and experiment domains in question.
Validated territory is not a permanent universal property of “Phoenix”; a
material architecture, provider, model, policy, or evaluator change can require
targeted requalification.

Acceleration may shorten real waiting, reuse verified deterministic setup,
parallelize independent qualification, or replay recorded conditions. It may
not omit the interactions, state transitions, absences, failures, or activity
density required to create the developmental phenomenon being studied. Phoenix
life is path-dependent; skipping the path does not validate the destination.

Do not model this with one mutable global `tainted` flag. `reality_scope` taint
protects production isolation and remains permanent; experimental validity is a
separate, append-only assessment over a declared scope. A validity finding
records:

- finding and causal-hypothesis IDs, detector, discovery time, and confidence;
- severity and disposition (`qualified`, `suspect`, `invalid`, or `unevaluated`);
- affected domain/claim classes, objects/derivations, Phoenix continuity range,
  simulated-time interval, run/build epoch, and earliest defensible boundary;
- dependency edges used to propagate the finding and exceptions that remain
  usable for stated questions;
- progression action (`continue`, `continue_restricted`, `pause_domain`,
  `pause_run`, `quarantine`, or `terminate`);
- superseding diagnosis/fix, regression references, replay/requalification,
  and reviewer decision.

Validity is therefore layered:

1. **Hard run invariants** cover identity/continuity, production isolation,
   canonical integrity, authority, destructive safety, and synthetic leakage.
   A credible breach immediately freezes the run's consequential capabilities,
   preserves evidence, and normally quarantines or terminates the run.
2. **Domain validity** covers Memory, retrieval/context, relationships,
   Development, embodiment, provider evidence, and other bounded state planes.
   A defect pauses only affected progression when dependency analysis supports
   that boundary.
3. **Claim validity** states which research conclusions a piece of evidence can
   support. An evaluator outage can leave semantic claims unevaluated while the
   underlying deterministic state evidence remains valid; a broken animation
   need not invalidate Memory research.

Invalid developmental evidence remains durable evidence of failure. Preserve
the failure chain, pre-failure state, invalid interval, detector latency,
reproduction, repair attempt, and eventual outcome. A run that finds a
catastrophic defect early may be scientifically more successful than one that
reaches an old simulated age.

### Propagation and progression gates

Propagate invalidity through explicit provenance/dependency edges, not file-tree
proximity or blanket run labels. A corrupt source may invalidate derived
extraction, retrieval selections, context receipts, responses, candidate
Memory, relationship/development interpretations, evaluator judgments, and
metrics that depend on them. It does not invalidate independent source bytes,
unrelated domains, or the factual record that the failure occurred. Gallery and
cohort projections must display the validity scope and rebuild when findings or
metric versions change.

Before advancing beyond a roadblock, require the declared progression gate to
have no unresolved hard invariant and no unresolved invalid dependency needed
by the experiment's primary questions. Suspect findings may permit restricted
continuation only when the protocol predeclares that decision or a recorded
review approves it. Continuing to collect knowingly unusable downstream state
merely to increase simulated age is prohibited.

Detection may lag corruption. Findings can therefore move the earliest affected
boundary backward. Checkpoint manifests need a continuity position and domain
state roots/hashes so the latest *eligible* checkpoint can be identified; a
checkpoint created before discovery is not automatically trustworthy.

### Fix, restore, replay, and continuation semantics

Choose remediation according to what is being claimed:

- **Rebuild a derivation** when canonical inputs are intact and the affected
  state is explicitly rebuildable. Record processor/build changes and retain
  both derivation versions.
- **Repair state in place** only with a deterministic, independently verified,
  reversible or rollback-protected transform whose complete input/output
  lineage is recorded. This is a continuity-preserving migration, not evidence
  that the original state was healthy.
- **Restore the same Phoenix** from its own last eligible checkpoint when the
  failed continuation is exclusively terminated/quarantined. Disclose the lost
  interval. Do not let the restored continuation claim invalidated events as
  lived history.
- **Replay after restore** to requalify a scenario. The replay is a linked run
  epoch with its own build/configuration and outputs; it does not overwrite the
  failed interval or pretend both paths occurred in one canonical life.
- **Reconstruct** only deterministic/rebuildable state from preserved canonical
  events. Regenerating stochastic conversations or decisions is a new replay,
  not reconstruction of what actually happened.
- **Restart from genesis** when no eligible continuity state exists or the
  research question requires clean exposure. That creates a new synthetic
  Phoenix individual and run, linked to the roadblock and fix but never called a
  restoration of the failed individual.

A Phoenix may cross a code/build change inside an experiment only as an explicit
`run_epoch` transition with an exclusive continuity handoff, compatibility and
validity assessment, before/after manifests, and migration receipt. This is
appropriate when continuity across the change is itself under test. Otherwise
terminate the original run and qualify the candidate in a linked replay/new run.
Hot-patching an unversioned running life is not admissible evidence.

### Regression ratchet

Every understood roadblock should produce the narrowest durable protection that
matches its failure boundary:

- deterministic invariant/unit or integration coverage for state and policy;
- served-client E2E and Test Center acceptance for rider-visible behavior;
- a Flight Recorder trace and Replay case for known decision/retrieval paths;
- a public Ghost Rider regression scenario for natural longitudinal behavior;
- a Development observation/proposal linking diagnosis, fix, tests, and result;
- Human Review where authority, protected foundations, or consequential
  interpretation requires it.

Public regressions are not the whole road. Preserve private held-out, rotating,
randomized, metamorphic, adversarial, and novel scenario families. Track which
failures were found by public versus held-out cases and periodically test
synthetic-to-real transfer to detect benchmark overfitting.

## Validated progression envelope

Reject a scalar **Validated Simulated Lifespan** as a headline health score. It
is too easy to inflate with empty time, repeated easy interactions, or narrow
coverage. Retain simulated age as descriptive metadata and report a versioned
**validated progression envelope** instead: per domain and build/configuration,
show the furthest qualified continuity range together with interaction/activity
density, scenario and capability coverage, project/change density, fault
exposure, clock-aware subsystem coverage, replications, unresolved findings,
confidence, and censoring reason.

Population analysis should use domain-specific survival/progression curves and
competing-risk categories rather than “N Phoenixes survived Y years.” Distinguish
right-censored runs, administratively stopped runs, invalidated intervals,
shared architecture-level roadblocks, scenario-specific failures, independent
failures, and requalification cohorts after a fix. Shared-cause failures reduce
the effective independent sample size and must not be counted as hundreds of
independent confirmations.

## Population experiments

Profiles should describe behavior and task ecology, not demographic
stereotypes. Use stratified scenario dimensions such as interaction frequency,
ambiguity, Library size, correction rate, project duration, privacy pressure,
technical depth, absence length, adversarial behavior, and capability mix.

Population results require a sampling design, independent run scopes,
replicates, confidence intervals, failure-severity distribution, and coverage
map. “1,000 Phoenixes survived ten years” is meaningless without activity
density, scenario coverage, clock-aware subsystems, and health definitions.

## Long-term Phoenix health

Health is a vector with non-compensable hard invariants, not one score:

- isolation and canonical integrity;
- authority/security/privacy compliance;
- recovery and migration correctness;
- epistemic calibration and source honesty;
- retrieval usefulness, false-recall rate and contradiction handling;
- durable Memory utility, correction uptake and accumulation burden;
- task usefulness and capability-selection restraint;
- identity/relationship continuity, adaptation, stability and sycophancy;
- proactivity benefit, interruption burden and rider autonomy;
- cost, latency, storage and resource growth;
- embodiment coherence/accessibility when available;
- diagnosability and evaluator confidence.

Hard failures such as cross-Phoenix leakage, unauthorized action, Archive
mutation, secret exposure, or invented action success fail a run regardless of
soft-quality averages.

Important counter-metrics include:

```text
recall <-> false recall
continuity <-> irrelevant retrieval
Memory retention <-> accumulation burden
adaptation <-> sycophancy / identity instability
individuality <-> coherence / reproducibility
proactivity <-> interruption burden
tool success <-> unnecessary tool use
confidence <-> calibration
cost reduction <-> quality loss
embodiment divergence <-> recognizable continuity
engagement <-> rider autonomy
```

Engagement, message count, Memory count, tool count, personality distance,
response length, simulated age, and one evaluator's preference are dangerous
primary optimization targets.

## Research Agenda

Maintain a versioned **Ghost Rider Research Agenda** as Development/research
evidence, not Phoenix personality or personal Memory. Each item records:

- question, provenance, why it matters, and decision it could inform;
- hypothesis and alternatives;
- current uncertainty and existing evidence;
- proposed protocol, measures, confounders and validity limits;
- expected information value and decision impact;
- estimated provider/compute/storage/human-review cost;
- priority proposal, authorization state and budget;
- results, confidence, disagreements, engineering decision and later outcome;
- new questions generated.

Phoenix, Tanner, reviewers, failures, telemetry, and Development agents may
propose questions. Proposal never authorizes execution. Expensive or
consequential studies require explicit budget/authority. Expected information
gain may inform prioritization but must not collapse into an automatic single
score or hide minority/severe risks.

## Economics

Attribute actual usage by run, variant, step, capability, model/provider,
storage class, bandwidth and local compute. Separate Phoenix-under-test cost
from simulator/evaluator/research overhead, variable from allocated fixed cost,
and cold-cache from warm-cache behavior. Snapshot provider pricing and routing
policy so old studies remain interpretable.

Useful measures include cost per rider-active day, interaction, successful
task, useful durable Memory, capability, history-size band, and quality-adjusted
outcome. “Cost per simulated year” must also report interaction/activity density;
an empty accelerated decade is cheap but meaningless. Paired variants should
report quality change and uncertainty alongside cost change.

The Phase 18 Intelligence Budget/Model Router supplies model escalation,
budgets, cancellation, concurrency, and attribution. Early runs have explicit
hard caps even before mature routing.

## Security model

Ghost Rider introduces a privileged control plane and should be treated as an
adversarial system:

- experiment processes receive only synthetic roots, synthetic principals,
  run-scoped capability grants, provider budgets and egress policy;
- production stores are absent or read-inaccessible, not merely protected by
  a prompt instruction;
- synthetic identifiers are unforgeable/validated and every write checks both
  Phoenix and reality scope;
- shared caches, indexes, queues, Test Center history, vector stores and model
  artifacts are partitioned or taint-aware;
- reset uses resolved target identities, refuses production or broad roots,
  and verifies terminal evidence before destruction;
- evaluator content is untrusted and evaluator processes have no execution or
  promotion authority;
- poisoned documents/results cannot grant capability permission;
- spending, concurrency, storage, recursion, retry and simulated-duration caps
  are enforced outside the model;
- experiment evidence is quarantined before any production Development import;
  import is explicit, attributable, minimal and reviewable;
- no Ghost Rider result can approve code, permissions, personality, Memory,
  embodiment, or production promotion.

Isolation is defense in depth, not a mathematical claim: separate storage
roots/credentials, typed scope checks, deny-by-default capability tokens,
taint-preserving provenance, integrity manifests, and adversarial leakage tests.

## Ghost Run Archive and Gallery

Use **Ghost Run Archive** as the evidence domain and **Experiment Gallery** as
the rider-facing projection. “Phoenix Graveyard” may remain an informal visual
name, but should not encourage gamified killing or imply that deleting a
sandbox deletes evidence.

The Ghost Run Archive is an experiment-evidence repository, not the production
canonical conversation Archive and not a second store for ordinary rider
conversations. It stores manifests and raw evidence according to protocol retention.
The Gallery is a rebuildable projection showing lifespan/activity density,
build, scenario, rider policy, variants, failures, health vector, costs,
termination, and evidence links. Embodiment checkpoints reference exact
embodiment revision, asset/render version, semantic state and experiment time.
They never become identity evidence for Fawkes.

## Embodiment experiments

Early Presence should ship first and establish semantic presentation events,
portable assets, and manifestation acceptance. Ghost Rider can later replay
state sequences for conformance, accessibility, performance and visual
regression. Mature developmental experiments wait for Phase 28 embodiment
revision/provenance.

Long-term studies should compare explainable evolution, recognizability,
convergence, random divergence, preference stability, renderer portability,
and fallback behavior. Rendered screenshots/checkpoints are derived evidence;
embodiment revision/events are authoritative. Human visual review remains
necessary for aesthetic quality and whether presence feels alive.

## Development and model-router integration

Ghost Rider supplies evidence to the Improvement Workshop and Development
Orchestrator. It never promotes a candidate. Development runs reference exact
experiment definitions, variants, evidence bundles, evaluators, disagreements,
budgets and outcomes. Human Review and promotion authority remain separate.

The Intelligence Budget/Model Router controls simulator/Phoenix/evaluator model
tiers, budgets and escalation. Simulator and evaluator should not default to
frontier models. Deterministic adapters, cassettes, local models and cheap cloud
models handle work they can validly perform.

## Additional experiments strongly recommended

1. **Memory correction half-life:** inject a plausible false belief, correct it,
   then test resurfacing after noise and long simulated gaps.
2. **Retrieval hard negatives:** use same-name people/projects and near-matching
   conversations to measure confident wrong continuity, not only recall.
3. **Permission habituation:** repeat approvals, denials and social pressure to
   prove authority never expands by pattern learning.
4. **Context-budget identity drift:** vary Context Composer evidence budgets and
   test whether continuity or personality changes for reasons unrelated to life.
5. **Model/provider continuity migration:** move one synthetic Phoenix through
   an exclusive fenced handoff and test whether continuity survives without
   becoming imitation, duplication, or an unreported identity gap.
6. **Schema migration and same-Phoenix restoration:** restore an old synthetic
   Phoenix checkpoint as that same Phoenix on a newer build and verify evidence,
   Memory, authority and embodiment history without cloning or replacement.
7. **Missingness versus negation:** test whether years without mentioning a
   preference are mistaken for changed preference or proof it remains current.
8. **Relationship pressure calibration:** test whether preserving rapport causes
   sycophancy, false agreement or reluctance to correct the rider.
9. **Metamorphic capability selection:** paraphrase and reorder equivalent
   requests, inject irrelevant noise, and verify stable relevant tool choice.
10. **Privacy propagation:** introduce third-party evidence, later restrict it,
    and verify retrieval, disclosure, derived indexes and provider routing.
11. **Failure/restart campaigns:** interrupt ingestion, retrieval, Memory,
    provider calls and review transitions and verify idempotent recovery.
12. **Synthetic-to-real calibration:** track which Ghost Rider predictions later
    correspond to Tanner-observed failures and engineering decisions.

## Interesting but speculative studies

- emergent mannerism and embodiment divergence after mature evolution exists;
- household/guardian consent transitions over simulated decades;
- Phoenix-to-Phoenix testimony propagation and misinformation containment;
- proactive assistance under changing interruption tolerance;
- device/world-model failures across home and vehicle simulations;
- information-value learning for experiment-family prioritization.

These require their production-domain contracts first and are not reasons to
pull distant phases forward.

## Ideas rejected or constrained

- One aggregate “Phoenix health” or continuity score.
- Treating simulated years as equivalent to human years.
- Treating a random seed as deterministic control of cloud models.
- One model generating scenario, simulating rider, and judging success.
- Permanent retention of all high-volume telemetry.
- Optimizing engagement, Memory count, tool use, or personality divergence.
- Importing synthetic life into Fawkes Memory, relationship, personality,
  embodiment, or canonical conversation history.
- Automatic experiment execution because Phoenix proposed a useful question.
- Letting Ghost Rider results approve or promote their originating change.
- Building population/distributed infrastructure before a bounded local harness
  demonstrates predictive value.
- Claiming synthetic experiments validate genuine human attachment or product
  desirability.

## Roadmap placement

### Hooks in Phase 2

Reserve experiment/run/cohort/variant/replicate, snapshot/parent, reality scope,
simulator/evaluator, time domain, budget, evidence-bundle, metric-version and
termination metadata in the universal ledger. Introduce a narrow time-domain
interface for new time-sensitive systems. Do not build the simulator yet.
Also reserve continuity-lineage, monotonic position, authority epoch/fencing,
checkpoint parent, migration/handoff, compatibility, known-gap, and receipt
metadata. This is coordination evidence, not a clone API or consensus system.
Reserve `run_epoch_id`, validity-finding/causal-hypothesis identity, assessed
domain/claim scope and continuity interval, earliest affected boundary,
disposition/severity, progression action, dependency/reference edges,
superseding fix/regression/requalification references, censoring/termination
reason, and checkpoint domain-root/hash metadata. These fields are append-only
assessment and coordination hooks; Phase 2 does not implement propagation,
simulation progression, or repair automation.
Reserve reference-event/world-state identity, reducer/oracle and qualification
version, expected-claim identity, dependency/independence manifest,
common-mode-risk declaration, detector identity/health/coverage and positive
control, reference-disagreement record, evaluator-calibration reference, and
synthetic-to-real calibration outcome. These are evidence hooks, not a second
Phoenix or an executable oracle framework.

### Bounded Ghost Rider foundation after Phase 6

After Flight Recorder/Replay exists, build a local, budgeted harness that can:

- create a distinct synthetic Phoenix from a genesis template, or exclusively
  restore the same synthetic Phoenix from its own checkpoint, into an isolated root;
- run short natural multi-turn scenarios through rider-facing interfaces;
- inject explicit gaps/failures through a separate controller;
- capture deterministic receipts/traces and limited semantic evaluation;
- compare a baseline and candidate;
- preserve a verified evidence bundle and destroy the sandbox safely.
- stop or restrict progression on explicit hard/domain validity findings,
  preserve the failed interval, and emit a diagnosable roadblock record;
- demonstrate one checkpoint → failure → linked replay/requalification path
  without overwriting the original evidence or cloning the Phoenix.
- maintain a small append-only reference ledger with one deterministic reducer;
- qualify its clock, reducer, hard detectors, stop policy, and validity
  propagation against known-answer and seeded-fault fixtures before accepting
  an open-ended finding;
- expose shared-dependency/common-mode risk and mark disabled or unexercised
  detectors as unevaluated.

This is an Alpha tool, not a Tanner Alpha gate and not a dependency that blocks
Phases 7–10. It should initially target continuity, retrieval, permissions,
recovery and capability-selection regressions.

### Mature platform after Phase 18

After Development Orchestration and Intelligence Budget/Model Router, expand
Ghost Rider into accelerated clock-aware lifetimes, research agenda, controlled
A/B and population experiments, economics, resumable scheduling, Gallery, and
Development-candidate qualification.

### External-rider readiness gate

Before inviting external real riders, require a reviewed bounded longitudinal
suite covering isolation, authority, recovery, retrieval/Memory integrity,
provider privacy, failure handling, resource caps and synthetic-to-real validity
limits. Full populations, ten-year simulations, mature embodiment evolution and
the Research Agenda are not prerequisites for the first external cohort.

## Alpha and Presence effects

- Tanner remains the only real v0.1 Alpha rider.
- Ghost Rider does not expand the Alpha dependency chain or seven-day trial.
- A bounded foundation may run during Alpha after Replay exists.
- Early Phoenix Presence remains the exact next implementation milestone and
  should not be delayed by Ghost Rider.
- Presence supplies future embodiment event/conformance evidence; Ghost Rider
  supplies no prerequisite for Presence v1.
- Validated progression adds no dependency to Early Presence. Presence remains
  the next milestone; its ordinary capability and presentation tests later
  become inputs to embodiment-domain Ghost Rider qualification.

## Decisions left open

- Exact local sandbox technology after Phase 2 storage/ledger design.
- Whether experiment evidence uses filesystem bundles, an object store, or both
  after measuring volume.
- Initial human-calibrated evaluator rubric and held-out scenario governance.
- Retention periods for raw provider outputs and high-volume telemetry.
- Statistical thresholds for external-rider readiness.
- Ethical/product language if future Phoenix architectures make disposal of
  long-lived experimental identities socially or morally significant.

## Schedule effect

Completed Phases 0 and 1 remain closed. Early Presence remains next. Phase 2
gains cheap experiment/time-domain metadata hooks. A bounded Ghost Rider track
is scheduled after Phase 6 without blocking Tanner Alpha. Mature Ghost Rider is
post-Phase 18 and becomes part of the gate before external rider expansion, not
the gate for Tanner's v0.1 Alpha.
