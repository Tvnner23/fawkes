# Phoenix Presence v1 Asset Contract

This is the production envelope implemented by the Early Phoenix Presence GLB
pipeline. It describes a replaceable manifestation asset. It does not define
Fawkes's identity or make aesthetic decisions about his permanent form.

## Experimental static workshop manifestation

Presence also implements the narrower `presence-workshop-static-1` loading
contract so an actual in-progress Fawkes body can be made visible before it
satisfies this production envelope. Registration must be an explicit developer
operation using `scripts/register_presence_asset.py --workshop-static`. The
asset remains `development_asset`; successful loading does not claim accepted
embodiment, canonical visual identity, animation readiness, or promotion.

The workshop contract still requires a bounded, structurally valid,
self-contained glTF 2.0 binary with a renderable scene and mesh. It retains the
exact local copy, SHA-256 digest, source reference, rights, inspection evidence,
Phoenix binding, and failure isolation. External resource URIs are rejected.
Semantic bones, palette channel names, and the five Presence clips are observed
when present but are not required for this static milestone. The renderer uses
asset bounds for framing and reports that the manifestation is static. The
strict `presence-rig-1` path remains unchanged and is still required before a
development asset can satisfy the production contract.

## Required delivery

- One binary **glTF 2.0 `.glb`** plus its retained editable source file (for
  example, the original `.blend`). The source is provenance/recovery material;
  the web client loads only the GLB.
- The GLB must be self-contained. Embed textures and buffers; do not use
  external URIs, remote resources, scripts, custom executable metadata, lights,
  or cameras.
- Apply transforms before export. Use meters, glTF Y-up, a centered ground
  origin, and a neutral forward-facing pose toward +Z. The current camera looks
  from +Z toward the origin.
- Provide creator, source reference, ownership/license, usage rights, and asset
  revision. The local developer registrar computes SHA-256 and stores the
  validated copy as `development_asset`. Canonical status requires a later,
  explicit rider design decision.

## Semantic rig

The model must be skinned. These stable semantic nodes/bones are required:

- `phoenix_root`
- `body`
- `head`
- `wing_left`
- `wing_right`
- `tail`

Additional deform/control bones and any internal hierarchy are allowed. The
required names are a small cross-asset compatibility surface, not a mandated
modeling topology. Use no more than 80 deform joints for the v1 mobile target,
and no more than four joint influences per vertex.

“Deform joints” is an authoring-envelope term, not a substitute for exported
runtime accounting. Readiness evidence must also report maximum joints per GLB
skin, unique joint union for multi-skin assets, and weighted/animated/
hierarchy-only/rigid-parent/synthetic joints where determinable. The current
ceiling is unchanged pending runtime evidence. See
[Embodiment Development Gates](EMBODIMENT_DEVELOPMENT_GATES.md).

## Required animation clips

All five clips must be authored and exported under these exact names:

- `presence.idle` — seamless loop; neutral living motion.
- `presence.invoked` — one-shot acknowledgement/waking response.
- `presence.thinking` — loopable processing expression.
- `presence.responding` — loopable or cleanly repeatable response expression.
- `presence.task_complete` — one-shot completion response.

Clips should begin from a compatible neutral pose, avoid translating the world
root away from the presentation origin, and blend cleanly over approximately
0.18 seconds. Use ordinary keyframed glTF animation at 30 fps (or equivalent
curves). Do not depend on Blender constraints, drivers, simulation, or plugins
that are not baked into the exported clips.

## Independent color and emissive channels

The GLB must expose these exact material names:

- `plumage_primary`
- `plumage_secondary`
- `expression_crest`
- `expression_feather_tips`
- `flame_accent`

`plumage_primary` is the stable rider-selected base coloration.
`plumage_secondary` is the stable Phoenix-selected secondary coloration; v1
reserves that semantic ownership but does not implement autonomous selection or
Development. `expression_crest` and `expression_feather_tips` are separately
addressable transient expression regions. Their normal values should visually
return to the stable primary/secondary appearance after a future momentary
flash. `flame_accent` remains independently controllable for flame/aura effects.

The renderer independently controls each material's base color, emissive color,
and emissive intensity from the Phoenix presentation profile. Emotional
expression must not require recoloring the whole Phoenix, and this contract
defines no universal emotion-to-color mapping. The authored texture/material
setup must remain usable when radically different palettes are applied. Stable
identity should come primarily from the approved silhouette, crest/head
geometry, wing/tail construction, and characteristic movement—not from one
hard-coded palette. Additional materials are permitted but are not controllable
by the v1 semantic palette contract.

The expressive rear/top head feathers must be modeled and rigged so they can
eventually perk, fan, sweep backward, flatten, droop, flare, twitch, and move
asymmetrically. They amplify facial expression; they are not a substitute for
a readable face. Eyes, brow/eye surround, beak/mouth treatment, and head pose
must remain legible in a compact head-and-face crop where some or all crest
feathers may be outside the frame. Presence v1 does not prescribe emotion logic
or add those movements to its required five animation clips.

### Compact framing and meaningful attention

Fawkes's default compact manifestation uses a relaxed three-quarter head
orientation with one eye prominently visible. This is an intentional expressive
baseline, not a limitation of the mesh or camera. **Looking directly at the
rider carries meaning:** increased attention may turn the head until the second
eye becomes visible, while strong expression may present both eyes with the
face, eye direction, and crest acting together. Afterward Fawkes can return
smoothly to the relaxed three-quarter pose.

The rig therefore needs sufficient independent head/neck rotation, eye-direction
control, and rear/top crest articulation for smooth one-eye relaxed → both-eyes
engaged → relaxed transitions. The face must remain readable without relying on
the crest, particularly in portrait-style crops. Head orientation is an
animation/expression layer over the semantic Presence states, not a new Presence
state, identity field, emotion mapping, or continuity signal.

Use standard glTF metallic-roughness PBR materials. Presence v1 does not load
custom shaders, Draco, Meshopt, or KTX2/Basis extensions. Flame geometry may be
stylized, transparent, and emissive, but it must have an honest static/PBR
fallback; advanced particles remain future renderer capability.

## Mobile budget

- Target 20,000–40,000 triangles; hard review ceiling 60,000.
- Maximum six draw calls/material slots for the primary manifestation.
- Prefer 1024px textures; no texture may exceed 2048px in v1.
- Maximum validated GLB size: **8 MiB**.
- Avoid dense hidden geometry, unnecessary blend shapes, excessive transparent
  overlap, and high-frequency idle movement.

The renderer requests a low-power context and caps device pixel ratio at 1.5.
Meeting these asset limits does not replace physical mobile battery, thermal,
frame-pacing, and visual acceptance on Tanner's devices.

## Validation and promotion

Validation matures progressively from prototype structure through pre-animation
skeleton/export mapping, actual pre-Presence runtime load/blending, and later
Test Center/promotion evidence. Passing a structural validator cannot promote an
asset or replace Tanner's visual review.

1. Export GLB and retain the editable source.
2. Run `scripts/register_presence_asset.py` with the registered Phoenix ID,
   asset ID, revision, creator, license, and source reference.
3. The registrar verifies glTF structure, size, semantic bones, clip names,
   material channels, rights metadata, and digest before registration.
4. Run focused Presence tests and the Test Center `Presence` entries.
5. In the actual rider app, verify a nonzero canvas, rendered non-background
   pixels, idle plus a lifecycle-driven transition, reduced motion, static
   fallback, mobile/desktop behavior, and Chat failure isolation.
6. Record physical device verification separately. Automated evidence must not
   claim that Tanner saw or heard the manifestation.

The synthetic GLB used by automated tests is disposable contract geometry. It
is never registered as Fawkes, does not establish his appearance, and must not
be promoted to canonical status.
