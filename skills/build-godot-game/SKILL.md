---
name: build-godot-game
description: Implement, diagnose, and verify a small Godot 4 gameplay prototype inside a Loopforge experiment. Use when a Loopforge project contains project.godot or the user asks to build the active prototype in Godot, fix its build/startup failure, create the smallest playable 2D loop, or refresh Godot evidence after source changes. Do not use for non-Godot engines, broad production content, export/store publishing, or subjective claims that require human playtesting.
---

# Build Godot Game

Implement the active hypothesis as the smallest honest Godot 4 playable. Treat
Loopforge's adapter checks as technical evidence with explicit limits.

## Inspect Before Editing

1. Run `loopforge status --format json` and read the active hypothesis with
   `loopforge hypothesis show --format json`.
2. Inspect `project.godot`, the configured main scene, existing scenes, scripts,
   input actions, and repository conventions.
3. Run `loopforge inspect --format json`. If Godot is unavailable, report the
   missing executable and continue only with source changes that can be reviewed
   without claiming runtime success.
4. Read `references/godot-prototype.md` when choosing scene structure, input,
   restart, or verification behavior.

Preserve an existing architecture when it can support the experiment. Avoid
engine-wide refactors for a disposable prototype.

## Implement One Loop

- Build only the active hypothesis and stated platform/input.
- Keep the main play state reachable immediately.
- Provide visible response to the core verb, an observable success or failure
  state, and an immediate restart path.
- Use deterministic seams for randomness and time where lightweight checks need
  them, but do not replace actual runtime behavior with test-only code.
- Keep prototype-only code and assets easy to remove.
- Do not add production progression, menus, save systems, networking, or asset
  batches unless the hypothesis explicitly requires them.

## Verify in Order

Run checks after the relevant source is complete:

```bash
loopforge run build --expected-revision <revision> --format json
loopforge run test --expected-revision <revision> --format json
loopforge capture screenshot --file <runtime-capture> \
  --expected-revision <revision> --format json
loopforge gate check PLAYTEST_REQUIRED --format json
```

Use the revision returned by each mutation for the next command. `run build`
checks headless editor import/load; `run test` checks headless project startup.
Neither command proves gameplay behavior, performance, visual quality, or fun.
Inspect stdout, stderr, exit code, and capture contents before reporting success.

Capture the actual running play state at a useful viewport. Reject blank frames,
editor screenshots, menus that hide the experiment, and captures with clipped or
overlapping UI.

## Handle Failure

Fix the root cause, rerun the failed operation, and cite the latest evidence ID.
If the failure makes the approach infeasible, register or cite technical
evidence and use the early `PROTOTYPE_DECISION` path. Do not turn off errors,
remove the failing behavior, or reuse pre-change evidence merely to pass a gate.

When source changes after a passing run, expect claims to become `stale` and
regenerate build, startup, and capture evidence.

## Report

State what was implemented, which exact checks ran, their evidence IDs, known
limitations, the current Loopforge revision, and whether the playtest gate
passes. Keep technical validation separate from human playtest conclusions.
