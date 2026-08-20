# Product Roadmap

## Planning principle

Each milestone must prove a product assumption with a usable artifact. The team
should not build a hosted platform, broad dashboard, or multi-engine layer
before the independent Agent workflow works on a real game. Workbench features
must directly support that validated workflow.

## Milestone 0: Design baseline

**Goal:** Establish a coherent product boundary and implementation plan.

Deliverables:

- product, architecture, workflow, CLI, and skill design documents;
- documented reference research and license risks;
- MVP scope and acceptance criteria;
- initial architecture decisions.

Exit criteria:

- The relationship among Loopforge Agent, internal Skills, deterministic core,
  Kura, engine, Workbench and human reviewer is unambiguous.
- MVP non-goals prevent an accidental generic-agent platform build.

## Milestone 1: State and evidence CLI

**Goal:** Make a game-development session resumable and auditable.

Deliverables:

- `loopforge init`, `inspect`, `status`, `validate`, and `history`;
- schema-versioned project, event, derived state, and evidence records;
- project locking, optimistic revision checks, and explicit reconciliation;
- evidence source identity, subject revision, trust, and freshness checks;
- atomic derived writes and actionable diagnostics;
- tests for invalid transitions, interrupted writes, concurrent mutations,
  stale evidence, and missing evidence.

Exit criteria:

- A fresh fixture project can be initialized, inspected, resumed, and validated.
- Invalid or corrupted state fails without silent repair or data loss.
- A committed event can rebuild a missing or stale state snapshot.
- Concurrent stale writes fail without overwriting newer state.

## Milestone 2: Prototype workflow

**Goal:** Let an existing coding agent move from hypothesis to a verified
playable prototype.

Deliverables:

- `loopforge-router` and `prototype-gameplay` skills, with discovery and
  playtest procedures initially included in `prototype-gameplay`;
- hypothesis records, discovery gate checks, and guarded `advance` transitions;
- Godot headless build/test execution with run records and tool-generated
  evidence;
- hypothesis, prototype brief, and decision templates;
- first engine adapter;
- build, smoke-test, capture, and prototype gate commands;
- positive/negative trigger and procedural skill evaluations.

Exit criteria:

- Codex can use Loopforge to create a small playable prototype in a fixture or
  real project.
- The CLI blocks advancement when the prototype cannot be built or played.

## Milestone 3: Human playtest loop

**Goal:** Turn observed play into an explicit product decision.

Deliverables:

- evaluated playtest procedure, split into `run-playtest` only if trigger or
  context results justify a separate installed skill;
- playtest protocol and report schemas;
- import, validation, and evidence commands;
- `keep`, `kill`, and `refactor` decision records;
- privacy and consent guidance.

Exit criteria:

- A decision cannot be recorded without cited evidence and a human approver.
- Raw observations remain distinguishable from interpretations.
- An early technical or scope decision may be `kill` or `refactor`, but cannot
  produce a `keep` decision or a human-playtested claim.

## Milestone 4: Representative vertical slice

**Goal:** Add a controlled art, audio, and integration workflow after gameplay
validation.

Deliverables:

- `direct-game-art` and engine implementation skills;
- art direction and asset manifest schemas;
- representative-target approval gate;
- asset technical checks and in-engine captures;
- integrated runtime, visual, and performance evidence.

Exit criteria:

- One representative slice can be rebuilt and reviewed without relying on chat
  memory.
- Batch asset production cannot begin before target approval.

## Milestone 5: Portability and distribution

**Goal:** Verify that the core workflow is not accidentally Codex-only.

Deliverables:

- generic host adapter guidance;
- compatibility tests on at least one additional Agent Skills host;
- installation and packaging strategy;
- optional Codex plugin packaging after the standalone workflow is stable.

Exit criteria:

- Core skill outputs and CLI state remain compatible across tested hosts.
- Host-specific capabilities fail or degrade explicitly.

## Deferred

- Hosted project dashboard.
- Background job queues.
- Multi-user collaboration and permissions.
- Multi-model routing.
- Unity, Unreal, Roblox, and console adapters.
- Store publishing automation.
- Remote playtest recruitment or analytics service.
