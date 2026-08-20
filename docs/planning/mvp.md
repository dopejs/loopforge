# MVP Plan

## 1. MVP question

Can the independent Loopforge Agent help a non-expert user produce a small
playable game prototype, preserve the process across sessions, and make an
evidence-based prototype decision while keeping its generic runtime and public
libraries domain-neutral?

## 2. Scope

The MVP covers:

- one product host: Loopforge Workbench, with Codex retained for compatibility
  and workflow evaluation;
- one engine and project shape, selected during implementation planning;
- one-player, local prototypes;
- discovery, hypothesis, prototyping, verification, playtest import, and
  keep/kill/refactor decision;
- local filesystem state only;
- CLI human and JSON output;
- repository-local Agent Skills.

The engine choice remains an explicit implementation decision. The current
preference is Godot 4 2D because it supports normal local projects, headless
execution, screenshots, and a broad range of prototype genres. This must be
validated with a thin technical spike before being locked.

## 3. Representative user journey

1. User opens a new or existing game repository in Loopforge Workbench.
2. Loopforge Agent opens or initializes the project through deterministic core
   operations and routes the next action internally.
3. The internal discovery procedure produces one hypothesis and
   a small validation plan.
4. User confirms the hypothesis.
5. Loopforge Agent implements the smallest playable loop using its internal
   prototype and engine capabilities.
6. Deterministic core operations run build, smoke test, and capture operations.
7. User conducts an external playtest using the generated protocol.
8. Loopforge Agent imports the report and uses its internal playtest procedure
   to analyze evidence.
9. User confirms `keep`, `kill`, or `refactor`.
10. CLI records the decision and presents the next allowed action.

## 4. Functional requirements

### CLI

- Initialize and inspect a project.
- Maintain schema-versioned stage and hypothesis state.
- Commit mutations to a revisioned event log and rebuild derived state.
- Reject concurrent stale writes and reconcile interrupted operations.
- Register evidence with checksums, provenance, source identity, subject
  revision, and trust level.
- Run the first engine's build and smoke-test commands.
- Capture or register runtime screenshots.
- Validate playtest reports.
- Check stage gates and record human-approved decisions.
- Recover predictably after interruption.

### Skills

- Route relevant requests without triggering on unrelated software work.
- Produce a falsifiable hypothesis rather than an unbounded GDD.
- Keep prototype scope to one experimental question.
- Require observable keep/kill criteria before implementation.
- Separate automated validation from human playtest conclusions.
- Use the CLI rather than simulating persistent state in prose.

## 5. Acceptance criteria

- A new user can complete the representative journey from documented commands.
- Closing and reopening Codex does not lose the current stage or evidence.
- A failed build prevents the playtest-ready transition.
- Technical infeasibility or an explicit scope limit can reach an early
  `kill`/`refactor` decision, but never `keep`.
- Missing or malformed human playtest evidence prevents a prototype decision.
- A decision cites evidence and records a human approver.
- Evidence from changed source or an earlier hypothesis is reported as stale and
  cannot silently satisfy a current gate.
- Concurrent mutations cannot silently overwrite one another.
- A committed event remains recoverable if snapshot replacement is interrupted.
- `loopforge status --format json` is stable and machine-readable.
- Every CLI command has tests for its success path and at least one failure path.
- Every MVP skill passes trigger and procedural evaluations.
- No output claims that a prototype is fun based only on automated evidence.

## 6. Test project

Use one deliberately small game to validate the MVP, for example:

> A 2D single-screen movement game where the player risks charging an action
> near moving hazards to multiply score.

The exact design is less important than its ability to exercise:

- input and movement;
- a clear risk/reward hypothesis;
- win/fail/restart flow;
- visible feedback;
- automated state verification;
- external observation of comprehension and replay behavior.

The test project must not be tailored so tightly to the skills that evaluation
becomes circular. A second unseen prototype prompt should be used before calling
the MVP generally useful.

## 7. Risks

### Workflow overhead overwhelms small projects

Mitigation: keep the MVP artifacts concise and expose a minimal mode without
removing state or evidence integrity.

### Agent follows documents but produces an uninteresting prototype

Mitigation: evaluate hypothesis quality and playtest analysis independently;
do not use technical completion as the product success criterion.

### Engine automation is unreliable

Mitigation: run a thin adapter spike before finalizing the engine and preserve
manual evidence registration as a fallback.

### Skill trigger conflicts

Mitigation: maintain explicit positive and negative trigger sets and use a
single router for broad game-development requests.

### Agent scope grows into a generic agent platform

Mitigation: keep Loopforge Agent domain-specific and delegate generic model,
session and execution capabilities to Kura. Do not add Loopforge domain routes
or types to Kura.

## 8. Verification strategy

- Unit-test state, schema, and gate logic.
- Integration-test the engine adapter using a fixture project.
- Run CLI recovery tests after simulated interrupted writes and failed tools.
- Run concurrency tests for lock contention and stale expected revisions.
- Run evidence invalidation tests after source, hypothesis, platform, profile,
  and consent changes.
- Evaluate skills against realistic prompts and raw project artifacts.
- Complete at least two end-to-end prototype runs, one expected `keep` or
  `refactor` and one expected `kill`.
- Have an external reviewer inspect whether reported conclusions match the raw
  evidence.
