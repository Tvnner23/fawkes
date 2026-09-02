# Cross-worker Improvement Proposals

This is a review register for portable cross-worker proposals. Entries are
non-authorizing: recording them does not approve implementation, assign a
roadmap phase, install a tool, or promote experimental work.

## Versioned Semantic Expression Interface

- **Discovered by:** Embodiment specialist (Codex / Blender MCP worker)
- **Area:** Presence software and embodiment integration
- **Observation:** Raw Blender bone names would couple Phoenix expressive intent
  to one asset and rig revision.
- **Proposed upgrade:** Define a versioned, provider/body-neutral semantic
  expression interface between expressive intent and renderer-specific rig
  mappings. Illustrative channels include gaze, lid openness, brow pitch, crest
  spread/sweep/asymmetry, head tilt, wing openness, tail energy, and flame
  intensity; the vocabulary should remain extensible.
- **Fawkes principle fit:** Preserves one Phoenix's expression across replaceable
  bodies and renderers without making an asset the identity root.
- **Benefit:** Portability, safer asset evolution, and cross-device consistency.
- **Cost/complexity:** Requires software/embodiment version negotiation,
  fallbacks, and validation fixtures.
- **Risks/tradeoffs:** A premature fixed vocabulary could flatten expression or
  become another renderer-specific contract.
- **Authority/security impact:** None proposed; expression intent must not grant
  device, environmental, or identity authority.
- **Reversibility:** High while introduced as a versioned adapter contract.
- **Validation:** Presence and embodiment cross-review, mapping conformance,
  missing-channel fallbacks, reduced-motion and device acceptance.
- **Dependencies:** Legitimate Fawkes GLB and future Presence scope.
- **Cross-system impact:** Presence, presentation, embodiment asset contracts,
  Test Center, future personality/expression interpretation.
- **Recommendation:** Approved roadmap direction: prototype jointly before
  substantial production animation; stabilize only after representative body
  and software evidence. No runtime implementation is authorized here.

## Automated Fawkes GLB Readiness Gate

- **Discovered by:** Embodiment specialist (Codex / Blender MCP worker)
- **Area:** Presence asset acceptance and Test Center
- **Observation:** Manual GLB inspection alone can miss export, rig, animation,
  material, scale, and compatibility defects.
- **Proposed upgrade:** Add a deterministic automated readiness gate tied to the
  existing Presence asset contract and export validation.
- **Fawkes principle fit:** Keeps embodiment production claims evidence-based and
  protects reliable manifestation of the same Phoenix.
- **Benefit:** Earlier defect detection and portable acceptance evidence.
- **Cost/complexity:** Requires representative fixtures, parser/toolchain
  selection, platform tolerances, and maintenance across GLB revisions.
- **Risks/tradeoffs:** A narrow validator may produce false confidence and cannot
  replace rider-visible render acceptance.
- **Authority/security impact:** Asset inspection only; it must not install
  tooling, approve an asset, or promote a revision by itself.
- **Reversibility:** High if implemented as an isolated acceptance adapter.
- **Validation:** Known-good/known-bad fixtures plus real desktop/mobile visual,
  lifecycle, accessibility, performance, and fallback acceptance.
- **Dependencies:** Finished legitimate Fawkes GLB and separately authorized
  Presence implementation scope.
- **Cross-system impact:** Presence, Test Center, processing ledger, artifact
  provenance, provider/tool permissions.
- **Recommendation:** Approved progressive roadmap direction: begin lightweight
  structural/export evidence during prototyping, then mature at pre-animation,
  pre-Presence, and Test Center/promotion gates. No validator is implemented by
  this record.

## Protected Pose-regression Library

- **Discovered by:** Embodiment specialist (Codex / Blender MCP worker)
- **Area:** Embodiment diagnostics and cross-worker validation
- **Observation:** Pose and deformation regressions need portable evidence that
  survives worker and tool replacement.
- **Proposed upgrade:** Define a protected, versioned pose-regression evidence
  library containing approved diagnostic poses, expected observations, asset and
  rig versions, render conditions, and results without treating diagnostics as
  Phoenix Memory or canonical lived history.
- **Fawkes principle fit:** Preserves evidence across replaceable embodiment
  workers and renderers while keeping authority domains distinct.
- **Benefit:** Repeatable weighting/rig regression detection and clearer
  software–embodiment handoffs.
- **Cost/complexity:** Storage, versioning, render comparability, review policy,
  and potentially large media artifacts.
- **Risks/tradeoffs:** Diagnostic evidence could be mistaken for canonical
  embodiment identity or overfit one renderer.
- **Authority/security impact:** Requires protected artifact ownership and
  explicit promotion/review rules; no automatic personality or identity effect.
- **Reversibility:** Medium; schemas can evolve, while accepted evidence history
  should remain attributable and append-only.
- **Validation:** Known deformation regressions, cross-version comparison,
  provenance/integrity checks, and reviewer attribution.
- **Dependencies:** Semantic expression/rig contract decisions and future
  embodiment acceptance scope.
- **Cross-system impact:** Presence, artifact storage/recovery, processing
  ledger, Test Center, Replay concepts, Human Review.
- **Recommendation:** Preserve as a design proposal for future Presence and
  embodiment cross-review; do not implement in the current governance slice.

## Semantic Island Manifest

- **Discovered by:** Embodiment specialist (Codex / Blender MCP worker)
- **Area:** Revision-local topology ownership and diagnostics
- **Observation:** Disconnected feather/component islands make topology-based
  ownership more reliable than proximity weighting, while component numbers are
  unstable across topology revisions.
- **Proposed upgrade:** Prototype a versioned, body/topology-revision-local
  manifest of component fingerprints, semantic declarations, intended owners,
  permitted blends, and exclusions.
- **Fawkes principle fit:** Improves repeatable embodiment evidence without
  turning body topology into Phoenix identity.
- **Benefit:** Safer reweighting, portable handoffs, and regression diagnostics.
- **Cost/complexity:** Fingerprint algorithms, migration/invalidation, storage,
  and review policy.
- **Risks/tradeoffs:** Brittle over-canonicalization could mistake revision-local
  topology for universal anatomy or continuity.
- **Authority/security impact:** Diagnostic evidence only; no identity,
  promotion, or write authority.
- **Reversibility:** High while prototype-only and explicitly invalidated on
  topology change.
- **Validation:** Known component changes, collision/staleness tests, weighting
  regressions, and cross-worker inspection.
- **Dependencies:** Body revision identity, artifact provenance, recovery, and
  future embodiment acceptance evidence.
- **Cross-system impact:** Embodiment, Presence, Test Center, Assurance, and
  checkpoint dependency closure.
- **Recommendation:** Prototype only near embodiment/GLB acceptance; do not
  canonize island membership across body revisions.
