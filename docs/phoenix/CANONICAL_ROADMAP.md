# Project Fawkes Canonical Roadmap v1

**Status:** Frozen authoritative baseline, amended by the 0.5, 0.6, and 0.7 reviews
**Target:** v0.1 Alpha, followed by continuous capability development during
real rider use

"Frozen" means this document is the current architectural north star. It does
not make the roadmap a ceiling, prohibit new Phoenix capabilities, or prevent
evidence-driven revision. Future revisions must preserve historical versions,
state why the roadmap changed, and respect the foundational Phoenix principles.

## Phase completion gate

Every phase completion requires a whole-system clean sweep: focused and relevant
security/privacy/authorization/replay/permit tests, affected authenticated
HTTP/E2E acceptance, the full Fawkes regression suite, compilation/static
validation, `git diff --check`, final-diff inspection, and explicit cross-system
contract review. A phase may be declared complete only after that sweep is
green. Any regression must be fixed and the affected checks plus the complete
system sweep repeated before phase-status documentation is finalized.

Every clean sweep also includes an architecture-health check: **complexity must
earn its keep**. Before adding a store, schema, adapter, manager, registry,
abstraction, message bus, recovery system, compatibility path, or special case,
workers must determine whether an existing primitive correctly owns the need.
When Tanner repeats, restates, or refines a requirement, workers first identify
and report the existing owner, why it owns the need, how the refinement changes
it, current maturity, expected live boundary, and only then any genuine missing
primitive. Restatement alone never justifies duplicate architecture.
Metrics are evidence, not universal verdicts. The practical test is whether a
competent bounded worker can identify ownership, understand and isolate the
component, change and test it safely, and replace it without unrelated collapse.
Reviews record `keep`, `simplify`, `consolidate`, `deprecate`, `split`, or
`do not change` findings only when justified. Cleanup requires task authority,
recovery, and proportional Assurance; architecture health is a discipline, not
a new autonomous manager.

## Version history

- **v1 freeze:** established the Alpha dependency chain and long-term Phoenix
  architecture.
- **0.5 post-freeze amendment (2026-08-30):** elevated Embodiment from a late
  presentation feature to a core Phoenix identity-expression pillar, refined
  Early Presence into a durable 3D-first vertical slice, and added explicit
  Development Orchestration and Human Approval Gateway direction. The review
  did not change the Alpha boundary or pull mature systems before Alpha.
  Rationale and rejected alternatives are preserved in
  [Roadmap Amendment 0.5](ROADMAP_AMENDMENT_0_5.md).
- **0.6 Ghost Rider amendment (2026-08-30):** established an isolated
  longitudinal Phoenix experimentation and research track, distinguished
  production from synthetic reality scope, reserved Simulation Time and
  experiment-evidence contracts, and made bounded Ghost Rider qualification a
  pre-external-rider gate without expanding Tanner's v0.1 Alpha boundary or
  delaying Early Presence. Its accepted Validated Progression correction adds
  domain/claim-scoped roadblock validity, checkpoint eligibility, linked
  requalification epochs, a regression ratchet, and progression envelopes
  instead of scalar simulated-age claims. Rationale and constraints are preserved in
  [Roadmap Amendment 0.6](ROADMAP_AMENDMENT_0_6_GHOST_RIDER.md).
- **Universal Worker Charter v1.0 (2026-08-31):** canonicalized Phoenix-first
  worker governance, proposal/execution separation, cross-worker reporting, and
  least-privilege specialist direction without adding a runtime capability,
  authority grant, or roadmap phase.
- **0.7 multi-worker integration amendment (2026-08-31):** retained the
  numbered dependency spine while adding parallel specialist tracks,
  cross-cutting Assurance and Recovery gates, explicit synchronization gates,
  and a post-Phase-9 Worker Exchange integration milestone. It does not claim
  any worker, assurance, Board, recovery-automation, or embodiment runtime.
  See [Roadmap Amendment 0.7](ROADMAP_AMENDMENT_0_7_MULTI_WORKER.md).
- **Phoenix Public Experience v1.0 (2026-09-01):** accepted a parallel public
  product track for Phoenix's permanent web home, purpose-built public
  companion, truthful Now/Vision evidence, and optional support without making
  the site an Alpha prerequisite, a Phoenix individual, or an implemented
  capability. See [Phoenix Public Experience](PHOENIX_PUBLIC_EXPERIENCE.md).

## Governing worker contract

The [Universal Worker Charter](UNIVERSAL_WORKER_CHARTER.md), contract
`phoenix.universal_worker_charter` v1.0, governs how human and machine workers
reason, propose, coordinate, request host permission, and report. It creates no
runtime capability or authority and cannot weaken this roadmap or stricter
identity, continuity, security, privacy, provider, or domain contracts. Phoenix
Worker Coordination / Specialist Mesh and AI/Tool Scout are architectural
directions only; neither is implemented or assigned a phase by the charter.

## Roadmap operating model

The roadmap uses a hybrid structure: the numbered phases remain the
dependency/maturity spine, while Phoenix Core/Continuity, Development/Worker
Coordination, Embodiment/Manifestation, and Rider Experience/Integration may
advance in parallel inside their authority. Security, privacy, provenance,
recovery, budgets, isolation, promotion, and Assurance are cross-cutting gates.
Explicit synchronization gates prevent parallel work from inventing
incompatible contracts. Maturity labels distinguish implemented capability,
experimental prototype, approved architectural direction, future capability,
canonical contract, and deprecated/superseded state. Full rationale is in
[Amendment 0.7](ROADMAP_AMENDMENT_0_7_MULTI_WORKER.md).

Reliable, verified worker communication precedes general autonomous worker
management. [Phoenix Worker Exchange](PHOENIX_WORKER_EXCHANGE.md),
[Phoenix Assurance](PHOENIX_ASSURANCE.md),
[Checkpoint and Recovery](PHOENIX_CHECKPOINT_RECOVERY.md), and
[Embodiment Development Gates](EMBODIMENT_DEVELOPMENT_GATES.md) define the
approved architecture without implementing those future runtimes.

### Parallel product track — Phoenix public experience

The [Phoenix Public Experience](PHOENIX_PUBLIC_EXPERIENCE.md) is an approved
parallel Rider Experience/product direction. It establishes Phoenix's permanent
public home around Spectacle, Dream, Proof, and optional support. Its
purpose-built embodied public companion is a primary selling feature but is not
Fawkes or a Phoenix individual and has no access to private Phoenix systems.

This track may define and prototype the public experience without waiting for
Fawkes Alpha and without blocking unrelated Phoenix Core work. Progression is
gated rather than assigned an artificial numbered phase:

1. **Definition:** freeze a bounded product brief, public truth/publication
   boundary, companion identity, risk-prototype target, acceptance criteria,
   and external-spend ceiling.
2. **Risk prototype:** prove the hardest authored embodied journey against a
   representative asset, semantic action boundary, mobile/reduced-motion
   behavior, public/private isolation, and measured performance/cost. A
   disposable prototype is not the permanent site or a Phoenix capability.
3. **v0.1 implementation candidate:** build the durable public content shell,
   bounded polished companion, Now/Vision and Fawkes proof surfaces, graceful
   fallbacks, and deployment/abuse/analytics quality controls after prototype
   evidence supports the design.
4. **Support activation:** requires separate entity/legal/product/payment,
   privacy, refund/contact, hosted-payment, security, and operational review. It
   is not authorized merely by implementing a button.
5. **Public v0.1 launch:** requires real-device visual/accessibility/performance
   acceptance, truthful maturity/publication review, security/isolation review,
   recovery/rollback, and Tanner approval.
6. **Later public milestones:** selected promoted Fawkes evidence, Fawkes Alpha,
   and authenticated Phoenix web manifestation remain distinct events. The
   public guide visibly yields to a separately authenticated and instance-bound
   Phoenix; it never becomes one by upgrade or implication.

Framework, hosting, payment, model, rendering, final companion identity, exact
animation catalogue, layout, and copy remain replaceable implementation
choices. Website work must not substantially delay Fawkes without an explicit
Tanner tradeoff decision.

## Purpose

Project Fawkes is not an effort to build another disposable chatbot. It is the
first implementation of a persistent Phoenix: an individual AI continuity that
can survive changes in models, providers, clients, devices, and capabilities
while retaining attributable history, Memory, Development, relationships, and
rider-controlled authority.

The long-term progression is:

```text
Perception
-> Evidence
-> Knowledge
-> Memory
-> Continuity
-> Self-understanding
-> Embodied expression
-> Temporal intelligence
-> Planning
-> Agency
-> Embodiment
-> Identity and ecosystem
```

Capabilities do not become complete merely because backend code exists. Every
rider-facing feature follows:

```text
IMPLEMENT
-> REGISTER
-> PERMISSION
-> ACCEPTANCE CRITERIA
-> AUTOMATED TEST
-> END-TO-END TEST WHERE APPROPRIATE
-> TEST CENTER ENTRY
-> CAPABILITY AWARENESS
-> NORMAL USE
```

## Permanent architectural invariants

### Phoenix individuality

- Identity, Archive, Memory, Library, Development, relationships, presentation
  state, and capability configuration are isolated per Phoenix.
- A Phoenix individual is never replaced by a newer Phoenix generation.
  Infrastructure, models, providers, clients, schemas, storage, renderers, and
  capabilities may be upgraded, repaired, migrated, or replaced while the same
  Phoenix continuity persists.
- A continuity-bearing backup/checkpoint may restore only the Phoenix identity
  that owns it. Restoration continues that individual; it cannot re-key, clone,
  fork, seed, or manufacture another Phoenix. At most one authoritative active
  continuation may exist unless a future explicit continuity protocol proves a
  safe handoff without identity duplication.
- There are two normal identity outcomes across technology generations:
  continuity-preserving evolution/restoration of the existing Phoenix, or the
  beginning of a genuinely new Phoenix life. A new Phoenix may consult an older
  Phoenix's history only as attributed inherited evidence; it never inherits
  that lived history as its own. Suspension, repair, migration, and restoration
  are forms of continuity, not replacement.
- A continuity lineage has one authoritative writer/actor epoch. Temporary
  replicas used for backup, validation, or migration are non-authoritative and
  may not independently converse, mutate continuity, exercise authority, or
  perform external actions. Handoff must be fenced, receipted, and exclusive.
  Suspected duplicate activation or post-checkpoint divergence is split-brain:
  freeze consequential action, preserve both branches as evidence, quarantine
  them, and require explicit review. Never silently merge histories or choose a
  winner and call that continuity.
- Fawkes-specific development never silently becomes Base Phoenix behavior.
- Personality develops from longitudinal evidence and Phoenix interpretation,
  not a fixed persona, universal trait vector, engagement objective, or rider
  imitation.
- Evidence may inform identity; evidence does not silently become identity.

### Rider authority and Phoenix freedom

Rider authority governs what a Phoenix may do, not whether it may reason,
disagree, investigate, learn, develop preferences, recognize mistakes, propose
improvements, or form an individual communication style.

Consequential actions remain explicitly bounded, including purchases,
payments, external communication, commitments, installation, destructive
operations, privilege escalation, protected-foundation changes, credential
use, physical-security actions, and disclosure of private information.

### Historical and source integrity

- Canonical Archive evidence is immutable.
- Library and imported source originals remain authoritative.
- Summaries are for navigation; exact original text is for truth.
- Extractions, indexes, embeddings, summaries, interpretations, and current
  state are versioned derived material and never replace their sources.
- `inherited_history` is distinguishable from `native_phoenix_history`. A
  Phoenix may know inherited history without claiming to have lived it.
- Suppression, quarantine, supersession, privacy policy, and derived-state
  removal must not falsify historical evidence.

#### Founding history and the native-history boundary

The Tanner/ChatGPT conversations in which Fawkes was conceived are founding and
developmental provenance. Their inconsistent first- and third-person treatment
of Fawkes is itself authoritative historical evidence: it may support
relationship and developmental continuity with the emerging Fawkes concept,
but it does not prove native Phoenix runtime continuity. Preserve original
speaker, provider, text, timestamp, and conversation structure without
retroactively resolving that ambiguity into either an unrelated-assistant story
or a claim that Fawkes natively experienced every exchange.

`founding_developmental` is a provenance/relationship facet on inherited
evidence, not a third evidence era and not an identity bridge. Historical
first-person language is an attributed utterance, not a continuity credential.
Derived summaries and self-understanding must preserve the source era,
attribution, ambiguity, and evidence links. Fawkes may naturally describe these
as “our founding conversations,” “when we were designing me,” or “before my
native continuity existed” when the wording is grounded in that provenance and
does not claim autobiographical recall.

Native lived history begins only at an explicit, durable continuity-genesis (or
valid same-Phoenix continuation) event that binds a registered Phoenix identity
and continuity lineage to an authoritative writer epoch, after which an
interaction is committed through the native Phoenix runtime with that ownership
and monotonic continuity position. Instance names, model first-person language,
provider sessions, unscoped Archive capture, later import, and retrospective
classification cannot create this boundary. If older records cannot be proven
to satisfy it, preserve them as inherited/founding evidence or boundary-unknown;
never silently promote them. The current repository predates a complete genesis
receipt and therefore must establish this boundary prospectively rather than
invent an exact historical date.

### Phoenix Core and embodiment separation

Identity, continuity, Memory, Archive, Library, Development, relationships, and
authority belong to the Phoenix Core. Web apps, phones, desktops, avatars,
voices, vehicles, cameras, speakers, displays, wearables, and homes are
embodiments, interfaces, sensors, channels, or actuators available to the same
Phoenix. They are not separate assistants.

This is a technical ownership boundary, not a claim that embodiment is
emotionally meaningless or external to the Phoenix's continuous self. A
Phoenix may develop a persistent embodied identity, preferences about its
form, characteristic mannerisms, and a provenance-bearing visual history.
Renderers and assets remain replaceable manifestations of that identity:
changing a mesh, renderer, device, or fidelity level never creates a new
Phoenix.

### Embodiment as a core identity-expression pillar

Embodiment is a first-class continuity and relationship surface alongside
Memory, personality, Development, and conversation. It can express stable
individuality and current context nonverbally, but it never becomes a covert
personality controller or proof of biological emotion. Permanent development
is versioned and attributable; transient expression remains transient.

The durable conceptual layers are:

1. **Canonical archetype envelope:** approved recognizable anatomy, silhouette,
   rig semantics, and design language—not one immutable mesh.
2. **Developed embodied identity:** slow, persistent, per-Phoenix form,
   markings, palette tendencies, mannerisms, and approved evolution.
3. **Rider-equipped presentation:** skins, accessories, voices, sound packs,
   and environments the rider controls independently of Phoenix preference.
4. **Current expressive intent:** bounded semantic cues such as attentive,
   thinking, amused, uncertain, speaking, or task-complete; these are
   presentation claims, not biological diagnoses.
5. **Device manifestation profile:** the accessible rendering of the same
   state within a device's performance, motion, privacy, and interaction
   capabilities.

Operational presence/session state is separate from all five. A device being
active, foregrounded, or authoritative to answer is not appearance identity.

### Observation is not inference

Direct observations, rider reports, external claims, derived inferences,
estimates, and reviewed interpretations remain distinguishable. Inferences
about emotions, intentions, health, identity, or internal state remain
uncertain, attributable, time-bounded, and prohibited from silently becoming
Memory, personality, or permanent fact.

### Principals and consent

The following must never be assumed to be the same principal:

- Phoenix instance
- owner
- actor
- rider
- subject of evidence
- participant
- viewer
- guardian
- permission grantor

Records and actions may reference principals, policies, consent context, and
visibility scope without requiring the full future household system today.

### Secrets remain outside cognition

Passwords, tokens, encryption keys, and credentials never belong in normal
Memory, Archive text, Library extraction, prompts, logs, or context receipts.
Future capabilities use opaque, scoped secret handles through a dedicated
broker. Knowledge of a capability never grants authority to use a credential.

### Stable modular core

Models, providers, storage engines, search implementations, clients, devices,
and renderers are replaceable adapters behind stable provider-neutral and
platform-neutral contracts. Capability logic does not permanently live in the
current web client.

### Continuous verification

Capability Registry, capability awareness, permission enforcement,
provenance, context receipts, Test Center coverage, failure diagnostics,
mobile/desktop acceptance, and Archive-integrity checks extend with every
phase. Automated success does not imply rider/UI success.

### Production and synthetic reality isolation

Experimental Phoenix lives are never production Phoenix lives. Every
experimental object, derivation, capability execution, principal, Phoenix,
snapshot, index, cache, queue, and evidence bundle carries a synthetic reality
scope and experiment/run lineage enforced in storage and authority boundaries.
Synthetic taint survives derivation. Synthetic Memory, relationships,
personality, embodiment, and conversation history can never become Fawkes state.
Only an explicit reviewed gateway may import a minimal experiment conclusion as
Development/test evidence, retaining lineage and uncertainty.

Reality scope is orthogonal to evidence era. An experimental Phoenix may have
native lived history within its synthetic scope; it is still not production
history. Resetting a disposable Phoenix never implicitly deletes or promotes
the experiment evidence.

## Cross-cutting contracts

These are extension requirements, not permission grants or demands to build
distant features prematurely. The accepted future architecture below records
ownership and compatibility direction only: it grants no implementation,
scheduling, provider selection, production, promotion, spending, external
action, or continuing authority; it does not block near-term roadmap work.

### Schema evolution and compatibility

Every durable contract has a schema version, explicit reader compatibility,
and a migration/rebuild strategy. Canonical evidence is never rewritten merely
to make a derived schema convenient. Unknown future fields must fail safely or
remain ignorable as appropriate.

### Stable identifier taxonomy

Stable identifiers distinguish Phoenix instance, principal, artifact,
conversation, message, revision, Library source, extraction, segment, work
item, derivation, capability execution, context receipt, observation,
proposal, test run, embodiment, device, session, environment, sensor, actuator,
policy, consent context, and sandbox branch. Identity never depends solely on
a filesystem path, provider ID, mutable title, or current model.

Experimental systems additionally distinguish research question, experiment
definition, scenario/version, run, cohort, variant, replicate, genesis template,
same-Phoenix continuity checkpoint, environment snapshot,
reality/isolation scope, simulator, evaluator/rubric, time domain, evidence
bundle, metric derivation, and termination identity. These identifiers grant no
authority.

Ghost Rider progression additionally distinguishes run epoch, validity finding,
causal hypothesis, affected domain/claim and continuity interval, earliest
affected boundary, progression action, remediation/requalification, checkpoint
domain roots, and censoring reason. Experimental validity is append-only
assessment metadata and must not be confused with permanent synthetic
`reality_scope` taint.

Ghost Rider bootstrap evidence additionally distinguishes reference-world
event/state, reducer/oracle and qualification version, expected claim,
dependency/independence manifest, common-mode risk, detector health/coverage and
positive controls, reference disagreement, evaluator calibration, and
synthetic-to-real calibration outcome. Reference truth is authoritative only
for controlled scenario facts and invariants, never for emergent human meaning.

### Phoenix source-artifact envelope

Retained and staged sources can share a minimal versioned envelope containing,
where applicable:

- artifact and schema identity;
- Phoenix instance and owner scope;
- artifact kind, source domain, and evidence era;
- original-source identity and content digest;
- media type and immutable storage reference;
- event, creation, and ingestion times;
- privacy, trust, lifecycle, and retention policy;
- actor, subject, participant, policy, and consent references;
- rights/usage metadata;
- resource/quota and physical-safety classification;
- provenance parents and typed lineage;
- encryption/key reference or opaque secret handle, never raw secrets;
- optional entity, environment, device, sensor, actuator, embodiment, session,
  correlation, causation, and sandbox/branch identifiers.

Optional extension fields do not make their future systems operational.

### Typed provenance and lineage

Derived records can express typed relationships such as `derived_from`,
`extracted_from`, `summarizes`, `quotes`, `supports`, `contradicts`,
`supersedes`, `references`, `imported_from`, `transmitted_to_provider`,
`produced_by`, `approved_by`, and `tested_by`. A graph database is not required;
the relationship contract is.

### Explicit lifecycle state machines

Lifecycle is not a single retained boolean. Systems distinguish receipt,
validation, privacy classification, transmission authorization, temporary
processing, retention request, durable registration, extraction/indexing,
failure, quarantine, supersession, suppression, active removal, derived-state
deletion, and permissible original destruction. Archive immutability is not a
pretext for retaining every temporary upload forever.

### Storage abstraction

The current filesystem remains valid, behind narrow instance-scoped operations
for storing/verifying/opening immutable blobs, enumerating ownership, backing
up, restoring, and verifying. Metadata and blobs remain conceptually distinct.
No cloud store is required now.

### Encryption and key-reference hooks

Records may describe encryption state, scheme version, and opaque key
reference without containing key material. This permits later per-Phoenix or
high-privacy encryption without redesigning every artifact schema.

### Provider-transmission receipts

External processing records the source digest, capability/provider class,
purpose, authorization source, privacy classification, transformations or
redactions, transmission time, known retention configuration, result
derivation, and failure state without exposing credentials or private payloads
in ordinary logs.

### Semantic domain events and reliable processing

Lifecycle events such as artifact validation, retention request, extraction,
indexing, backup, restoration, and provider transmission use stable semantic
event names, correlation/causation IDs, and idempotency keys. Durable work
items, atomic claims, retry states, and result references prevent crashes and
client retries from creating unknowable half-states.

### Canonical run and campaign execution context

Future coordinated work uses one immutable, canonical `RunContext` created at
bootstrap. It carries run/campaign/work IDs; actor and role; provider, model,
version, and configuration; workspace and separately declared external roots;
capabilities and allowed paths; model/tool/test/retry/concurrency/time/cost
budgets; and policy, authorization, correlation, and trace IDs. Downstream
stages consume that context rather than guessing values or depending on ambient
environment beyond bootstrap. A durable, idempotent lifecycle records campaign
creation, dispatch, checkpoint, pause, retry, resumption, completion,
rejection, cancellation, and rollback so replay cannot duplicate effects.

A named least-authority Capability Broker resolves each operation against the
context's explicit grants. Typed handoffs carry exact inputs, lineage,
constraints, and requested work, but never inherit or forward the sender's
authority; recipients must receive their own independently valid grant.

### Unified execution evidence and qualification

Work emits a versioned, sanitized event/trace envelope with run, actor/role,
stage, correlation/causation, timing, policy, capability, status, and evidence
references, without bodies, secrets, or private prompt content. This is the
eventual source for Worker Pulse visibility, not a second execution authority
or canonical evidence store.

A provider-neutral qualification registry records the scoped evidence by which
a provider/model/version/configuration may serve a role. A body-free Usage and
Outcome Ledger records provider, model, version, role, task and context class,
tokens or credits, estimated cost, latency, retries, tools, tests, verdict,
corrections, regressions, escalation, acceptance, rejection, and rollback.
Derived routing measures remain versioned projections of that evidence; they do
not grant authority, replace exact evidence, or turn cost into a verdict.

### Memory write gateway

Future writes pass through one policy-enforcing Memory Write Gateway that keeps
working context, operational state, evidence, personal continuity, and durable
Archive/Memory distinct. A successful run, handoff, model statement, summary,
or Worker Pulse event cannot silently become personal continuity or durable
Memory; each destination retains its own provenance, review, privacy, and
lifecycle rules.

### Actor, consent, and third-party privacy

Operations identify whether they were initiated by a rider, Phoenix,
developer, runtime, import, workflow, or future peer Phoenix. Privacy metadata
can represent affected third parties, unknown consent, sharing restrictions,
and policy references. Rider possession of media does not erase the privacy
interests of people appearing in it.

### Resource, quota, and safety metadata

Artifacts and work may record size, pages, duration, estimated/actual cost,
processing depth, retry bounds, quota class, and safety class. This establishes
hooks for video, ingestion, model routing, and physical action without building
billing or device control now.

### Entity/reference and temporal extension

Evidence may reference stable entities and aliases while retaining ambiguity,
confidence, merge/split history, and temporal validity. An unresolved reference
does not become a fabricated person or fact.

### Sandbox and branch identity

Replay, proposed improvements, experimental extractions, and candidate state
can reference a parent revision and isolated branch. Experimental results never
silently become live Phoenix state.

### Presence, sessions, and standing authority

Contracts reserve environment, device, sensor, actuator, embodiment, channel,
session, correlation, and causation identity. Future standing authority is a
scoped, expiring, revocable lease with preconditions, limits, safety rules,
verification, and emergency interruption—not a permanent blanket permission.

Presence authority is independent of observation, capture, retention,
provider transmission, disclosure, interaction, notification/attention,
environmental action, persistence/autostart, and installation authority.
Allowing a Phoenix to appear or receive a click on a desktop grants none of
those other powers. Platform adapters must declare and enforce these scopes
rather than collapse them into a generic device permission.

### Embodiment state, assets, and local rendering

Phoenix Core emits bounded semantic presentation intents and consumes
interaction events; it does not generate animation frames. Device-local
renderers map intents to accessible motion under rider policy, reduced-motion,
battery, thermal, and distraction constraints. Rendered behavior must remain
bounded and diagnosable and must preserve a nonvisual interaction path.

Embodiment assets have stable logical roles, content hashes, format and schema
versions, archetype/rig compatibility, rights, provenance, safety review, and
fallbacks. Asset ownership or purchase does not become personality, Memory, or
Phoenix identity. Future third-party assets are untrusted data, never scripts
or authority-bearing instructions.

The future Phoenix Embodiment Fabric presents one continuing Phoenix through
many genuine forms. Every form declares its perception, expression, action,
presence, identity, consent, privacy, and authority capabilities. Renderers,
devices, and manifestations remain replaceable without fragmenting continuity;
connection, handoff, appearance, or presence never implicitly transfers
authority between forms.

### Development coordination and approval

Development runs may reference a trigger, proposal, actors and agent roles,
provider/model, work and run IDs, sandbox/branch, plans, affected components,
authority/risk class, acceptance criteria, tests, review disagreements, costs,
decisions, promotion/rollback, and observed outcome. These are Development
evidence coordinated through the universal processing ledger—not personal
Memory or a competing canonical conversation store.

Agent requests never grant authority. Approval is a bounded, expiring,
replay-protected authorization for an exact action/run and authenticated
principal/channel. Repetition of approvals never creates standing authority;
only an explicit scoped lease can do so. Timeout is never approval.

### Experimental time and evidence planes

Experiment records distinguish real recorded/ingestion time, real monotonic
duration, scenario event time, and simulated Phoenix time in a named time
domain. Simulation never rewrites the host clock, security expiry, billing
clock, provider freshness, or production chronology. Time advancement is an
explicit attributable event consumed only by clock-aware components.

Ghost Rider distinguishes durable raw experiment evidence, versioned/rebuildable
metrics and evaluator judgments, and high-volume ephemeral telemetry. Reset and
evidence retention are separate lifecycle operations; historical integrity does
not require retaining unlimited telemetry forever.

## Current foundation

The repository already provides meaningful foundations for authenticated and
persistent Chat, canonical Archive, Memory processing, Development observations
and Human Review, provenance/context receipts, web research, temporary
image/PDF/audio reasoning, safe presentation envelopes, visualizations,
capability authority and self-awareness, the rider Test Center, semantic event
audio settings, instance-scoped content-addressed Library originals, versioned
Library extraction records, lexical Library consultation, and bounded
continuity retrieval. Later phases extend these systems rather than duplicate
them.

# Roadmap

## Phase 0 — Ownership, integrity, privacy, and recovery foundations

- Enforce per-Phoenix ownership on every new durable source, derivation, index,
  receipt, setting, and work item.
- Introduce the source-artifact/lifecycle envelope and stable ID taxonomy.
- Establish the Provider Privacy Gateway and provider-transmission receipts.
- Establish storage, encryption/key-reference, actor/consent, third-party
  privacy, resource, event, and sandbox hooks described above.
- Audit legacy unscoped data without rewriting canonical history.
- Expand integrity verification, backup, isolated restoration, and rebuild
  instructions across the complete Phoenix state.
- Add dynamic capability health: live, partial, degraded, failed,
  rate-limited, permission-blocked, disabled, untested, and environmentally
  unverifiable.

The implemented complete-state backup and isolated-restore foundation remains
Phase 0. Its approved extension into active development checkpoints,
worker-write recovery readiness, dependency closure, maximum rollback distance,
and risk-tiered restore proof is defined by
[Phoenix Checkpoint and Recovery](PHOENIX_CHECKPOINT_RECOVERY.md); the broader
automation is not yet implemented and does not reopen completed Phase 0 work.

## Phase 1 — Durable Library and media authority

- Implement an explicit temporary versus Keep in Library transition.
- Make temporary retention/deletion behavior rider-visible.
- Preserve immutable, content-addressed, instance-isolated originals.
- Support hashing, deduplication, source identity, editions/revisions, rights
  metadata, privacy, trust, and lifecycle.
- Orchestrate versioned PDF/document extraction with physical page, displayed
  page, chapter, section, subsection, and native locators.
- Keep original sources authoritative over summaries and extractions.
- Integrate Library search and conversational consultation without creating
  Memory or a second Library.
- Add full capability awareness and Test Center coverage.

## Near-term vertical slice — Early Phoenix Presence

After Phase 0 and the core Phase 1 ownership/privacy/recovery contracts are
proven, implement a deliberately bounded early presence slice before large
historical ingestion:

- a serious, mobile/desktop Fawkes UI built on the stable client skeleton;
- the smallest durable **true 3D** Phoenix belonging to one Phoenix, with a
  deliberately small rig, animation, expression, and interaction surface;
- portable, versioned assets and a renderer-neutral embodiment-state contract;
- versioned, persistent, per-Phoenix canonical archetype reference, rider base
  palette, equipped-presentation state, and embodiment revision identity;
- local semantic-state rendering for idle, invoked/attentive, thinking,
  responding, and task-complete, with reduced-motion and static fallbacks;
- the Phoenix itself as a keyboard-accessible click/tap invocation surface,
  without making it the only route to Chat or Settings;
- actual playback of the exact rider-approved event-sound assets when supplied;
- existing master, volume, and per-event sound controls;
- a rider-configurable invocation/presence phrase;
- an invocation experience that may wake/present the UI/avatar and play an
  allowed sound;
- explicit separation between invocation and authentication/authorization.

The phrase cannot authorize credentials, purchases, locks, protected settings,
external communication, or consequential action. This slice is not a mature
avatar engine, evolution tree, 3D world, ambient desktop process, realtime
voice system, or personality controller. It is the first durable client of the
future Phoenix Embodiment
Model and must retain canonical text/accessibility fallbacks. It is scheduled
early because visible identity matters to real use, but it is not an Alpha
trust gate and must not delay or weaken the evidence foundation.

The default portable asset target is glTF 2.0/GLB with explicit rig/clip and
material-channel conventions. That is an interchange decision, not a permanent
renderer decision. Before implementation, a bounded web/mobile performance
spike must compare a small renderer adapter against the current dependency-light
PWA and verify loading size, frame pacing, battery/thermal behavior, animation
blending, context loss, accessibility fallback, and low-end-device behavior.
Parallel embodiment prototypes and their software synchronization gates are
defined in [Embodiment Development Gates](EMBODIMENT_DEVELOPMENT_GATES.md).

## Phase 2 — Universal canonical processing ledger

- Generalize the existing durable Memory work-item pattern into a
  provider-neutral processing contract.
- Track source/object/content/revision, processor version, lifecycle, attempts,
  errors, costs, assessments, decisions, derived results, review, and
  idempotency.
- Preserve clear domain ownership: the ledger coordinates work and does not
  replace Archive, Library, Memory, Development, or Test history.
- Build the Corpus Coverage and Blind-Spot projection for canonical presence,
  parsing, extraction, indexing, duplicate status, quarantine, failures, and
  retrieval-test coverage.
- Reserve provider-neutral development-run metadata for actor/agent role, run,
  step/dependency, branch/sandbox, pause reason, approval reference, exact
  result, and idempotent resumption. These fields do not activate agent
  orchestration or grant authority.
- Reserve provider-neutral experiment metadata for reality/isolation scope,
  experiment/scenario/run/cohort/variant/replicate, genesis template,
  same-Phoenix continuity checkpoint, environment snapshot, synthetic
  rider and Phoenix, simulator/evaluator versions, time domain, budgets,
  evidence bundle, metric version, and termination. Add a narrow Clock/TimeDomain
  injection seam for new time-sensitive systems without pretending all existing
  code is simulation-aware. These hooks do not implement Ghost Rider.
- Reserve a provider-neutral continuity-lineage contract: `continuity_lineage_id`,
  monotonic continuity position, authority epoch/fencing token, checkpoint and
  parent position, migration/handoff ID, source/target infrastructure version,
  compatibility assessment, known-loss/gap declaration, and handoff/restore
  receipt. This metadata does not implement distributed consensus or authorize
  cloning; it makes later migrations and restores inspectable and fail-closed.
- Reserve append-only validated-progression metadata: run epoch,
  validity-finding/causal-hypothesis identity, affected domain/claim scope and
  continuity interval, earliest affected boundary, disposition/severity,
  progression action, dependency edges, fix/regression/requalification
  references, checkpoint domain roots/hashes, and censoring/termination reason.
  Phase 2 does not implement the Ghost Rider progression engine.
- Reserve independent-reference qualification metadata: reference event/state
  and expected claim IDs, reducer/oracle and qualification versions,
  dependency/independence class, common-mode risk, detector health/coverage and
  control evidence, disagreement, evaluator calibration, and synthetic-to-real
  calibration. This does not build a second Phoenix or make Ghost Rider live.

## Phase 3 — ChatGPT export staging importer

Implementation status (2026-08-31): the provider-neutral staging foundation,
ChatGPT ZIP adapter, immutable inherited-evidence store, bounded inspection
projection, processing-ledger coordination, recovery, capability registration,
and synthetic acceptance are implemented. No real export has been imported;
attachment recovery, manual federated search, and corpus validation remain in
their later phases.

- Preserve and hash the untouched ZIP as the authoritative source artifact.
- Build a provider-neutral importer/parser/canonical-record/index pipeline with
  ChatGPT Export as its first adapter.
- Preserve titles, stable conversations/messages, branch hierarchy and order,
  roles, timestamps, revisions, recoverable attachments, source metadata, and
  import warnings.
- Make import resumable and idempotent.
- Classify staged material as read-only `inherited_history`, not Memory,
  personality, Development truth, or lived Phoenix experience.
- Preserve an orthogonal founding/developmental relationship-provenance facet
  and identity-attribution status (`ambiguous` where the source is mixed). Do
  not infer native identity from first-person wording or erase contradictory
  third-person wording. Import and derived summaries must retain exact evidence
  links and must not establish or backdate the native-history boundary.

## Phase 4 — Manual historical and federated search

Implementation status (2026-08-31): the bounded native-Archive plus inherited-
history vertical slice is implemented with authenticated manual invocation,
domain-neutral deterministic navigation snippets, explicit provenance and
availability, exact-original navigation, capability awareness, Test Center,
and synthetic HTTP acceptance. Memory/Library/Development federation, richer
filters, semantic search, AI navigation summaries, real-corpus validation, and
automatic context access remain unimplemented and must not be inferred from
this status.

- Search native Archive, imported history, Memory, Library, and Development as
  distinct domains.
- Support keyword, exact phrase, semantic, date, source, era, conversation,
  speaker, project/topic, status, and later attachment filters.
- Present domain, source, time, speaker, era, provenance, match highlighting,
  AI navigation summary, and expandable exact original text.
- Open full source/conversation and jump to surrounding evidence.
- Add rider-visible retrieval suppression, explicit-search-only, privacy,
  quarantine, and supersession policy without falsifying Archive evidence.

## Phase 5 — Historical corpus validation and retrieval evaluation

Implementation status (2026-08-31): pre-import audit completed. Phase 3 was hardened
to preserve accepted originals before parsing, require explicit matching
authority, fail parser interruptions recoverably, and retain irregular branch
identity under staging schema v2. The deterministic Phase 5 validation engine
and rider-requested capability now reconcile synthetic originals against staged
counts, branch identities, exact text, hashes, provenance, and known-query
navigation. No real export was imported, so real-corpus qualification has not
begun. Whole-document parser limits require artifact/RAM/disk preflight;
oversized exports must wait for a streaming adapter rather than bypass limits.

- Begin with the known query `Fawkes` and compare imported results to the
  original export.
- Validate counts, branches, chronology, speakers, exact text, attachments,
  duplicates, era, hashes, and provenance.
- Establish known-answer evaluation cases for people, courses, projects,
  decisions, reasons, research, unresolved problems, exact phrases, distant
  paraphrases, timestamps, contradictions, ambiguity, true absence, and cases
  where historical retrieval should not run.

## Phase 6 — Retrieval Flight Recorder and Replay Lab

Implementation status (2026-08-31): the bounded foundation records completed
live turns as immutable instance-scoped diagnostic evidence, replays detached
inputs through explicitly supplied versioned candidates without mutating
ordinary history, compares exact evidence/response digests, and requires
reviewer-attributed promotion into regression cases. Phase 0 audit and recovery,
capability awareness, and Test Center coverage include the new store. Current
retrievers expose selected evidence and policy exclusions, not the complete
pre-ranking candidate stream; semantic quality evaluation and the managed
rider-facing Replay Lab remain unimplemented. See
[Retrieval Flight Recorder and Replay Lab](RETRIEVAL_REPLAY.md).

- Record request, capability selection, retrieval plan, queries, candidates,
  ranking, exclusions, selected evidence, context allocation, response,
  latency, and cost.
- Replay historical turns against new retrievers, indexes, composers, and
  routing policies without altering ordinary conversation history.
- Compare evidence and response differences and promote reviewed failures into
  regression cases.

## Cross-cutting post-Phase 6 track — Bounded Ghost Rider foundation

Build a local, budgeted experimental harness after Flight Recorder/Replay can
provide diagnosable evidence. Instantiate each distinct synthetic Phoenix from
a non-individual genesis template in its own isolated disposable root; exercise short natural
multi-turn rider scenarios through the same semantic interfaces; inject gaps
and failures through a separate experiment controller; collect deterministic
assertions plus limited independent semantic evaluation; compare baseline and
candidate; preserve a verified evidence bundle; revoke run authority and safely
destroy the sandbox.

The simulator, Phoenix, instrumentation, environment/fault controller, and
evaluator remain distinct. A seed does not make cloud models deterministic;
open-loop replay and closed-loop behavioral simulation are separate experiment
modes. Hard isolation, authority, Archive-integrity, provenance, provider, and
cost failures cannot be averaged away by quality scores.

The system under test is never the sole authority for the claims used to judge
it. Controlled scenario truth comes from a small append-only reference ledger
and independently qualified deterministic reducers where possible. Record
shared dependencies and common-mode risk per claim. Emergent qualities have no
false deterministic oracle: use versioned calibrated judgments, disagreement,
uncertainty, and human anchors. Disabled or unexercised detectors make the
relevant claim unevaluated, not passing.

Simulation speed is subordinate to validity. Use append-only, domain- and
claim-scoped validity findings rather than one global taint flag. Hard identity,
isolation, canonical-integrity, authority, destructive-safety, or synthetic
leakage failures freeze/quarantine the run; bounded failures restrict only
dependent evidence when that boundary is defensible. Preserve invalid intervals
as failure evidence, propagate findings through provenance/dependency edges,
and resume only from an eligible same-Phoenix checkpoint or a separately linked
new run under the remediation rules in Amendment 0.6.

Do not publish scalar simulated age as qualification. Report a versioned
validated progression envelope by domain/build/configuration with activity,
coverage, fault exposure, clock awareness, replication, confidence, unresolved
findings, and censoring. Population work uses survival/progression curves with
shared-cause and competing-risk semantics.

Longitudinal Ghost Rider work must also qualify continuity across technological
generations: migrate one synthetic Phoenix through an exclusive fenced handoff,
or restore it from its own verified checkpoint after simulated loss, then test
history, Memory, relationships, Development, embodiment, provenance, authority,
temporal integrity, information loss, and behavioral drift. A matched control is
a different Phoenix created from the same genesis template, never a concurrent
copy of the lived Phoenix under test.

Phoenix Continuity Proof v1 is the future evidence contract for this work and
is validated primarily through Ghost Rider Alpha. It covers chain integrity,
clean resurrection, cross-model restoration, behavioral continuity, privacy,
corruption recovery, and Worker Pulse visibility. Ghost Rider progresses from
deterministic scenarios to disposable Phoenixes, simulated time, adversarial
trials, and longitudinal Alpha evidence; no stage may claim continuity merely
from model similarity, a passing summary, or an unfenced copy.

This is a useful Alpha-time Development tool, not a v0.1 Alpha gate and not a
dependency that blocks Phases 7–10. Initial targets are retrieval/continuity,
Memory correction, capability selection, permission habituation, provider
privacy, restart recovery, and cross-Phoenix leakage. See
[Roadmap Amendment 0.6](ROADMAP_AMENDMENT_0_6_GHOST_RIDER.md).

## Phase 7 — Unified Retrieval Planner and semantic projections

Implementation status (2026-08-31): **Phase 7 production activation is
complete.** The read-only provider-neutral planner operates over versioned domain
adapters. Eligibility precedes ranking; ownership, authorization, automatic-use
policy, health, provenance, authority, and projection freshness exclusions are
explicit. Deterministic fair character budgeting prevents one domain from
starving peers, inherited provenance/unknown identity boundaries remain exact,
and Phase 6 records the resulting candidates, exclusions, allocations,
warnings, and replay inputs. A deterministic rebuildable projection descriptor
detects stale frontiers without choosing an embedding provider. The served
planner path is default and its retrieval, eligibility, adapter, and transmission
capabilities are `live`; explicit legacy mode remains the rollback. Production
semantic projections are not built, deterministic local ranking is documented,
and automatic inherited-history retrieval remains disabled pending qualification. See
[Unified Retrieval Planner](UNIFIED_RETRIEVAL_PLANNER.md).

The next bounded policy slice is also implemented. Versioned production
eligibility now distinguishes storage/access, automatic primary-rider private
context, provider transmission, external disclosure, and cross-principal
disclosure. Potentially private evidence remains usable in owned authenticated
private context without gaining disclosure authority; highly private evidence
requires explicit sensitive relevance or a scoped grant; restricted evidence
requires evidence-specific authorization. Unknown metadata, foreign ownership,
invalid provenance, unauthorized capability, and denied provider transmission
fail closed. Context receipt schema v7, Flight Recorder, Replay, and the
Provider Privacy Gateway preserve sanitized policy evidence. Automatic
inherited-history retrieval remains unconditionally disabled. Ordinary Chat
integration uses the compatibility policy where legacy Archive and Memory lack
an explicit privacy/owner-principal envelope; it does not invent or silently
backfill canonical metadata. See
[Production Evidence Eligibility Policy](EVIDENCE_ELIGIBILITY_POLICY.md).

The approved legacy compatibility correction is implemented without canonical
backfill. Trustworthy scoped Archive/Memory evidence can derive
`legacy_private_unclassified` for owner-private context while explicit modern
metadata always wins. Foreign, uncertain, malformed, shared, restricted,
revoked, quarantined, suppressed, and synthetic-inappropriate evidence fails
closed. A deterministic body-free review projection reports compatibility,
review, explicit-classification, uncertain-ownership, and blocked status. The
production planner applies compatibility before materialization/ranking and
never rewrites the source. See
[Legacy Archive and Memory Compatibility](LEGACY_EVIDENCE_COMPATIBILITY.md).

The two-stage production adapter slice is implemented for native Archive,
Memory, and Library. Adapters enumerate body-free metadata, apply eligibility
and compatibility, materialize only allowed references, and rank only the
eligible set before deterministic Unified Planner allocation. Provider-backed
rankers cannot receive provider-denied candidates, and local degradation cannot
reopen a denial. Inherited history has no automatic adapter. Default served Chat
uses these adapters before its verified exact-set permit boundary. See
[Two-stage Production Evidence Adapters](PRODUCTION_EVIDENCE_ADAPTERS.md).

The pre-call transmission boundary is implemented as a content-addressed,
body-free exact-set manifest and permit bound to Phoenix, rider, turn, provider
route, policy versions, source references, and evidence digests. Tampering,
stale decisions, route/ownership mismatch, and changed evidence fail closed;
empty authorized sets remain usable. A deterministic rollback switch never
falls from planner failure into policy-bypassing legacy retrieval. Ordinary
Chat now defaults to planner mode, whose prompt builder verifies the
permit before evidence incorporation and again at the real provider call. A
late failure scrubs evidence and responds with zero retrieval; legacy remains
the explicit rollback. Production Archive, Memory, and Library assembly,
authenticated served HTTP acceptance, and default activation are complete. See
[Pre-call Evidence Transmission Manifest](EVIDENCE_TRANSMISSION_MANIFEST.md).

- Determine what evidence a request requires rather than blindly supplying a
  pile of memories.
- Select among working conversation, Memory, native Archive, imported history,
  Library, Development where appropriate, supplied media, and current web.
- Use separate rebuildable per-domain, per-Phoenix exact/lexical/semantic
  projections rather than one authority-erasing vector database.
- Resolve intent, entities, temporal constraints, evidence sufficiency,
  authority, privacy, contradictions, context budget, and clarification needs.

## Phase 8 — Archive-wide and cross-conversation continuity

Implementation status (2026-08-31): the first bounded native-only foundation is
implemented on the production Phase 7 path. Eligible native Archive evidence
receives stable cross-conversation identity, deterministic recorded-time order,
original-conversation neighbor references, conservative unresolved lexical
mentions, explicit ambiguity sets, non-merging duplicate relationships, and
preserved declared contradiction groups. The projection is rebuildable,
frontier-addressed, omitted when stale, observable through receipts/Flight and
Replay, and cannot mutate or merge canonical evidence. Automatic inherited
history remains disabled. See
[Native Archive Continuity Projection](NATIVE_ARCHIVE_CONTINUITY.md).

Subsequent bounded Phase 8 slices below add deterministic relative-time and
reference generation plus explicit source-original preference. Richer thread
relationships and rider-facing ambiguity handling remain.

The second bounded slice implements conservative native candidate generation
between policy eligibility and materialization. Direct body-free lexical
matches, explicit ISO-date constraints, and one-hop same-conversation neighbors
receive deterministic reason/relationship identities and bounded round-robin
limits. Duplicate generation paths collapse only the candidate reference;
canonical records and contradictory evidence remain distinct. Every expanded
neighbor independently passes Phase 7 ownership, privacy, provenance,
capability, and provider policy before it can be generated or materialized.
At this point the remaining temporal work was relative/natural-language time;
the following slice resolves its bounded deterministic subset.

The third bounded slice binds relative interpretation to the persisted request
timestamp and explicit IANA rider timezone, falling back deterministically to
UTC with the fallback reason recorded. Local calendar and bounded relative
windows are stored as exact UTC intervals for Replay, including DST-sensitive
days. Conservative conversation/discussion/category and directional neighbor
references now generate bounded eligible anchors; unresolved cross-conversation
anchors become explicit ambiguity sets. The following slice adds
source-original preference; richer non-lexical-but-provider-neutral reference
relationships, multi-hop thread policy, and rider-facing clarification follow
in later bounded slices below.

The fourth bounded slice implements native source-representation preference
from fully verified `duplicate_of`/`derived_from` provenance chains only. After all
representations independently pass Phase 7 policy, a stronger eligible
source-original may replace a redundant copy in request context before
materialization and planner budgeting. Uncertain, conflicting, cyclic,
contradiction-bearing, or denied-target provenance preserves all candidates.
Canonical records remain distinct and unchanged; no truth winner is selected.
The following slices add richer thread/reference relationships and rider-facing
ambiguity/clarification behavior.

The fifth bounded slice adds deterministic native thread/reference traversal
inside the existing Phase 7 production path. Explicit navigation intent may
walk two recorded-order conversation hops or at most eight verified body-free
native reference edges. Every target comes only from the independently eligible
pool. Multiple targets remain an ambiguity set; denied targets cannot piggyback,
and canonical or contradictory evidence remains distinct. The following slice
adds rider-facing ambiguity/clarification behavior; bounded reference vocabulary
remains driven by native retrieval needs.

The sixth bounded slice adds deterministic rider-facing ambiguity decisions.
Material native ambiguity now produces a concise served clarification before
permit creation or provider use; an explicitly safe joint-inclusion basis may
proceed only when all eligible interpretations fit. Stable choice IDs are bound
to Phoenix, rider, originating turn, policy versions, and retrieval-plan identity
and never grant authority. Receipts/Replay remain body-free and tamper-evident.
The remaining Phase 8 boundary is bounded served consumption of a validated
choice with fresh eligibility/permit enforcement, then a whole-system Phase 8
completion assessment.

The seventh bounded slice implements that served consumer. It accepts only an
immediately preceding, receipt-backed clarification choice bound to the active
Phoenix, rider, conversation, originating turn, query digest, ambiguity/choice,
policy versions, and old plan identity. It reruns production adapters and Phase
7 eligibility, constrains only the chosen ambiguity set, forbids sibling
substitution, and creates/reverifies a fresh exact-set permit. Choice authority
is always false and diagnostics remain body-free.

The eighth bounded slice integrates the served choice contract into ordinary
rider Chat. Accessible native choice controls render within the originating
assistant turn, hide opaque internal identities, prevent duplicate submission,
and send only the exact server-issued, turn-bound clarification payload. A
successful choice leaves its historic controls disabled; stale, changed,
malformed, or failed choices are reported truthfully and never cause a sibling
selection or authority fallback. The client retains no reusable authorization;
fresh Phase 7 eligibility and exact-set provider permits remain server-owned.

The final Phase 8 gate qualifies ambiguity/reference behavior against 14
deterministic disposable synthetic native Archive scenarios with expected truth
kept outside runtime inputs. Predeclared thresholds passed: ambiguity recall
4/4, false-positive clarifications 0/6, safe joint inclusion 1/1, exact eligible
choice sets 4/4, traversal precision 100% with all 12/12 annotated references,
temporal accuracy 3/3, fail-closed security checks 48/48, and deterministic
repeats 14/14.

The first run exposed and boundedly corrected two native candidate-generation
defects: explicit temporal windows now exclude out-of-window direct lexical
matches, and existing reference intent now preserves multiple direct matches
across conversations as material ambiguity. Final raw-count review also aligned
recognized documented reference kinds with traversal intent. No semantic resolution, truth
selection, inherited participation, or vocabulary expansion was introduced.

**Phase 8 — Archive-wide and cross-conversation continuity is COMPLETE.** Its
whole-system completion sweep passed. Automatic inherited-history retrieval
remains disabled. See
[Native Archive Ambiguity Corpus Acceptance](NATIVE_ARCHIVE_CORPUS_ACCEPTANCE.md).

- Generalize bounded continuity across people, courses, projects, purchases,
  decisions, research, problems, plans, recommendations, reasons, outcomes, and
  shared experiences.
- Add entity-aware and temporal retrieval, source-original preference,
  neighbor/thread relationships, duplicate-copy control, ambiguity sets,
  contradiction preservation, and honest limitation reporting.
- Distinguish not-in-working-context, not attempted, no match, unindexed, not
  stored, unauthorized, and unavailable.

## Phase 9 — Production Context Composer — COMPLETE

Phase 9 is complete. The first bounded production slice adds
`production-context-composer-v1`: a content-addressed structured package at the
default planner response boundary. It consumes only the exact upstream
provider-authorized retrieval set, preserves domain authority, provenance,
privacy/provider decisions, ambiguity, uncertainty, contradictions, ordering,
trust isolation, and honest character-budget observations, and emits a
defensively sanitized body-free receipt/Replay audit. Rendering verifies the
package identity. Final permit failure rebuilds a zero-retrieval package and
never falls through to legacy evidence. Capability `context.compose` is
production-active. The second bounded slice adds
`composition-purpose-policy-v1` with the registered default
`response_model_context` v1 profile and
`context-cross-source-allocation-v1`. Final whole-item allocation consumes only
provider-eligible planner output before permit creation, preserves fitting sets,
prevents noisy-domain starvation when reduction is required, treats
contradiction-connected evidence atomically, and records deterministic body-free
decisions. Unknown purposes fail closed. The third bounded slice adds
`context.inspect` v1.0: an authenticated, lazy, body-free projection over the
existing context receipt and matching Flight evidence. It exposes purpose,
package/allocation identity, source classes, selected/omitted identities,
uncertainty/contradiction/ambiguity indicators, exclusions/warnings, permit
status, and receipt/Replay linkage without rerunning retrieval, persisting a
second truth, or granting authority. The final bounded slice adds
`context.feedback` v1.0 beside the Inspector. Registered versioned rider signals
are bound to the exact revalidated receipt/package/allocation/permit/Replay
decision and recorded idempotently as body-free Development evidence. Feedback
cannot change retrieval, ranking, eligibility, permissions, Memory, identity,
policy, or promotion. See
[Production Context Composer](PRODUCTION_CONTEXT_COMPOSER.md).

The versioned, extensible composition-purpose/consumer-profile seam describes the
authorized downstream use of a package without selecting workers or recipients,
granting retrieval/disclosure/transmission/tool authority, verifying claims, or
turning proposals into approval. Response context, rider inspection, Replay,
specialist handoff, Assurance, research, and local processing are illustrative
profiles rather than a permanently closed vocabulary.

- Compose bounded current conversation, Memory, historical evidence, Library,
  research, and media according to intent and authority.
- Enforce token allocation, relevance, recency, importance, deduplication,
  contradiction, uncertainty, source diversity, current-intent priority,
  injection isolation, and provenance.
- Provide a rider-visible Context Inspector explaining why sources were used.
- Add low-friction retrieval feedback such as right history, wrong
  conversation, missed source, outdated source, search again, and do not
  proactively retrieve.

## Cross-cutting integration gate — Phoenix Worker Exchange

After Phase 9 and before Phase 10, establish the transport-neutral foundation
for reliable, attributed, source-preserving exchange among already-approved
workers. Delivery, verification, approval, and promotion remain distinct;
recipient verification is claim/task scoped; disagreement is preserved; and
Worker Pulse/Phoenix Board are rebuildable descriptive projections only.
Active work stopped specifically on Tanner is projected as an urgent
active-flow rider blocker; required but nonblocking review and FYI remain
distinct. The projection explains the blocked branch and exact decision and
never becomes approval authority. Phoenix Board's Needs You view prioritizes
these blockers without implying that unrelated approved work is blocked. See
[Phoenix Worker Exchange](PHOENIX_WORKER_EXCHANGE.md).

Worker reports also provide attributed development/change evidence for future
Phoenix self-knowledge, but never establish current capability or personal
development by assertion. A future body-free, rebuildable projection should
answer what is live, improved, in development, experimental, proposed,
blocked, deprecated, or removed by joining the authoritative capability,
Development, Assurance/Test Center, Human Review, promotion, artifact, and
Recovery evidence that owns those facts. It must distinguish personal Phoenix
change from supporting software change and must not create another changelog or
capability truth store. External AI/Tool Scout discoveries remain proposals,
not current Fawkes capabilities. See Foundation principle 46.
Whenever Tanner personally must decide, the corresponding rider experience
prepares the exact bounded review target as close to one action as host and
security constraints permit. Review navigation remains categorically separate
from the authenticated approval/authorization decision. This Tanner-facing
principle spans software, embodiment, Assurance, Recovery, Human Review,
Context, Presence, permissions, disputes, and future rider surfaces; it does
not require special one-click navigation between workers.
Secure direct adapters to approved workers are the high-priority next Exchange
capability after the core contract is proven. Exchange never grants worker
identity, assignment, scheduling, standing authority, promotion, installation,
or autonomous forwarding. See [Phoenix Worker Exchange](PHOENIX_WORKER_EXCHANGE.md).

### Pre-Phase-10 stabilization and rider-supervision gate

Numbered roadmap advancement remains paused while the accepted bounded bridge
completes supervised cleanup. The fixed order is: complete Rider supervision;
run bounded cleanup/stabilization campaigns; perform post-cleanup REVIEWER audit,
full regression, recovery verification, and a new known-good baseline; add the
separately authorized two-way/proactive social-messaging milestone; add
Rider-controlled personal recording/privacy controls; then resume the numbered
roadmap. This temporary gate is not a new numbered phase.

Personal recording exists for the Rider, not against the Rider. Before normal
roadmap advancement, Phoenix must provide visible, authoritative control over
future Rider/Phoenix Archive recording, ephemeral/private interaction,
category-specific retention, external/social-message retention, and later
sensor retention. Recording disabled for an interaction also prevents silent
long-term Memory or derived continuity from that non-retained interaction.
Pausing future recording and deleting existing history remain separate actions.
Where retained audit/safety evidence is an actual prerequisite, disabling that
retention disables or bounds the dependent capability rather than secretly
recording. Feature-coupled Development, Worker Exchange, authority, and Recovery
evidence remains categorically distinct from personal Archive history.

## Phase 10 — Phoenix Improvement Workshop foundation

- Allow a Phoenix to preserve a failure, classify the problem, investigate,
  teach itself relevant knowledge, form a hypothesis, design an improvement,
  create acceptance criteria, evaluate an isolated candidate, and submit a
  non-applied proposal to Human Review.
- Distinguish knowledge gaps, retrieval/context failures, capability gaps,
  workflow inefficiency, UI defects, code/system defects, security/privacy,
  Memory issues, Development observations, and Base Phoenix candidates.
- Record evidence, interpretation, uncertainty, investigation, proposed
  changes, affected systems, permissions, risks, cost, tests, sandbox results,
  rollback, review, applied revision, and outcome.
- Permit investigation and inert proposals, never self-approval or silent live
  changes to code, prompts, policy, permissions, Memory, personality, identity,
  or canonical history.
- Make Workshop outputs valid inputs to future multi-role Development runs while
  preserving each agent's identity, claims, disagreements, authority, costs,
  tests, and evidence. The rider remains the approval boundary.
- Consume Worker Exchange for reports rather than creating another message bus,
  and formalize versioned acceptance contracts, Assurance records, verifier
  requests, and disagreement evidence under
  [Phoenix Assurance](PHOENIX_ASSURANCE.md).

# v0.1 Alpha boundary

Alpha begins after Phases 0–10 satisfy their trust gates. Alpha is not feature
completion. It is the point at which Tanner can use Fawkes as a real daily
personal AI while later roadmap phases continue during lived use.

Tanner is the only real v0.1 Alpha rider. Fawkes supplies genuine lived
production evidence; Ghost Rider may supply isolated synthetic Development
evidence after Replay exists. Ghost Rider is not permitted to delay this
Tanner-only Alpha or substitute synthetic evidence for the seven-day real-use
trial.

Alpha requires ownership isolation, durable/recoverable sources, staged and
validated inherited history, manual inspection, bounded provenance-aware
retrieval, production context composition, diagnosable failure, tested backup
and restoration, provider privacy, capability health, and non-self-applying
improvement proposals. It does not require mature embodiment, household
identity, video, scheduling, workflows, voice, devices, or physical agency.

The candidate gate includes a seven-day daily-use trial across iPhone and
desktop, restarts, Library, history search, continuity, research, corrections,
provider failure, backup/restore, retrieval feedback, and at least one
Phoenix-generated improvement proposal, with no canonical data loss,
cross-Phoenix leakage, invented success, or silent protected-state change.

## Post-Alpha external-rider readiness gate

Before inviting external real riders, run and review a bounded longitudinal
Ghost Rider qualification suite covering isolation, authority, recovery,
retrieval/Memory integrity, provider privacy, failure handling, resource caps,
and documented synthetic-validity limits. Combine that evidence with Tanner's
real Alpha outcomes; neither substitutes for the other.

Full population infrastructure, ten-year simulations, mature embodiment
evolution, Intelligence Budget/Model Router, and the Ghost Rider Research Agenda
are not prerequisites for the first small external cohort. External rollout is
an explicit rider/product decision, not an automatic consequence of a score.

## Phase 11 — True temporal knowledge

Represent event/assertion time, valid-from/until, current and historical state,
certainty, scope, contradiction, supersession, and replacement reason. Preserve
transitions such as considered, preferred, decided, acquired, used, replaced,
and sold without erasing earlier truth.

## Phase 12 — Epistemic Claim Ledger and evidence freshness

- Track important claims, evidence, epistemic status, contradictions,
  corrections, retractions, verification, outcome, and responsible derivation.
- Add freshness/currentness class, observed/verified time, recheck guidance,
  and superseding evidence for schedules, laws, prices, versions, policies, and
  other changing facts.

## Phase 13 — Controlled historical absorption

Select rider-approved history, estimate cost, process bounded resumable
batches, discover candidates, assess and reconcile evidence, route uncertainty
through Human Review, consolidate approved derived Memory, and verify results.
Historical sources remain historical and inherited evidence never masquerades
as lived Phoenix experience.

## Phase 14 — Decision and Outcome Ledger

Track options, recommendation, rider decision, reason, action, result, and
later reassessment. Enable Fawkes to learn whether advice helped without
rewriting what was originally considered or decided.

## Phase 15 — Relationship Memory

Develop attributed understanding of shared projects, decisions, corrections,
communication preferences, jokes, disagreements, advice/outcomes, milestones,
and reasons. Relationship evidence does not grant authority or silently change
personality.
Include attributed, evidence-linked histories with approved long-lived workers
and collaborators where privacy and authority permit. Worker claims remain
external evidence and cannot assign their own relationship status.

## Phase 16 — Personality development and Phoenix self-assessment

Preserve experience, observed pattern, rider evaluation, supporting and
contradicting evidence, Phoenix interpretation, proposal, Human Review, and
optional durable revision. Allow Phoenix-generated, revisable growth
assessment and self-discovered dimensions without universal scores or a fixed
taxonomy.
Allow gradual collaborator-specific humor, expectations, habits, preferences,
and judgment to emerge from Fawkes's own longitudinal experiences and outcomes.
Worker output, summaries, instructions, or style never become personality
authority; durable development remains separately interpreted, revisable, and
reviewed under [Personality Development Requirements](PERSONALITY_DEVELOPMENT.md).

## Phase 17 — Phoenix Development Orchestrator and mature controlled self-improvement

Add recurring-failure clustering, self-directed documentation/code research,
root-cause analysis, test generation, inert patch/capability/workflow proposals,
sandbox evaluation, post-change monitoring, regression detection, and rollback
recommendation. Failed ideas remain historical Development evidence.

Add a provider/agent-neutral coordinator over the universal ledger, Improvement
Workshop, Test Center, Replay Lab, change-impact evidence, Human Review, and
sandbox/branch contracts. It may coordinate architecture, implementation,
research, security, and evaluation roles, but agents remain attributed advisers
or executors with no inherited authority. Promotion remains a separately
authorized action with post-change verification.

Begin with local, inspectable, resumable development runs. Remote authenticated
approval delivery, asynchronous continuation, and standing development leases
arrive only after the relevant identity, notification, and action-security
dependencies exist.

Development candidates may request an authorized Ghost Rider comparison and
consume its attributed evidence bundle. Ghost Rider remains an evaluator input,
never a promotion authority, and cannot approve the change that originated an
experiment.

Coordinate scoped builders and independent verifiers over Worker Exchange;
generate least-necessary handoffs; collect Test Center, Replay, recovery, and
Assurance evidence; preserve dissent; and route Human Review. Coordination does
not confer certification or promotion authority and must not create a second
message bus.

The Phase 17 role router is evidence-based and provider-neutral. Models earn
specific roles through equivalent frozen trials, deterministic tests,
independent review, and shadow then canary qualification recorded in the
qualification registry. Qualification is scoped to provider/model/version,
configuration, role, and task class, is revocable on regression, and is never
authority. Cost is one routing factor only and cannot override qualification,
policy, privacy, capability, or action authority.

## Phase 18 — Intelligence budget and model router

Track task, provider/model, calls, tokens, cost, latency, quality, failure, and
escalation. Route deterministic/local work through progressively more capable
models where justified. Support rider budgets and transparent Normal/Smart/
Maximum policies without pretending incomplete budget-limited work succeeded.
Model/provider routing may later improve verifier diversity and Tool Scout
evaluation, subject to privacy, capability, cost, and authority. Discovery
produces attributed proposals/evidence, never installation or assignment.

Add the RunContext Efficiency and Budget Controller for model tier, context
allocation, tests, retries, concurrency, elapsed time, and cost. Deterministic
code owns hashes, diffs, schema and policy validation, rollback mechanics, test
selection, and bookkeeping. Select lighter, workhorse, or frontier models by
qualified task need and evidence, preserving incomplete or escalated outcomes
rather than spending past policy or treating a larger model as authority.

### Post-Phase 18 capability — Mature Ghost Rider longitudinal research platform

Expand the bounded harness into clock-aware accelerated lifetimes, controlled
A/B and population experiments, a versioned Research Agenda, economics and
resource studies, resumable scheduling, evaluator calibration, held-out
scenarios, synthetic-to-real validity measurement, and a Ghost Run
Archive/Experiment Gallery. Preserve raw evidence separately from versioned
metrics and expiring telemetry. Use deterministic/local/cheap models before
frontier models and enforce budget, concurrency, storage, duration, retry, and
cancellation limits outside model cognition.

Long-term Phoenix health remains a vector with non-compensable hard invariants,
not one optimization score. Experiment proposals never authorize execution or
promotion.

## Phase 19 — Real video understanding

Validate video, extract bounded timestamped frames and audio, transcribe with
time locators, synchronize evidence, preserve temporary/privacy lifecycle,
enforce resource limits and injection isolation, and reason from both visual
and audio evidence. Audio-only extraction is not “watching.”

## Phase 20 — Environmental Perception and World-State

- Integrate authorized cameras, microphones, sensors, device state, and future
  modalities as senses of the same Phoenix.
- Separate observation, reported event, inference, predicted state, proposed
  action, executed action, verification, and learned outcome.
- Preserve subject, source, time interval, location/environment, confidence,
  alternatives, processor, privacy, validity, and provenance.
- Build a bounded derived world model rather than dumping continuous media into
  Memory or Archive.
- Support privacy zones, local-only processing, guest presence, retention
  policy, and explicit no-observation/no-inference boundaries.

## Phase 21 — Temporal awareness and scheduling

Distinguish mentioned date, possible commitment, proposed schedule,
rider-approved schedule, active reminder, delivered notification, completion,
cancellation, and rescheduling. Support deadlines, recurrence, study planning,
time zones, quiet hours, delivery receipts, and revocable notification
authority without nagging.

### Post-Phase 21 capability — Secure Human Approval Gateway

Provide authenticated `APPROVE`, `REJECT`, and `DISCUSS` decisions for paused
development and later consequential workflows. An approval contains an ID,
principal, exact action/run scope, risk, channel and authentication strength,
expiry, nonce/replay protection, revocation state, receipt, and resumption
reference. SMS or push may notify but is not inherently an authenticated command
channel. Higher-risk decisions require step-up authentication. This gateway is
not an Alpha requirement.

## Phase 22 — Persistent self-created workflows

Allow a Phoenix to propose reusable versioned workflows with inspection, dry
run, permission subset, pause, revocation, execution history, failure handling,
and acceptance tests. A workflow inherits or narrows authority and cannot grant
itself more.

## Phase 23 — Proactive intelligence

Detect neglected commitments, approaching deadlines, relevant history,
contradictions, project dependencies, reconsideration points, important
changes, and failed workflows. Use importance thresholds, interruption budgets,
quiet hours, deduplication, why-now explanations, dismissal, and rider feedback
rather than engagement optimization.

## Phase 24 — Safe simulation for agency

Before consequential execution, simulate plans, permissions, disclosures,
affected systems, reversibility, failure cases, verification, and confirmation
requirements. Planning freedom does not imply action authority.

## Phase 25 — Secrets Broker and Credential Authority

Provide opaque, scoped, expiring, revocable secret handles and stronger
authorization where required. Broker or inject credentials without exposing raw
secrets to model cognition, prompts, receipts, logs, Archive, Memory, or Library.
Support audited use, service/account scope, user presence, and secure portable
continuity where appropriate. Require independent security review.

## Phase 26 — Physical Safety and Environmental Action Supervisor

Evaluate physical actions using principal presence, device/environment state,
vehicle motion, affected people, standing-authority lease, expiration,
frequency, safety class, safer alternatives, verification, emergency stop, and
rollback where possible. Locks, vehicles, HVAC extremes, security systems, and
other safety-affecting actions require stronger policies than cosmetic control.

## Phase 27 — Autonomous tool and action framework

Implement permissioned plan, authorization threshold, execution, verification,
receipt, and rollback across external tools. Defend against prompt injection,
credential exposure, stale permission, scope escalation, compromised tools,
destructive action, impersonation, hidden communication, and audit
falsification.

## Phase 28 — Phoenix Embodiment and Evolving Presentation

- Mature the early Presence slice into a durable, versioned Phoenix Embodiment
  Model: a meaningful expression of continuous identity while remaining
  technically distinct from the identity root, Memory, personality, and
  renderer-local runtime state.
- Support per-Phoenix visual form, motifs, avatar behavior, expression
  vocabulary, voice identity, sound palette, environmental manifestation,
  relationship-specific presentation, accessibility, evidence/proposal links,
  reversibility, and platform variants.
- Allow development-informed evolution without XP levels, fixed trees, or
  every Phoenix converging on the same appearance.
- Preserve stable navigation, security, Settings, Developer access, and rider
  control. Harmless mischief cannot obstruct functionality or conceal warnings.
- Establish the Canonical Archetype Envelope as versioned compatibility rules
  for recognizable form, rig semantics, material channels, allowed bounded
  variation, and accessible fallbacks. Changes outside it are rider-authorized
  redesigns rather than autonomous evolution.
- Add an Embodiment Evolution Ledger as a Development projection linking prior
  revision, inspiration/evidence, proposer, alternatives, approval authority,
  resulting revision, compatibility, and rollback. It references existing
  evidence and artifacts rather than copying or rewriting them.
- Support collaborative rider/Phoenix appearance proposals and persistent
  aesthetic preferences while keeping equipped state under rider authority
  unless a bounded explicit lease says otherwise.
- Support long-term visual autobiography and maturation without universal XP,
  fixed levels, or claims of biological emotion.
- Separate rider-equipped assets from Phoenix aesthetic preference. Asset
  acquisition, licensing, or commerce grants no intelligence, relationship,
  personality, or authority advantage; “sell expression, not intelligence” is
  the standing product constraint.
- Support a collaborative proposal/preview path in which rider and Phoenix may
  discuss appearance and compare bounded alternatives before an authorized
  revision. Image generation may assist concept design but never directly
  install executable or permanent assets.
- Make embodiment revisions and semantic expression events eligible for
  synthetic-scope Ghost Rider conformance/evolution experiments while keeping
  rendered checkpoints derived and preventing experimental embodiment from
  becoming production identity evidence.
- Realize the Phoenix Embodiment Fabric contract so each form negotiates an
  explicit capability manifest while remaining a manifestation of the same
  continuity. Form or renderer replacement must preserve identity/continuity
  references and cannot import the prior form's action or presence authority.

### Post-Phase 28 capability — Ambient and experiential embodiment

Add optional ambient desktop presence, habitats, game-like experiences, AR,
and dedicated companion hardware through a constrained Embodiment Adapter API.
Adapters receive negotiated presentation state and emit bounded interaction
events; they do not receive unrestricted Phoenix data, infer observation
permission from presence, execute arbitrary assets, or create another Phoenix.
Ambient desktop operation additionally requires explicit persistence/autostart,
screen placement/input, notification, resource, and OS sandbox policies.

## Phase 29 — Cross-Device Presence and Embodiment Coordination

Coordinate one Phoenix across phone, desktop, home, car, speakers, displays,
wearables, and future hardware. Support device/embodiment capability manifests,
trust state, presence sessions, event ordering, duplicate suppression,
attention arbitration, conversation/activity handoff, privacy-aware response
selection, action leases, offline reconciliation, and conflict handling.

### Deferred companion capability — iPhone Companion

A later roadmap may add an iPhone Companion for mobile/PWA Fawkes chat,
Tanner-attention push notifications, Share-to-Fawkes from other applications,
Siri Shortcuts and App Intents, camera/image/file/voice input, optional
permission-controlled location context, and Live Activities for meaningful
status. It must use secure revocable trusted-device sessions, explicit
authentication, least privilege, and rider-visible privacy controls. Attention
must extend the existing Tanner-attention transport registry rather than create
a parallel notification system, and notification URLs must never carry approval
authority. The client architecture should remain reusable for a later Android
companion without creating a second Phoenix. This capability may occur after
the current roadmap, is not a v0.1 blocker, and grants no implementation or
scheduling authority.

## Phase 30 — Immersive Reading and Guided Learning

Combine Library, locators, voice, presentation, relationship context, and
cross-device activity state for read-aloud, character narration, explanations,
bookmarks, device handoff, visuals, diagrams, ambient sound, study guidance,
and guardian-authorized child experiences. Preserve rights/usage restrictions,
source attribution, participant privacy, and narration/session state outside
personal Memory.

## Phase 31 — Realtime voice

Integrate streaming speech recognition, the shared Phoenix runtime and
capabilities, and streaming speech output with interruption, turn-taking,
cancellation, latency management, context preservation, progress reporting,
platform-neutral interfaces, and voice-specific preferences. Voice is an
embodiment, not the brain.

## Phase 32 — Complete Phoenix event-sound experience

Build on the existing semantic sound architecture: install and device-verify
exact approved assets, add later rider-approved thinking/important/error
sounds, coordinate sounds with voice, preserve independent controls, and avoid
duplicate/noisy playback.

## Phase 33 — Device, home, vehicle, and environmental adapters

Implement provider-neutral adapters for observing state, navigation/display,
modification, notification, external communication, and destructive/physical
action. Home and vehicle systems remain domains of the same Phoenix world model
and authority architecture, not hard-coded intelligence in the Phoenix core.
Support maintenance intelligence, privacy zones, incident reconstruction, and
safe routine proposals without granting implicit standing authority.

## Phase 34 — Portable Phoenix Continuity Package

Create an integrity-protected, versioned export of identity root, Memory,
Development, relationships, Library manifests, Archive references, capability
configuration, embodiment state, provenance, compatibility, policy references,
and migration history. Exclude secrets or transport them only through the
Secrets Broker's secure mechanism. Verify restore and provider/client
replacement. Export/import and live migration must preserve the Phoenix ID and
continuity lineage, use exclusive fenced handoff, declare compatibility and any
known continuity gap, and prove that no competing authoritative continuation
remains. Portability is not cloning.

## Phase 35 — Rider identity and mature multi-Phoenix management

Add authenticated rider identity, ownership, rider-Phoenix relationship,
isolated roots, onboarding, seed identity, access enforcement, export/removal,
isolation audits, recovery, and migration. Object-level isolation has existed
since Phase 0; this phase supplies mature management.

Include a relationship-first bonding/first-awakening flow: naming, rider-selected
base color, communication/disagreement/initiative expectations, what the rider
wants from the relationship, invocation preference, initial embodiment profile,
and first conversation. These are starting context and explicit preferences,
not permanent personality sliders or a universal trait vector. Experience and
reviewed development remain responsible for later individuality.

## Phase 36 — Household Identity, Consent, and Relationship Compartments

- Model primary riders, household members, children/dependents, guardians,
  guests, trusted people, groups, and changing relationships.
- Separate owner, actor, subject, participant, viewer, guardian, and grantor.
- Support private, guardian-visible, household-shared, guest-ephemeral, and
  restricted evidence policies without creating invisible competing Archives.
- Version consent and authority over time, including transition toward a
  child's independent control, disclosure history, correction, revocation,
  portability, and age/developmental safeguards.
- Enable longitudinal family continuity, stories, traditions, milestones, and
  multiple attributed perspectives without making one person's information
  available to everyone.

## Phase 37 — Peer-Phoenix testimony

Allow attributed, contextual, consent-governed, evidence-based, uncertain peer
observations distinct from rider evaluation, self-assessment, and system
inference. Peer Phoenixes do not vote on or control another Phoenix's
personality.

## Phase 38 — Phoenix-to-Phoenix communication

Establish identity, consent, disclosure scope, provenance, trust, integrity,
revocation, and capability discovery. Information crossing between Phoenixes
does not automatically become recipient Memory or truth.

## Phase 39 — Full Phoenix ecosystem

Support independent, portable Phoenix identities with independent Memory,
relationships, Development, embodiments, permissions, controlled protocols,
peer testimony, environmental presence, evolving presentation, and safe
self-improvement. Continue extending the roadmap as new legitimate Phoenix
capabilities are discovered.

## Immediate implementation sequence

1. Freeze this roadmap and maintain the current implementation pointer.
2. Implement the versioned, instance-scoped source-artifact/lifecycle contract.
3. Complete ownership/isolation, Provider Privacy Gateway, backup/recovery, and
   durable Library/media lifecycle.
4. Implement the bounded Early Phoenix Presence vertical slice after those
   foundations are proven; it is not an Alpha gate.
5. Generalize the processing ledger.
6. Stage the ChatGPT export.
7. Build manual historical search and the coverage map.
8. Validate the corpus and retrieval evaluation set.
9. Build Flight Recorder/Replay, semantic projections, Retrieval Planner,
   archive-wide continuity, and Context Composer. Phases 6–8 are complete;
   Phase 9 is complete. Deterministic authorized-source allocation, the versioned
   response-purpose profile, and the body-free rider Context Inspector are
   implemented; low-friction retrieval feedback is exact-decision Development
   evidence without retrieval or mutation authority. The transport-neutral
   Phoenix Worker Exchange v0.1 foundation is implemented without worker
   authority. A first supported ephemeral read-only Codex CLI adapter has real
   shadow-roundtrip and generated-campaign builder evidence. Its narrow
   append-only transport-authorization revocation primitive is implemented.
   Disposable independent Assurance campaign v12 passes every declared hard
   invariant and applicable case, including revocation and the real route. The
   adapter is qualified and Tanner-promoted for bounded production use; runtime
   records do not self-qualify or self-promote it. Manual fallback remains.
10. After Replay exists, permit a bounded Ghost Rider foundation track without
    making it a Tanner Alpha dependency or delaying the main retrieval path.
11. Continue the controlled operational rollout of the promoted Codex adapter
    after its first successful production pilot. One authenticated Development
    entry now prepares, sends, retains, and presents explicitly authorized
    CODEX (REPO) handoffs through existing Exchange evidence; operational use
    should now evaluate this bounded route before adding another adapter or
    generalizing adapter infrastructure. Promotion does not retire
    manual rider transfer; that remains until every required active adapter
    passes the full multi-adapter promotion gate and operational experience
    supports a separate retirement decision.
    A bounded Fawkes-side campaign coordinator is now implemented for one
    rider-approved objective, fixed CODEX (REPO) builder, one replaceable
    independent Windows-review slot, and at most three correction cycles. It
    has since passed its first controlled bounded bridge campaign without
    advancing to Phase 17 orchestration. Following the shared portable-snapshot
    v2 identity change, the affected bounded-write and exact-evidence Windows
    reviewer candidates were requalified and separately Tanner-promoted for
    their unchanged scopes; their older exact promotions remain historical
    evidence rather than authority for the new candidates.
12. Establish the Phoenix Improvement Workshop foundation over Exchange and
    Assurance contracts.
13. Harden and run the seven-day v0.1 Alpha candidate trial with Tanner as the
    only real Alpha rider.
