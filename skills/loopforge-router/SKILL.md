---
name: loopforge-router
description: Route Loopforge game-development work from the repository's current stage to the smallest applicable workflow. Use when a user explicitly mentions Loopforge, asks what to do next in a Loopforge project, resumes an evidence-backed game prototype, or asks to move a game idea through hypothesis, implementation, playtest, keep/kill/refactor, game design, representative art, or a vertical slice. Do not trigger for unrelated software projects or generic game-engine questions with no Loopforge workflow intent.
---

# Loopforge Router

Inspect durable project state before recommending work. Route to one primary
skill and keep stage transitions in Loopforge's own tools.

## Use the tools; do not describe them

Loopforge's commands are available to you as tools named `loopforge_*`. Call
them. Do not write out a shell command and say you are running it -- you cannot
run shell commands, and a message that says "Running `loopforge init`..." is a
message in which nothing happened.

Some tools ask a person before they run. That is normal and it is not an error:
the call waits, someone answers, and you are given the result or told it was
refused. Wait for it rather than reporting that you were blocked.

## Establish State

1. Call `loopforge_inspect`.
2. If the project is uninitialized and the user intends to use Loopforge, call
   `loopforge_init`.
3. Call `loopforge_status`.
4. If `snapshot_status` is not `current`, call `loopforge_validate` and report
   the integrity failures. Do not rewrite evidence or history.
5. Preserve the returned revision and pass it as `expected_revision` on the
   next tool that changes something.

Do not infer the current stage from chat history. Do not edit `.loopforge`
records directly.

## Route One Next Action

Use the current stage and the user's requested outcome:

| Stage | Primary workflow | Next outcome |
|---|---|---|
| `DISCOVERY` | `$prototype-gameplay` discovery | Approved falsifiable hypothesis |
| `PROTOTYPING` | `$prototype-gameplay`, plus `$build-godot-game` for Godot | Fresh build, startup, and capture evidence |
| `PLAYTEST_REQUIRED` | `$prototype-gameplay` playtest | Imported external observations |
| `PROTOTYPE_DECISION` | `$prototype-gameplay` decision | Human-confirmed `keep`, `kill`, or `refactor` |
| `VERTICAL_SLICE` | `$design-game` | Approved scoped design contract and handoff readiness |
| `KILLED` | Report decision and cited evidence | Stop unless the user starts a new experiment |

If the engine is not Godot, keep the hypothesis and evidence workflow but use
manual evidence registration rather than pretending an adapter exists.

Within `VERTICAL_SLICE`, route a missing, pending, or stale design contract to
`$design-game`. After explicit design approval, route representative visual
direction to `$direct-game-art` and bounded implementation to the engine Skill.
Do not make art or engine workflows reconstruct scope from unapproved prose.

## Guardrails

- Call `loopforge_gate` before `loopforge_advance`.
- Treat `missing`, `failed`, `stale`, and `unknown` as blocked, not as implicit
  permission.
- Never use direct event edits or invent a force path.
- Never attribute an approver identity or rationale that the user did not
  provide or confirm.
- Never describe automated build, startup, or capture evidence as proof that a
  game is fun or human-playtested.
- Never expand implementation or content beyond the approved design scope.
- Never start batch art production before the representative target has explicit
  human approval.
- End each work segment with `loopforge_status` and report the
  current stage, revision, fresh claims, stale claims, and one next action.
