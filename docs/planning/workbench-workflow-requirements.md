# Workbench Workflow Requirements

## 1. Purpose

The Workbench can currently show a project and talk to a model. It cannot move
a project through a single step of its lifecycle. This document defines what
the Workbench must be able to do for the workflow in `mvp.md` §3 to be
completable without dropping to the command line, and what each surface owes
its user.

It is a requirements document, not a design or an implementation plan. It fixes
purpose, data source, constraints, failure states and acceptance criteria per
capability; screen layout is settled during implementation against the existing
UI vocabulary.

## 2. Current position

Wired and serving real data: chat with streamed replies and Agent-owned
history, provider inventory and model-role routing, engine run history
(Terminal), test run history plus a test trigger (Test), stage and derived
quality claims (Tasks).

The gap is narrow to describe and wide in consequence. The stage machine is:

```
UNINITIALIZED → DISCOVERY → PROTOTYPING → PLAYTEST_REQUIRED → PROTOTYPE_DECISION
                                    ↘                              ↓
                                     PROTOTYPE_DECISION    KILLED | PROTOTYPING | VERTICAL_SLICE
```

It has eight transition points. The Workbench covers none of them.

The consequence is measurable rather than theoretical. Quality claims derive
from registered evidence, and `TECHNICALLY_VALIDATED` requires a passing build
*and* a passing test. The Test workspace sends `operation: "test"` only, so:

```
test only        → TECHNICALLY_VALIDATED: unknown
test and build   → TECHNICALLY_VALIDATED: satisfied
```

Every claim a user can see today is permanently `unknown`, because no path
through the Workbench can produce the evidence any of them require.

## 3. Principles

These constrain every requirement below.

1. **The core decides, the Workbench asks.** Stage legality, gate satisfaction
   and evidence validity are computed by the deterministic core. The Workbench
   must never re-implement a rule to grey out a control; it asks and renders
   the answer. A UI that disagrees with the core is worse than one that lets
   the user try and be refused.
2. **Claims stay orthogonal.** Per ADR 0002, no surface may combine claims into
   a single score or completion bar. A passing build must never read as a
   validated game.
3. **Observation stays separate from interpretation.** Playtest raw
   observations and the Agent's reading of them are distinct fields and must
   remain visually distinct.
4. **The Agent drafts, the human approves.** Where a record needs prose the
   user should not face an empty form. The Agent proposes, the user edits and
   confirms. This follows `mvp.md` §3 steps 3-4 and is what makes the product
   an assistant rather than a wizard.
5. **Nothing is claimed on the user's behalf.** Approver identity and consent
   are recorded because a human supplied them, never defaulted.

## 4. Capability requirements

Each capability names the CLI contract it is built on. Where the Agent does not
yet expose it, that endpoint is part of the requirement.

### R1 — Initialize a project

**Why.** Opening a non-Loopforge folder currently shows "This folder is not a
Loopforge project yet." and offers nothing. That is a dead end in the first
thirty seconds of the product.

**Core contract.** `loopforge init`, no arguments. Moves UNINITIALIZED →
DISCOVERY at revision 1.

**Agent.** New `POST /v1/project/init`.

**Requirements.**
- The uninitialized state must offer initialization in place, not as a separate
  setup screen.
- The folder being initialized must be shown in full before the action, since
  the user may have opened the wrong directory.
- Initialization is a write to the user's filesystem; it must state that a
  `.loopforge/` directory will be created.
- A folder that is already a project must not offer the action.

**Acceptance.** Opening an empty folder and initializing it leaves the project
in DISCOVERY, and Tasks reflects the new stage without a manual reload.

### R2 — Author and approve a hypothesis

**Why.** No hypothesis means no active experiment, which means registered
evidence has a null `hypothesis_revision` and cannot be attributed. This gates
everything downstream.

**Core contract.** `loopforge hypothesis create --file <markdown>` with optional
`--approver-id`, `--approver-name`, `--rationale`. The file is Markdown parsed
by heading; eleven fields are required and must be non-empty:

`intended_player`, `platform`, `player_fantasy`, `core_verb`,
`moment_to_moment_loop`, `hypothesis`, `constraints`, `non_goals`,
`cheapest_validation`, `keep_signals`, `kill_signals`.

`loopforge hypothesis show` reads the active record.

**Agent.** New `POST /v1/hypothesis` and `GET /v1/hypothesis`. The Agent
writes the Markdown file from structured input; the Workbench must not
construct file paths.

**Requirements.**
- The user must not be presented with eleven empty fields. The Agent drafts
  from the conversation, and the surface is a review-and-edit view over that
  draft. This is principle 4 and the difference between this product and a
  form.
- Drafting belongs to a skill, not to a bespoke Agent endpoint. The
  `prototype-gameplay` skill already owns a `Discovery` section covering this
  stage, so the requirement is to make that reachable from the Workbench rather
  than to add a second authority on what a hypothesis should contain. See §9.
- Every field must be individually editable after drafting.
- Incomplete fields must be visible as incomplete before submission, because
  `HYPOTHESIS_COMPLETE` will otherwise fail at the gate with less context.
- The active hypothesis and its revision must be readable at any later stage;
  a decision made months later cites it.

**Acceptance.** From a DISCOVERY project, a user can ask the Agent for a
hypothesis, edit at least one field, submit, and see `gate check PROTOTYPING`
report `HYPOTHESIS_PRESENT` and `HYPOTHESIS_COMPLETE` as satisfied.

### R3 — Check gates and advance stages

**Why.** Advancing is the only way to reach the stages where playtest and
decision records are legal. Today it is command-line only.

**Core contract.** `loopforge gate check <stage>` returns a requirement list,
each entry carrying a code, a status of `satisfied | missing | invalid`, and a
remediation string. `loopforge advance <stage>` performs the transition and
accepts `--reason {technical,scope,abandon}` plus approver fields.

**Agent.** New `GET /v1/gate/{stage}` and `POST /v1/advance`.

**Requirements.**
- The gate result is a checklist, one row per requirement, showing the core's
  remediation text verbatim. Do not paraphrase it: it is the actionable part.
- Advancing must be available from the gate view when every requirement is
  satisfied, and must remain attemptable when they are not — the core refuses
  and its refusal is the message (principle 1).
- Transitions that carry a `reason` (`technical`, `scope`, `abandon`) must
  make the reason an explicit choice; it is recorded in the event log and
  changes how a later reader interprets the project's end.
- The next legal stages must be derivable by the user from the current one
  without consulting documentation.
- This is the Flow workspace's purpose. Flow currently draws a generic coding
  pipeline (`trigger → plan → edit → test → review`) belonging to a different
  product. Loopforge's real flow is the stage machine, and unlike that pipeline
  it has a live data source. Repointing Flow at it reuses the existing node and
  connector layout and gives R3 a home.

**Acceptance.** A project with a complete hypothesis shows an all-satisfied
gate for PROTOTYPING and can advance. A project without one shows the missing
requirement and its remediation, and advancing fails with that reason shown.

### R4 — Trigger a build

**Why.** The smallest gap with the largest visible effect: `TECHNICALLY_VALIDATED`
is unreachable without it, so every claim in Tasks is stuck at `unknown`.

**Core contract.** `loopforge run build`, already reachable through
`agent_run_engine` with `operation: "build"`. The Agent and Tauri layers accept
it today; only the UI entry point is missing.

**Requirements.**
- Build and test must be triggerable from the same surface, since together they
  are what satisfies one claim. Splitting them across workspaces hides that.
- Both operations write run records and register evidence automatically; the
  surface must not imply a separate registration step.
- A run in progress must be distinguishable from a finished one, and the
  trigger must not be re-entrant.

**Acceptance.** On a fixture Godot project, running build and then test moves
`TECHNICALLY_VALIDATED` from `unknown` to `satisfied` without leaving the
Workbench.

### R5 — Register a visual capture

**Why.** `VISUALLY_REVIEWED` has no other source.

**Core contract.** `loopforge capture screenshot --file <path>`. Note this
registers an existing image; it does not drive the engine. The resulting
evidence is `trust_level: manually_imported`, `result: observation`.

**Agent.** New `POST /v1/capture`.

**Requirements.**
- The surface must make clear the user is registering a file they produced, not
  asking Loopforge to take a screenshot. Implying the latter would misrepresent
  what the evidence attests.
- File selection uses the existing native dialog path; the Workbench must not
  accept a typed path.
- The recorded trust level must be visible, since `manually_imported` is
  weaker than `tool_generated` and a later reader needs to know.

**Acceptance.** Registering a PNG moves `VISUALLY_REVIEWED` to `satisfied` and
the evidence list shows it as manually imported.

### R6 — Run a human playtest

**Why.** `HUMAN_PLAYTESTED` is the claim that separates this product from
automated testing, and it is the core of Milestone 3.

**Core contract.** Both steps require stage `PLAYTEST_REQUIRED` and fail with
`PLAYTEST_STAGE_INVALID` otherwise. `loopforge playtest create --protocol
<file>` registers the protocol; `loopforge playtest import --file <report>`
imports the result and requires an existing protocol.

The two artifacts have different shapes, and this decides the two surfaces:

- The **protocol** is free-form UTF-8 Markdown. The core stores it without
  schema validation, so its quality is entirely the Agent's responsibility and
  the Workbench cannot validate it. The surface presents and exports prose.
- The **report** is JSON validated against ten required fields:
  `participant_context`, `consent_status`, `raw_observations`,
  `comprehension_time`, `confusion_points`, `failure_points`,
  `abandonment_points`, `strategies`, `replay_behavior`, `interpretation`.
  The surface collects structured input and the Agent assembles the JSON; the
  Workbench must not ask a user to write JSON.

**Agent.** New `POST /v1/playtest/protocol` and `POST /v1/playtest/report`.

**Requirements.**
- The protocol is generated by the Agent for the human to run away from the
  machine. The surface must support getting it out of the application —
  copy or export — because the playtest happens elsewhere.
- `consent_status` must be an explicit human input. It must never be
  pre-filled, defaulted, or inferred; it records a third party's consent.
- `raw_observations` and `interpretation` must be visually separated, and
  their difference stated. This is principle 3 and ADR 0002; a surface that
  blends them destroys the evidentiary value of the record.
- Entering the report before the stage allows it must explain the stage
  requirement rather than surfacing a raw error code.
- Participant context must carry a privacy note: it describes a real person.

**Acceptance.** From `PLAYTEST_REQUIRED`, a user can obtain a protocol, enter a
report with explicit consent, and see `HUMAN_PLAYTESTED` become `satisfied`
with raw observations still distinguishable from interpretation.

### R7 — Record a keep, kill or refactor decision

**Why.** This is the product's terminal act — the point of the whole loop.

**Core contract.** `loopforge decide <keep|kill|refactor>` requires stage
`PROTOTYPE_DECISION`, at least one `--evidence` id, and `--approver-id`,
`--approver-name` and `--rationale`, all mandatory. A `keep` also requires a
playtest record for `FUN_HYPOTHESIS_SUPPORTED` to become satisfied.

**Agent.** New `POST /v1/decision` and `GET /v1/evidence`.

**Requirements.**
- Evidence must be chosen from the registered list, showing each item's type,
  result and trust level. A decision citing evidence the user never saw is
  ceremony.
- The rationale is mandatory and must not be satisfiable with whitespace.
- The three outcomes must be presented as equally legitimate. A UI that makes
  `keep` the prominent path biases the decision the product exists to make
  honestly.
- Where `keep` is chosen without the evidence to support the fun hypothesis,
  the surface must state that the decision is recorded but the claim remains
  unsupported.

**Acceptance.** A decision cannot be submitted without evidence, approver and
rationale. A recorded `keep` with a playtest moves `FUN_HYPOTHESIS_SUPPORTED`
to `satisfied`; a `kill` moves it to `failed`.

### R8 — Diagnose and recover

**Why.** ADR 0003 makes interrupted writes and stale snapshots normal, expected
conditions. The recovery path is currently command-line only, which means the
Workbench can enter a state it cannot explain or leave.

**Core contract.** `loopforge doctor`, `validate`, `history`, `inspect`, and
`reconcile --dry-run | --yes`.

**Agent.** New `GET /v1/project/validate`, `GET /v1/project/history`, and
`POST /v1/project/reconcile`.

**Requirements.**
- A stale snapshot blocks every gate (`STATE_SNAPSHOT_CURRENT`). When it is
  stale the Workbench must say so wherever it blocks, not only in a diagnostics
  view.
- `reconcile` rewrites derived state. It must be preceded by a dry run whose
  result the user sees before confirming, and must never be automatic.
- History is the audit trail. It must be readable in the product that produced
  it.

**Acceptance.** A project with a deliberately stalled snapshot reports the
condition, offers a dry run, and can be reconciled from the Workbench.

## 5. Cross-cutting requirements

**Localization.** Every new string enters `src/i18n/locales/en.ts` and all seven
other catalogues. `en.ts` is the typed source of truth, so an omission is a
compile error, not a runtime blank. Arabic is RTL; new layout uses CSS logical
properties.

**Runtime guards.** Every write action is gated on `isDesktopRuntime()`, as
`invoke` is absent in a browser shell.

**Contracts.** Each new Agent endpoint gets a schema under `contracts/` with
`additionalProperties: false` and a conformance test, matching
`loopforge-provider-v1` and `loopforge-project-status-v1`.

**Error surfacing.** Core diagnostics carry a code and a remediation. Surfaces
show the remediation and keep the code available. A raw code alone is not an
acceptable user-facing error.

**Approver identity.** R2, R3 and R7 record an approver — four commands
(`hypothesis create`, `gate check`, `advance`, `decide`), mandatory only on
`decide`.

Loopforge is a local agent with no cross-user collaboration, and the core
already reflects this: every approval record carries
`identity_source: "local-declaration"`. It does not claim the identity was
verified, because it was not. There is no role model to build here.

The approver is therefore the Workbench user, configured once as a General
setting and sent to the Agent, with approvals refused until it is set — a
recorded approver must be a real choice, not a default.

The subagent drafts; it never approves. Where it drafts a rationale, two
requirements follow:

- the drafted text must be shown and remain editable before submission. A
  rationale is checksummed into the record under the user's name, so accepting
  unread agent prose would attribute an argument to someone who never made it;
- no path may submit a draft without displaying it first.

## 6. Verification requirements

The engine path is the least verified code with a UI entry point in this
repository. `run_engine` has no test coverage at all, and the only Godot-related
test substitutes a shell script that echoes a version string. No fixture Godot
project exists.

This is the same gap that mocked tests left in the Kura client, where every
wire-level failure passed the unit suite and was found only against a live
daemon. The remedy is symmetric:

- a minimal fixture Godot project committed to the repository;
- `tests/cli/test_engine_integration.py` running build and test against a real
  Godot binary, skipped via a `requires_godot` decorator when absent;
- a CI job installing Godot and running it, with a guard step that fails when
  the binary is not discoverable — a skipped suite reports success, so without
  the guard the job silently becomes a no-op.

R4 is the natural first consumer: it is the shortest path from a UI action to a
changed claim, and therefore the best end-to-end assertion available.

## 7. Non-goals

- **Canvas, Assets, Profiler.** These serve Milestone 4, whose `VERTICAL_SLICE`
  stage is reachable only through `PROTOTYPE_DECISION`. Building them before R7
  produces surfaces no user can reach.
- **Diff.** Removed rather than deferred. The decisive objection is not scope
  but that it has no data source: the core does not track code changes, no CLI
  command produces a diff, and `source_identity` is a project fingerprint for
  detecting stale evidence, not a change set. Building it would require a new
  core capability over git first. Loopforge's human approval points are stage
  gates and decisions, not individual lines. If a review surface is wanted
  later it starts from a core capability, not from a retained placeholder.

  Flow is absent from this list deliberately: it is repointed at the stage
  machine under R3 rather than removed, because unlike Diff it has one.
- **Multi-project or multi-user surfaces.** Explicitly deferred in
  `roadmap.md`.
- **Engine-driven screenshot capture.** R5 registers existing files; making the
  engine produce them is a separate core capability.

## 8. Dependency order

```
R4 build trigger ── independent, smallest, first visible claim change
   └── verification (§6) is its acceptance test

R1 init ── entry point, no dependency
   └── R2 hypothesis ── creates the active experiment
        └── R3 gate + advance ── strictly serial; nothing downstream is legal without it
             ├── R5 capture      → VISUALLY_REVIEWED
             └── R6 playtest     → HUMAN_PLAYTESTED   (requires PLAYTEST_REQUIRED)
                  └── R7 decide  → FUN_HYPOTHESIS_SUPPORTED (requires PROTOTYPE_DECISION)

R8 diagnostics ── independent, but a stale snapshot blocks every gate above,
                  so it should not trail R3 by long
```

R1→R2→R3 is strictly serial: evidence registered without an active experiment
carries a null hypothesis revision and cannot be attributed to anything.

## 9. Skill boundary

R2, R6 and R7 all need the Agent to draft prose a human then approves. That
drafting is skill work, and the requirement is to make existing skills
reachable from the Workbench rather than to grow a parallel authority inside
the Agent on what a hypothesis, protocol or rationale should contain.

The mapping today:

| Need | Skill | Section |
|---|---|---|
| R2 hypothesis draft | `prototype-gameplay` | `Discovery` |
| R6 playtest protocol and report reading | `prototype-gameplay` | `External Playtest` |
| R7 decision rationale | `prototype-gameplay` | `Decision` |

`prototype-gameplay` covers the whole prototype loop, which is why the
Workbench work does not depend on the skill layer being reorganized first.

`design-game` is a separate matter and is out of scope here. It carries four
modes — `TRIAGE`, `DESIGN_CONTRACT`, `VERTICAL_SLICE`, `REVIEW` — spanning
from pre-hypothesis direction-finding to post-decision production planning.
Those belong to different lifecycle stages, which makes its trigger boundary
inherently ambiguous and is a standing argument for splitting it. None of the
requirements above depend on that split, so it should be planned on its own
rather than bundled into this work.

## 10. Resolved decisions

Recorded because the requirements above assume them.

**Approver model.** The Workbench user is the approver, configured once. No
cross-user or role model: Loopforge is a local agent and the core already
records `identity_source: "local-declaration"` rather than claiming
verification. The subagent drafts and never approves; drafted rationale must be
displayed and editable before it is submitted under the user's name. See §5.

**Flow.** Repointed at the stage machine as the surface for R3, replacing the
generic coding pipeline it draws today. See R3.

**Diff.** Removed. It has no data source in the core, and adding one means
building a git capability first. See §7.

**Hypothesis drafting.** Owned by the `prototype-gameplay` skill's `Discovery`
section, not a bespoke Agent endpoint. See §9.