---
name: prototype-gameplay
description: Run a production-grade Loopforge gameplay-prototype workflow from one game idea through a falsifiable hypothesis, bounded playable experiment, technical evidence, neutral external playtest, and human-confirmed keep/kill/refactor decision. Use when starting or resuming a Loopforge experiment, scoping gameplay validation, preparing or analyzing playtests, recovering stale or interrupted prototype work, or recording a prototype decision. Do not use for broad game design documents, production content expansion, release approval, non-game software work, or claims of fun based only on automated checks.
---

# Prototype Gameplay

Answer one player-behavior question with the cheapest honest playable test.
Persist state through Loopforge and leave every gate auditable.

## Operating Contract

1. Resolve the project root and a working CLI invocation: installed
   `loopforge`, or the repository's documented local invocation.
2. Run `loopforge inspect --format json`, `loopforge doctor --format json`, and
   `loopforge status --format json` before changing project or workflow state.
3. If uninitialized, run `loopforge init --format json`, then reread status.
4. Treat event history as canonical. Never edit `.loopforge` records directly.
5. Pass the latest returned revision through `--expected-revision` on every
   mutation. After exit code 5, reread status and re-evaluate; never blind-retry.
6. Stop mutations on integrity errors. Use `reconcile --dry-run` before
   `reconcile --yes`, and apply only a derived-state rebuild from intact history.

Read [references/operating-contract.md](references/operating-contract.md) before
executing transitions or recovering a failed command.

## Required Outputs

Produce only the artifacts required by the current stage:

| Stage | Required output | Exit condition |
|---|---|---|
| `DISCOVERY` | Approved hypothesis | Discovery gate passes |
| `PROTOTYPING` | Prototype brief, playable loop, fresh build/startup/capture evidence | Playtest gate passes and human confirms readiness |
| `PLAYTEST_REQUIRED` | Neutral protocol and external observation report | Decision gate passes |
| `PROTOTYPE_DECISION` | Evidence review and confirmed decision | Atomic decision command succeeds |

Create draft files with:

```bash
python <skill-dir>/scripts/prepare_workspace.py \
  --project <project-root> --artifact <name> --format json
```

Use `hypothesis`, `prototype-brief`, `playtest-protocol`, `playtest-report`,
`decision-review`, or `all`. The script never overwrites changed drafts unless
`--force` is explicit.

Before registering or importing a completed draft, run:

```bash
python <skill-dir>/scripts/validate_draft.py \
  --artifact <name> --file <draft-path> --format json
```

Treat a non-zero result as blocked. The CLI remains the final state and schema
authority; this preflight additionally rejects unfilled template placeholders.

Neutral-session invariant: the facilitator's only default prompt is "Please
play until you choose to stop." Never write or approve a validation plan that
has the facilitator give, state, or explain controls, goals, mechanics, or
strategies. Necessary cues belong in the tested build. Deviate only for safety,
an agreed accessibility need, or a predeclared research condition, and record
the intervention as a confound.

## Discovery

1. Identify intended player, platform/input, player fantasy, core verb, and the
   moment-to-moment loop. Ask only for missing choices that materially alter the
   experiment.
2. Write one falsifiable claim about observable behavior. Reject goals such as
   "make it fun" or "build the full game."
3. Bound the experiment with constraints and explicit non-goals.
4. Define the cheapest playable validation plus observable keep and kill
   signals. Signals must describe behavior, not compliments or feature counts.
   Plan a neutral external session from the outset and use the neutral-session
   invariant above.
5. Fill `hypothesis.md`, including its approval checkpoint. State the participant
   denominator, observation window, and inconclusive outcome between keep and
   kill thresholds. Validate that every heading contains concrete content.
6. Present the complete hypothesis and remaining uncertainty. Leave approval
   `pending` until the user provides an explicit decision, approver identity,
   and rationale; never infer or fabricate them.
7. Register the hypothesis, check `PROTOTYPING`, and advance only on a passing
   gate.

## Prototype

1. Fill `prototype-brief.md` before implementation. Keep one experimental
   question, one core loop, explicit controls, success/failure, and immediate
   restart. When voluntary replay is a keep signal, restart must require an
   observable player choice; automatic restart cannot support that signal.
2. Inspect the existing project and preserve compatible conventions. Keep
   disposable work localized; defer progression, accounts, content breadth,
   production polish, and unrelated refactors.
3. Use the available engine workflow. For Godot, use `$build-godot-game`. If no
   engine workflow exists, implement conservatively and register manual evidence
   with honest provenance; never label it tool-generated.
4. Run fresh build and startup checks. Capture the actual running play state,
   then inspect the image for blank output, menus, clipping, overlap, or a state
   that does not expose the tested behavior.
5. Run `gate check PLAYTEST_REQUIRED`. Regenerate stale evidence after any
   applicable source change.
6. Present the evidence, shortcuts, and known failures. Advance only after the
   user confirms this exact build is ready for external observation.

If technical or scope evidence makes the experiment infeasible, use the early
decision path. Early decisions allow only `kill` or `refactor`, never `keep`.

## External Playtest

Read [references/evidence-review.md](references/evidence-review.md) before
preparing or interpreting a session.

1. Bind `playtest-protocol.md` to the active experiment, hypothesis revision,
   and evidenced build/source identity.
2. Use a neutral task. Let participants discover controls from the build; do
   not teach controls, reveal the hypothesis, coach a strategy, or solicit
   positive feedback. Give only the minimum intervention required for safety,
   accessibility, or a predeclared research condition, and record the request,
   exact intervention, timing, and resulting confound.
3. Use a participant other than the implementing agent. Obtain consent before
   notes or media. For this external-session workflow, do not use `not_required`
   unless a written local policy was established before recruitment and no
   participant-linked data is collected. If consent is declined or withdrawn,
   stop and do not import the report.
4. Record ordered observable behavior in `raw_observations`; keep explanations
   in `interpretation`. Preserve confusion, failures, abandonment, and absence
   of replay.
5. Import the report only when required fields are complete and consent is
   `obtained` or legitimately `not_required`.
6. Check and advance to `PROTOTYPE_DECISION`. If no external participant is
   available, remain at `PLAYTEST_REQUIRED`.

Automated agents, the implementer, screenshots, and simulated personas cannot
satisfy the external playtest requirement.

## Decision

Fill `decision-review.md` with cited evidence IDs, strongest supporting and
contradicting observations, limitations, confidence, and one next action.
Recommend without deciding for the user:

- `keep` only when fresh external playtest behavior meets declared keep signals;
- `kill` when kill signals occur or the approach is infeasible;
- `refactor` when one specific revised hypothesis can resolve the uncertainty.

Obtain explicit decision, approver identity, and rationale. Run the matching
`loopforge decide` command with cited evidence IDs. For `refactor`, create a new
hypothesis draft and pass it with `--file`; preserve the prior revision.

## Completion Report

Finish with `loopforge validate --format json` and
`loopforge status --format json`. Report:

- stage, experiment ID, hypothesis revision, and project revision;
- artifacts created or changed;
- commands actually run and evidence IDs produced;
- every claim status, including `unknown` and `stale`;
- limitations, blocked gates, and exactly one next action.

Never report `RELEASE_APPROVED`, human playtesting, or fun unless the
corresponding evidence-backed claim explicitly supports it.
