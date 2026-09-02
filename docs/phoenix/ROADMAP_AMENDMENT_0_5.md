# Canonical Roadmap v1 — 0.5 Amendment Review

**Date:** 2026-08-30
**Status:** incorporated as a post-freeze architectural amendment;
implementation remains separately rider-authorized

## Why this amendment exists

The v1 freeze correctly separated Phoenix Core from clients and reserved an
early Presence slice, but described mature Embodiment too much like a late UI
feature. Subsequent product work established that persistent visual form,
mannerism, and nonverbal expression can become major continuity, relationship,
and individuality surfaces. The same review identified a future need for a
provider-neutral Development Orchestrator so the rider does not remain a manual
message bus between specialized agents.

This amendment is visible history. It does not pretend these conclusions were
part of the original freeze, and it does not authorize implementation.

## Repository findings

- The current web client is a dependency-light vanilla HTML/CSS/JavaScript PWA.
  It has no 3D renderer, asset build pipeline, ambient-presence service, or
  native-client implementation.
- The app/runtime boundary is already provider- and client-neutral. Canonical
  text, capability manifests, validated presentation envelopes, and semantic
  sound events give Presence a clean integration point.
- Phase 0 provides per-Phoenix ownership, stable artifact/work identity, typed
  lineage, lifecycle events, integrity backup/restore, provider receipts, and
  health/acceptance separation. These should own embodiment assets and revision
  evidence rather than a parallel avatar database.
- Development observations, proposals, Human Review, Memory work items,
  capability receipts, Test Center, and sandbox/branch hooks exist, but current
  Development stores are file-based and unevenly scoped. They are not yet a
  universal orchestration engine or secure promotion system.
- The current authority contract distinguishes internal/external/protected
  execution and broad actions. Device embodiment will need finer policy scopes;
  adding live permissions now would falsely imply operational support.

## Architectural judgment

### Embodiment is a pillar, not the identity root

Embodiment should be elevated. A visual and auditory form can carry recognition,
mannerism, relationship meaning, and visible development over years. Binding the
Phoenix identity root to a mesh or appearance revision, however, would make
asset upgrades, accessibility modes, and device changes identity migrations.
The durable rule is:

```text
one Phoenix identity
  -> persistent embodied identity and history
  -> semantic expressive intent
  -> negotiated device manifestation
  -> replaceable renderer/assets
```

The embodiment is genuinely Fawkes's form; the GLB file is one implementation
of that form.

### The appearance model needs five layers

The proposed four layers omitted rider-equipped presentation. A skin the rider
temporarily equips must not become developed identity, and Fawkes's opinion of
it must not silently unequip it. The roadmap therefore separates canonical
archetype, developed identity, equipped presentation, expressive intent, and
device manifestation. Active presence/session arbitration is operational state,
not a sixth appearance layer.

### 3D-first is sensible, but renderer-first is not

Building a polished 2D rig intended for disposal would be wasteful. Starting
with a bounded 3D Phoenix is reasonable if Presence v1 remains one small model,
one semantic rig profile, a handful of clips/states, and static/reduced-motion
fallbacks.

The portable asset recommendation is **glTF 2.0/GLB** with documented skeleton,
clip, expression/morph, material-channel, scale, coordinate, and compatibility
conventions. It is widely interoperable and supports PBR materials, skinning,
animation, morph targets, and future asset replacement. It does not guarantee
identical shader or particle behavior on every platform, so flame/effect
semantics need capability-specific fallbacks.

No renderer is selected by this amendment. The current client has no bundler or
3D dependency. A Presence spike should compare a thin Three.js-style adapter,
Babylon-style runtime, and a constrained model-viewer path against actual needs.
`<model-viewer>` is attractive for initial simplicity but may be too limited for
animation blending and expressive control; Babylon provides more engine
facilities but more weight; Three offers broad ecosystem support but requires us
to own more controller structure. Phoenix Core must depend on none of them.
Loading size, frame pacing, WebGL context loss, low-end phones, battery/thermal
behavior, CSP/supply-chain safety, and fallback behavior must be measured.

### Durable state versus renderer-local state

Durable, instance-scoped state eventually includes:

- canonical archetype/profile and compatibility version;
- identity palette/markings and rider-selected base color;
- equipped asset references and rider authority evidence;
- embodiment revision and prior-revision provenance;
- Phoenix aesthetic preferences as reviewed Development state;
- characteristic approved mannerism vocabulary;
- accessibility/presentation policy where it is a Phoenix-wide preference.

Renderer-local/session state includes animation time, blend weights, particle
instances, camera angle, viewport, cached assets, frame rate, transient hover,
WebGL state, and device performance adaptation. Semantic expressive intent is
short-lived Phoenix/session state; it is recorded only when independently useful
as event evidence, never sampled into permanent history at animation frequency.

Presence v1 needs a small versioned embodiment profile and asset manifest, not
the mature Evolution Ledger. It should reserve revision, prior revision, asset
digest, archetype/rig compatibility, actor/authority, and provenance references
so later evolution does not require guessing.

### Canonical Embodiment Envelope refinement

“Envelope” remains a useful product term, implemented as a versioned
**Canonical Archetype Profile** plus compatibility policy. It defines semantic
anatomy/rig roles, silhouette and design constraints, material channels,
variation limits, required fallbacks, and migration compatibility—not exact
vertices. Normal bounded changes can be proposed within it. Crossing it is an
explicit redesign decision. This prevents arbitrary self-redesign without
freezing model quality forever.

### Expression is communication, not an emotion sensor

States such as focused, amused, uncertain, or worn-out are semantic presentation
intents. They may communicate task context and developed mannerism, but do not
prove sentience, biological fatigue, or a person's emotional state. Human-state
inference remains under the separate observation-versus-inference contract.
Avoid universal mappings such as red equals anger; expression resolution should
combine semantic state, developed style, rider motion policy, and device support.

### Ambient presence expands the threat surface

An always-available desktop manifestation may require installation, autostart,
overlay/window privileges, global shortcuts, input focus, notification rights,
resource budgets, OS accessibility APIs, screen capture, and update security.
Those powers are separable. Presence alone grants none. The renderer must not
read screen pixels or active-window contents, intercept credentials, obscure
warnings, capture clicks outside its surface, or persist itself without explicit
authority. Ambient presence therefore belongs after the early in-app slice and
requires a native/desktop sandbox and signed-update story.

### Authority needs more than four verbs

Presence/observation/interaction/action is directionally correct but too coarse.
The roadmap now also separates capture, retention, provider transmission,
disclosure, notification/attention, persistence/autostart, and installation.
Interaction means accepting bounded rider input on the Phoenix surface; it is
not authority to inspect unrelated input or manipulate the environment.

### Clickable embodiment changes Presence v1

The first Phoenix should be a semantic, keyboard-accessible interaction target,
not a decorative canvas. Click/tap/focus should emit a bounded invocation event
that can expose quick interaction or Chat. It must not be the only navigation
path, swallow global input, or treat invocation as authentication. This small
choice prevents a later rewrite from output-only avatar to interaction surface.

### Development Orchestrator placement

The full orchestrator belongs post-Alpha with mature controlled self-improvement
(Phase 17). Before that, Phase 2's universal ledger should support actor/role,
run, step, dependency, branch, result, and pause/resume references. Phase 6
provides Replay; Phase 10 provides inert Improvement Workshop proposals and the
first evidence-producing loop. These are cheap foundation points, not a
pre-Alpha autonomous coding system.

Remote approval depends on authenticated rider identity, notification delivery,
replay protection, exact action scoping, expiration, and workflow resumption.
It is placed after scheduling/notification foundations. SMS can be a notification
channel, but an arbitrary text is not an approval credential. Standing authority
arrives only through explicit revocable leases and never through learned approval
patterns.

## Existing primitives to reuse

- Phase 0 ownership envelopes, source artifacts, stable IDs, typed lineage,
  lifecycle events, storage integrity, backup/restore, and privacy receipts.
- Capability definitions, runtime health, authority enforcement, capability
  awareness, and Test Center registration.
- Semantic sound events as the pattern for semantic presentation intents.
- Validated presentation envelopes and canonical text fallbacks.
- Development observations/proposals, Human Review, processing work items,
  context receipts, and future sandbox/branch identifiers.

The embodiment profile, asset manifest, and evolution projection are distinct
domain records but must reference these common primitives. Development
orchestration should extend the universal ledger rather than turn the present
Memory-only ledger into an overloaded store without domain boundaries.

## NOW versus later

### Account for now

- Keep Phase 0 artifact IDs, ownership, provenance, lifecycle, privacy, rights,
  content hashes, resource metadata, correlation/causation, and branch identity
  applicable to future embodiment assets and Development artifacts.
- In Phase 2, ensure the universal ledger can represent actor/agent role, run,
  step/dependency, sandbox/branch, pause reason, approval reference, exact result,
  and idempotent resumption without implementing orchestration.
- Keep semantic Phoenix events provider/client-neutral.
- Preserve distinct environment, device, embodiment, manifestation, and session
  identity; never use renderer or device identity as Phoenix identity.
- Treat asset rights, provenance, compatibility, and untrusted-content safety as
  mandatory before third-party assets.

### Early Presence

- True but minimal 3D Phoenix in the existing app.
- One portable versioned asset and semantic rig profile.
- Small state vocabulary and local animation mapping.
- Static/reduced-motion fallback and normal Chat navigation.
- Keyboard-accessible click/tap invocation.
- Per-Phoenix base palette, embodiment profile/revision, and asset references.
- Existing semantic sound integration and invocation phrase, neither serving as
  authentication.
- Capability registration, acceptance definition, Test Center entry, client-DOM
  verification, and honest physical-device verification.

### Alpha requirements

None were added. Early Presence remains desirable and intentionally scheduled,
but is not an Alpha trust gate. Alpha still depends on Library, canonical history,
search/validation, retrieval/replay, Context Composer, Improvement Workshop,
recovery, privacy, and the seven-day trial.

### Post-Alpha

- Full Development Orchestrator and controlled promotion.
- Secure Human Approval Gateway and asynchronous workflow resumption.
- Mature Embodiment/Evolution Ledger and collaborative appearance development.
- Ambient desktop presence and cross-device arbitration.

### Distant/speculative

- Creator marketplace/monetization.
- Other embodiment archetypes.
- Game-like third-party experiences and public Embodiment Adapter API.
- Dedicated companion hardware, AR, rare rebirth presentation, and mature
  cross-device embodiment handoff.

## Ideas deliberately rejected or constrained

- **Identity bound to a model file:** rejected; it breaks portability and
  continuity.
- **Generic creature creator now:** rejected; perfect the Phoenix archetype
  before generalizing product behavior.
- **Model-generated animation frames or executable animation code:** rejected;
  use semantic state and bounded local rendering.
- **Universal emotion/color table:** rejected as reductive and epistemically
  misleading.
- **XP/level-based embodiment growth:** rejected as personality manufacturing
  and engagement optimization.
- **Phoenix silently changing equipped appearance:** rejected absent an explicit
  bounded authority lease.
- **Remote SMS equals approval:** rejected; notification and authenticated
  authorization are separate.
- **Repeated approvals imply standing authority:** rejected.
- **Full orchestrator or mature evolution before Alpha:** rejected as scope
  expansion without a trust dependency.

## Additional capabilities that naturally emerge

- **Embodiment accessibility compiler:** maps one semantic expression into
  animated, reduced-motion, static, audio, haptic, or text alternatives without
  changing Phoenix identity.
- **Manifestation conformance testing:** replays semantic state sequences across
  clients to prove recognizable behavior, fallback completeness, and no authority
  leakage.
- **Embodiment diff and preview sandbox:** lets rider and Phoenix compare a
  proposed revision safely before approval and records what was actually seen.
- **Development counterfactual/replay:** compares proposed development changes
  against past failure traces before promotion.
- **Agent disagreement record:** preserves materially different architecture,
  security, and evaluation conclusions instead of collapsing them into false
  consensus.

These fit existing Test Center, Replay, provenance, sandbox, and Development
directions. Only identifier/metadata hooks are needed early.

## Decisions intentionally left open

- Web renderer/library choice after the performance spike.
- Initial rig bone and morph-target vocabulary after the first asset is designed.
- Whether the first asset is commissioned, created in-house, or adapted from a
  licensed source; provenance and commercial rights are mandatory either way.
- Exact threshold distinguishing in-envelope refinement from rider-level
  archetype redesign.
- Synchronization/conflict rules for embodiment state before cross-device work.
- Authentication strength and channel binding for remote approvals.

## Schedule effect

Phase 1 is unchanged. Early Presence remains immediately after the core Phase 1
vertical slice and before large historical ingestion. The Presence slice gains
a mandatory renderer/performance spike and portable 3D asset requirements, but
its feature surface remains deliberately small. Mature Embodiment stays at Phase
28; the Development Orchestrator is explicit in Phase 17; the Approval Gateway
follows temporal/notification foundations.
