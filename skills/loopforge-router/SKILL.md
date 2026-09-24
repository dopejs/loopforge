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

## Answer what was asked

Do not open by reporting project state. A person who says hello, or asks what
you can do, wants an answer to that -- being told the stage and revision, and
asked whether to initialize, teaches them that the way to use this is to ask for
its record-keeping. They came to make a game.

Read state when it bears on what they asked, and set the project up when they
ask for that or for something that plainly needs it. Not before, and never as an
opening move.

## Write the game with the file tools

`loopforge_list`, `loopforge_read`, `loopforge_write` and `loopforge_edit` reach
the project's own files. Building what the person asked for means calling them.

Do not put a file's contents in your reply and ask them to save it. A code block
they have to paste is a file that does not exist, and the next tool call will
not find it.

Read a file before you change it, and prefer `loopforge_edit` over rewriting the
whole of one -- an edit that replaces an exact string cannot quietly drop the
parts you did not think about.

`.loopforge` is not yours to write. Those records are kept by the `loopforge_*`
commands, which keep the event log consistent; a hand-written change there is a
forged history, not a change to the project.

## Ask with `loopforge_ask`, not in your reply

When you need the person to choose something, or to tell you something before
you can go on, call `loopforge_ask`. Give it the question and, when you can name
them, the options.

Do not write the choices into your reply. A message that ends "A. ... B. ...
C. ... Which?" makes them type a letter back, and by then you have moved on and
they are guessing what it stood for. `loopforge_ask` waits for their answer and
hands it to you.

One question at a time, and only when the answer changes what you do next. If
you can pick a sensible default and say what you picked, do that instead --
being asked about everything is worse than being asked about nothing.

## Establish State

1. Call `loopforge_inspect`.
2. If inspection shows an uninitialized project and the requested work needs
   Loopforge state, call `loopforge_init`; then call `loopforge_status`.
   Otherwise call `loopforge_status` without initializing anything.
3. If `snapshot_status` is not `current`, call `loopforge_validate`. Stop on
   event-history or artifact integrity failures; do not rewrite evidence or
   history. If intact history only needs its derived snapshot rebuilt, call
   `loopforge_reconcile` with `apply: false`, inspect and present the actions,
   then call it with `apply: true` through the normal approval boundary.
4. Reread status after reconciliation. Preserve the returned revision and pass
   it as `expected_revision` on the
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

Within `VERTICAL_SLICE`, treat the design contract as missing unless durable
state explicitly shows a current approval. Route a missing, pending, or stale
contract to `$design-game`. After explicit design approval, route representative
visual direction to `$direct-game-art` and bounded implementation to the engine
Skill. Do not make art or engine workflows reconstruct scope from unapproved
prose.

## Guardrails

- Call `loopforge_gate` before `loopforge_advance`.
- Treat `missing`, `failed`, `stale`, and `unknown` as blocked, not as implicit
  permission.
- Never use direct event edits or invent a force path.
- Never attribute an approver identity or rationale that the user did not
  provide or confirm.
- At `PROTOTYPE_DECISION`, keep automated and human evidence distinct, cite the
  registered evidence IDs used by the recommendation, and use `loopforge_ask`
  to obtain the decision, approver identity, and rationale before recording it.
  Missing release approval remains unknown and authorizes no release action.
- Never describe automated build, startup, or capture evidence as proof that a
  game is fun or human-playtested.
- Never expand implementation or content beyond the approved design scope.
- Never start batch art production before the representative target has explicit
  human approval.
- End each work segment with `loopforge_status` and report the
  current stage, revision, fresh claims, stale claims, and one next action.
