# M2 Unseen Prototype Run: Echo Lantern

## Prompt recorded before implementation

Create a small, single-screen Godot 4 2D game about navigating in darkness.
The player can reveal the scene with a lantern, but revealing it also lets a
pursuer move. Make the tradeoff observable within one short run, with a clear
failure, success, and restart loop. Do not reuse the risk-charge dash fixture.

## First hypothesis and scope

Hypothesis: after discovering that the pursuer moves only while the lantern is
on, a first-time player will voluntarily use short light pulses to navigate
between three beacons rather than leave the lantern on continuously.

Keep signal: an external participant uses at least one deliberate short pulse
after observing pursuer movement, collects a beacon, and restarts voluntarily
after a failed run. Kill signal: after two runs, they still cannot explain what
makes the pursuer move without coaching. These are hypotheses for future human
observation, not claims established by automated checks.

Scope: one scene, keyboard input, three beacons, one pursuer, no progression,
accounts, procedural content, or production art. The automated run may check
engine startup and deterministic mechanics; it must not infer player
comprehension or enjoyment.

## Execution and result

The prompt and first hypothesis above were recorded before implementing
`examples/echo-lantern`. On 2026-09-24, Codex implemented the single-scene
prototype and tested a fresh project copy, not the existing risk-dash fixture:

- Godot 4.7.2 imported the source without errors.
- The in-engine deterministic check printed `ECHO_LANTERN_SELF_TEST_OK`: Space
  toggled the lantern, the player moved, the pursuer froze in darkness and
  moved while lit, a beacon could not be collected in darkness, three beacons
  produced a win, R reset the state, and pursuer contact produced failure.
- The Loopforge CLI detected Godot, initialized revisioned state, and recorded
  tool-generated `build` and `test` evidence with passing engine runs. Both
  used source digest `sha256:6a20b000c20b0a2e0d460842863ef3c3876d2e65fbb85b0ca0b165ae6e28d02f`
  after the input-path test was added to the isolated run.
- A real Godot runtime capture produced a 960×540 PNG frame with the player,
  pursuer, three beacons, instructions, and warning visible. Its SHA-256 was
  `adfc24aceb7b322449eaa59f58b09919a5329b1fd03d666dcd1a66059096a309`.
  The frame was inspected visually and registered as manually imported capture
  evidence; it is not evidence of human play.
- `loopforge validate` reported a current snapshot and 15 valid events in the
  isolated run after the final source copy, build, test, and capture.
- `gate check PROTOTYPING` correctly returned `blocked`: no human has approved
  and registered the hypothesis. The build/test records were made before any
  approved hypothesis and therefore must be rerun after approval before they
  can satisfy a later stage gate. No stage transition or external playtest is
  claimed from this technical run.

The source remains available as a candidate for Run B in
`mvp-field-validation.md`. Actual participant behavior and an independent
review are still required.
