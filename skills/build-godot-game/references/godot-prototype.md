# Godot Prototype Reference

Read this reference when implementing or diagnosing a Loopforge Godot 4
prototype.

## Scene and Script Shape

- Keep one main gameplay scene for a single-screen experiment.
- Prefer a small coordinator node plus focused player, hazard, score, and UI
  scripts over one global script or a speculative framework.
- Declare input actions in `project.godot`; do not depend on editor-local state.
- Use signals for meaningful state changes when they reduce direct coupling.
- Make restart reconstruct a known state instead of partially resetting nodes.

## Observable Loop

The first running frame should make the playable state inspectable. The core
verb must produce visible feedback. Success/failure must be distinguishable, and
restart must work without reopening the project.

For timing or risk/reward experiments, expose the relevant timing, danger, and
reward state visually. Do not add decorative effects that obscure whether the
hypothesis is functioning.

## Lightweight Verification

Loopforge's current Godot adapter provides two bounded checks:

- `run build`: launch the editor headlessly and quit, exercising project import
  and resource/script loading;
- `run test`: launch the project headlessly and quit, exercising startup of the
  configured main scene.

These are import and startup smoke checks, not a unit-test framework and not a
packaged export. Add project-native deterministic checks only when the existing
repository already has a test runner or the hypothesis has a critical invariant
that a small check can cover.

## Common Failure Cases

- No configured main scene: set the intended prototype scene explicitly.
- Missing input actions: define them in project settings committed to source.
- Headless-only crash: avoid assuming a display server in startup code.
- Parser/resource error: follow the first concrete Godot error before secondary
  missing-node failures.
- Blank capture: confirm the game reached the play scene and that the viewport
  contains rendered content before registering it.
- Stale evidence: rerun checks after any applicable script, scene, project, or
  asset change.
