# Phoenix Embodiment Development Gates

**Contract ID:** `phoenix.embodiment_development_gates`  
**Version:** 1.0  
**Status:** Approved architectural direction; prototype evidence recorded; runtime automation not implemented

## Purpose

This contract lets embodiment mature in parallel with the numbered software
spine while defining the points where embodiment and Presence software must
synchronize. It does not promote an asset, grant write authority, or replace
the [Presence v1 Asset Contract](PRESENCE_ASSET_CONTRACT.md).

## Evidence-led deformation rule

Rig development proceeds in this order:

```text
semantic ownership
-> topology ownership
-> legitimate transition regions
-> measured deformation
-> additional complexity only when evidence requires it
```

Joint budget is a ceiling, not a reason to add joints. One bone is not presumed
universally sufficient.

The right-brow ownership experiment in
`Fawkes_DevBody_v007_RightBrowOwnership.blend` reduced right-brow membership
from 361 to 192 vertices by removing 169 vertices in 12 unrelated disconnected
components. Tested jaw-adjacent and opposite-side leakage fell to zero without
new bones, topology, or changes to known-good head/jaw architecture. This is
builder evidence for an experimental candidate, not production promotion or
authority to generalize the repair to the left brow.

Current reported lineage is:

- `Fawkes_DevBody_PreWeights.blend`: deeper protected legacy recovery state;
- `Fawkes_DevBody_v006.blend`: known-good pre-prototype baseline;
- `Fawkes_DevBody_v007_RightBrowOwnership.blend`: successful experimental
  candidate, builder validation and Tanner visual review complete with PASS,
  independent verification pending, rollback target v006.

Tanner's visual PASS removes the rider-review blocker only. Independent
verification still blocks promotion and using v007 as authority to generalize
the repair to the left brow; unrelated embodiment investigation may continue.

## Authoring and exported skeleton accounting

One generic “joint count” is insufficient. Current inspected v007 export
evidence reports 53 Blender bones, 41 Blender `use_deform` bones, 54 GLB skin
joints, 42 GLB joints carrying exported weights, and 12 GLB joints without
direct weights. Forty deform-enabled Blender bones carry skin weights;
non-deform `jaw_base` carries exported weights; deform-enabled `jaw` has no skin
weights but remains runtime-relevant because the rigid lower-jaw object is
bone-parented to it. One exporter-generated `neutral_bone` is associated with
otherwise unweighted exported geometry. No animation channels exist yet.

These are artifact observations, not universal exporter rules. Validation must
report separately:

- total authoring bones and deform-enabled authoring bones;
- maximum joints per exported GLB skin and unique exported joint union;
- weighted, animated, hierarchy-only, rigid-parent, and synthetic/exporter
  joints where determinable.

Maximum joints per skin is the current primary compatibility metric; unique
union is also reported for multi-skin assets. Software/runtime evidence is
required before changing the existing production ceiling.

## Progressive GLB readiness

The GLB readiness direction matures by gate:

1. **Prototype:** geometry, materials/textures, authoring bones, exported skin
   joints, influences, unweighted geometry, size, extensions, and external
   dependencies.
2. **Pre-animation:** authoring-to-runtime skeleton mapping, neutral/reference
   pose, animation inventory, baking rules, and deterministic export.
3. **Pre-Presence:** actual runtime load, playback/blending, semantic
   resolution, reduced-motion behavior, and visual smoke checks.
4. **Promotion/Test Center:** automated thresholds, known-good/bad fixtures,
   regression evidence, restore evidence, and explicit promotion state.

## Semantic Expression interface

A versioned, manifestation-neutral Semantic Expression interface should be
prototyped before substantial production animation, then stabilized only after
representative software and body evidence. Fawkes expressive intent targets
semantics rather than raw Blender bone names, renderer internals, or executable
animation code. Gaze, lids, brow/crest behavior, head emphasis, chest, wings,
tail, flame, intensity, and speed are illustrative channels, not a closed
schema. Authored coordinated performances may coexist with continuous semantic
variation.

## Pre-animation synchronization gate

Substantial production animation waits for sufficient agreement and evidence
for neutral/reference pose; authoring/export skeleton mapping; the
`neutral_bone`/unweighted-geometry issue; stable semantic aliases; eye aim;
blink/lid/squint architecture; asymmetry and brow/crest ownership; constraint
baking; root motion; clip naming/versioning and lifecycle; layering/runtime
override behavior; deterministic GLB export; protected diagnostic poses; and
representative runtime load/blending. Final crest design need not block bounded
experiments when these boundaries are preserved.

## Semantic Island Manifest

The Semantic Island Manifest remains a prototype, body/topology-revision-local
authoring and diagnostic artifact. It may support weighting, pose regression,
handoffs, and GLB validation. It is not Phoenix identity or universal anatomy.
Topology change invalidates or explicitly migrates it. Component numbers alone
are not stable identities; a useful fingerprint may include editable-mesh and
topology digests, quantized/component-space geometry, canonical internal edges,
UV/material topology, semantic declaration, intended owner, permitted blends
and exclusions, body version, and algorithm version.

## Explicit non-implementation

No Semantic Expression runtime, GLB readiness automation, island-manifest
runtime, pose-regression library, animation system, asset promotion, or Presence
expansion is implemented by this document.

## Progressive physical-prototype synchronization

The [physical development path](PHYSICAL_EMBODIMENT_DEVELOPMENT_PATH.md)
extends parallel embodiment development to our own increasingly capable robot
forms. Its first desk body is scheduled around the usable console / Phase 10 /
Alpha preparation, followed by expressive, aware, supervised rolling and refined
bodies as supporting capabilities become ready. These are learning and product
milestones; upgrading the same body is valid. Enjoyable actual interaction and a
short keep/change-next record are required outcomes of a useful prototype.

The GLB/rig gates above continue to govern digital assets. They do not certify
physical power, thermal behavior, actuator travel, stopping, connection loss or
mechanical safety. Introduce only capability-specific physical checks before the
corresponding function: scoped sessions before connecting to Fawkes, visible
privacy/retention controls before capture, bounded actuation and a local stop
before motion, and the physical-action boundary before autonomous movement.
A manual isolated fixture remains labeled Development evidence, not lived
Fawkes experience or permission to act. Mature Phase 26/28/29 functionality is
not required wholesale for an early stationary experiment, and earlier slices
must not claim those full phases complete.

Reuse the existing Semantic Expression direction without freezing a universal
anatomy or creating a second authority or capability registry. This amendment
adds planning/synchronization detail only; no robot runtime or operation is
implemented by it.
