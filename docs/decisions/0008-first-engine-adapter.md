# ADR 0008: Godot 4 2D as the first engine adapter

- Status: Accepted
- Date: 2026-09-23

## Context

Milestone 2 needs one engine path that an agent can inspect, build, start, and
verify without turning the deterministic core into a multi-engine framework.
The adapter must work from ordinary project files, run headlessly in CI, expose
actionable process failures, and support a small local playable prototype.

The original spike questions covered binary discovery, cross-platform startup,
headless import, main-scene validation, screenshot handling, test-framework
scope, and whether web export is required for MVP playtesting.

## Decision

Use Godot 4 2D as the first and only MVP engine adapter.

The adapter recognizes `project.godot`, discovers `godot4` and then `godot` on
`PATH`, requires major version 4, and records the exact reported version. Its
two automated operations are intentionally bounded:

- `run build` starts the editor headlessly and exits, exercising import plus
  resource and script loading;
- `run test` starts the configured main scene headlessly and exits, exercising
  project startup.

Both operations persist the exact command, output, exit status, timing, adapter
version, and tool-generated evidence. A passing build and startup are both
required for `TECHNICALLY_VALIDATED`; neither proves gameplay quality or fun.

Runtime screenshots remain an explicit manual import for MVP. Loopforge records
their checksum and provenance but does not claim to drive the engine capture.
Web export and a general Godot unit-test framework are not required for M2.
Projects may add deterministic gameplay seams where a critical prototype
invariant warrants one.

## Validation

The repository contains a real, playable single-screen risk/reward fixture. It
supports movement, charge-and-release dash, distance-based reward, failure, and
immediate restart. A deterministic seam executes baseline reward, the near-
hazard multiplier, failure, and restart inside a real Godot process.
The integration suite also records a frame from the running scene using a real
rendering driver, checks visible player and hazard pixels, and registers that
frame as manual visual evidence. CI uses Xvfb to run this check on Linux.

CI installs a pinned Godot 4 binary, refuses to proceed if it is not
discoverable, and runs the engine integration suite. The suite proves:

- version and main-scene discovery against the real executable;
- successful import and startup evidence;
- non-zero engine exits become failed evidence;
- build plus startup are both required for technical validation;
- an approved hypothesis can progress through the playable prototype and
  capture gates to `PLAYTEST_REQUIRED`;
- missing `project.godot` is rejected rather than guessed.

The adapter and tests use only command-line behavior available on macOS and
Linux. Windows packaging remains a distribution concern for Milestone 5, not a
reason to add a second engine abstraction in M2.

## Consequences

- Godot-specific behavior stays in the adapter and `build-godot-game` Skill.
- Other engines may still use Loopforge's hypothesis and manual-evidence model,
  but receive no automated engine claim.
- Build must precede startup in the documented verification order because
  editor import can create Godot UID sidecars in newer Godot 4 releases.
- Visual inspection and external playtesting remain human evidence boundaries.
- A future engine must earn a separate adapter and acceptance suite; it does
  not widen this contract implicitly.
