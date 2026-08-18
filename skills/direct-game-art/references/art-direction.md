# Art Direction Review

Use this reference while drafting the art direction and reviewing the
representative target.

## Direction Contract

Bind every rule to a gameplay or platform need. Prefer observable constraints
over adjectives such as "beautiful" or "premium."

Record:

- target platform, resolution/aspect, camera, and expected display size;
- player-facing hierarchy for avatar, threats, rewards, interactables, feedback,
  environment, and UI;
- silhouette, value, hue, saturation, scale, and motion rules that preserve the
  hierarchy in grayscale and common color-vision conditions;
- palette swatches with semantic roles rather than an unbounded color list;
- shape, material, edge, lighting, texture-density, and animation language;
- explicit exclusions and the technical/performance budget.

Do not copy a living artist's style or use a reference as proof of license.
Describe transferable visual properties and record each reference's provenance.

## Representative Target Gate

The target must exercise the highest-risk visual relationship in a narrow,
runtime-relevant context. Review it at target scale and target framing.

Approve only when all applicable criteria have evidence:

1. The intended focal hierarchy is visible without explanation.
2. Gameplay states remain distinguishable by more than color alone.
3. Character and asset-family identity is consistent with the canonical source.
4. Small details survive actual display scale; backgrounds do not compete with
   hazards, rewards, or UI.
5. Alpha, edges, texture density, animation anchors, and compression are
   compatible with the target engine and platform budget.
6. The target is narrow enough to revise without discarding a batch.

Use `pending`, `approved`, or `rejected`. Approval requires approver ID, name,
rationale, target revision, and the exact target artifact identity.

## Asset-Family Rules

- Static props and icons: inspect isolated alpha plus actual-size placement.
- Canonical characters: lock one accepted identity source before variants or
  animation; regenerate the source instead of compounding a weak anchor.
- Animated sprites: define states, frame timing, pivots, loop behavior, and
  runtime frame rectangles; review contact sheets and motion previews.
- Backgrounds: define crop/safe regions, parallax layers, tiling, and texture
  limits; inspect with gameplay and UI overlays.
- UI art: use the approved interaction architecture; include default, hover,
  pressed, disabled, focus, and error states where applicable.
- VFX: separate visual timing from gameplay semantics. Hitboxes, damage,
  cooldown, and target tracking remain code-owned.
