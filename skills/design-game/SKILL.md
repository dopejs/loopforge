---
name: design-game
description: Turn a validated game idea or kept Loopforge prototype into a production-bounded, testable game design contract and reviewable GDD. Use when defining player promise, design pillars, moment/session/meta loops, systems, progression, economy, content structure, scope, vertical slice, production risks, or when reviewing an existing GDD before art or implementation expansion. Do not use for proving that gameplay is fun, writing engine code, producing art assets, release approval, or unsupported market and revenue claims.
---

# Design Game

Convert validated gameplay learning into a coherent design that a team can
build, cut, review, and test. Preserve creative choices as human decisions and
keep facts, evidence, assumptions, and unknowns visibly separate.

## Operating Contract

1. Resolve the project root and run `loopforge inspect --format json`,
   `loopforge doctor --format json`, and `loopforge status --format json` before
   changing project artifacts. Reconcile stale derived state before relying on
   it; never edit `.loopforge` records directly.
2. Read the active experiment, approved hypothesis revision, prototype decision,
   external playtest evidence, current source identity, platform, team, budget,
   and schedule. Record unavailable inputs as `unknown`; do not silently invent
   them.
3. Keep project paths relative to the project root. Preserve existing GDD
   content and version history unless the user explicitly approves replacement.
4. Treat design documents as plans, not proof. Automated validation can prove
   structural consistency, not player value, balance, market demand, or human
   approval.

Read [references/design-framework.md](references/design-framework.md) when
creating or restructuring a design. Read
[references/scope-and-handoff.md](references/scope-and-handoff.md) before
committing scope or handing work to art and implementation. Read
[references/research-basis.md](references/research-basis.md) when changing this
workflow.

## Select One Mode

| Mode | Use when | Required outcome |
|---|---|---|
| `TRIAGE` | An idea has several plausible directions | Two to four design-nucleus options, assumptions, and one next decision |
| `DESIGN_CONTRACT` | A prototype was kept or a direction was selected | Player promise, loops, systems, scope, risks, and validation contract |
| `VERTICAL_SLICE` | The team needs the next production slice | Must-prove experience, bounded content/assets, milestones, and Go/No-Go criteria |
| `REVIEW` | A GDD or system plan already exists | Findings-first review, corrected contract, change log, and remaining unknowns |

Do not generate an encyclopedic GDD from a sentence. In `TRIAGE`, compare the
smallest plausible design nuclei first. If the user explicitly asks to continue
without choosing, recommend one but leave approval `pending` and keep downstream
production blocked.

## Required Design Sequence

1. **Source inventory:** cite user constraints, prototype evidence, current
   artifacts, external sources, and every material unknown.
2. **Design nucleus:** define the repeated player tradeoff that differentiates
   the game. Generate alternatives when more than one nucleus is credible.
3. **Player verbs and goals:** connect repeated actions to moment, session, and
   long-term goals. Theme counts only when it changes action, constraint, or
   consequence.
4. **Player promise:** specify the marketing promise, what the first ten minutes
   must prove, and why the player returns long term.
5. **Loops:** define moment, session, and meta loops as goal, action, choice,
   risk, feedback, reward, and next constraint. Avoid a meta loop that replaces
   rather than amplifies the proven moment loop.
6. **Systems:** add a system only when it names the loop served, behavior changed,
   inputs/outputs, feedback, smallest validation, and deletion condition.
7. **Progression and economy:** identify resources, sources, sinks, conversion
   rules, caps, pacing assumptions, failure recovery, and tuning controls. Never
   fabricate final balance values.
8. **Content and experience:** describe how a bounded set of content produces
   variation. Define onboarding, accessibility, difficulty, failure, restart,
   and completion states.
9. **Scope gate:** classify every feature as `mvp`, `vertical_slice`, `later`, or
   `cut`. State the evidence or promise each retained item proves and resolve
   dependencies before scheduling it.
10. **Feasibility and risk:** test the design against team capability, platform,
    content throughput, technology, art/audio cost, schedule, business model,
    and operational burden.
11. **Validation and decision:** name the most dangerous assumptions, cheapest
    tests, pass and fail criteria, rollback or deletion rules, and the next
    investment condition.

## Artifact Contract

Use the stable templates in `assets/`:

- `game-design.md`: human-readable design brief or GDD;
- `design-contract.json`: machine-checkable source of truth for loops, systems,
  scope, assumptions, risks, validation, and approval;
- `design-review.md`: findings, evidence limits, decision, and one next action.

The Markdown document explains intent. The JSON contract owns stable IDs,
dependencies, scope buckets, validation criteria, and approval state. Do not
derive these fields from headings or prose during implementation.

Validate before approving or handing off:

```bash
python <skill-dir>/scripts/validate_design.py \
  --project <project-root> --contract <design-contract.json> \
  --require-approved --format json
```

A non-zero result is blocked. Approval requires explicit approver identity,
rationale, timestamp, a concrete design document path, and a matching checksum.
Do not infer approval from silence, a prototype `keep` decision, or a positive
comment.

## Reference Games and External Claims

- Extract player behavior, decision structure, pacing, feedback, and production
  lessons; never copy protected names, characters, story, levels, terminology,
  art, or data.
- Use external research only when it could change the nucleus, audience,
  platform/business fit, scope, validation, or Go/No-Go decision.
- Label current evidence as `verified`, `partial`, `contradicted`, or
  `not_run`. A repository Star count is a discovery signal, not proof that a
  design pattern fits this game.
- Keep market size, retention, conversion, revenue, and schedule estimates as
  assumptions until they have cited, current evidence.

## Handoffs

- Route unproven core gameplay back to `$prototype-gameplay`; this Skill does
  not turn design confidence into playtest evidence.
- After the design contract is explicitly approved, route representative visual
  direction and asset planning to `$direct-game-art`.
- Route engine implementation to the applicable engine Skill, using contract
  IDs and scope buckets rather than prose guesses.
- Re-run design review when the hypothesis revision, nucleus, platform,
  business model, team capacity, or approved scope changes. Mark previous
  handoff evidence `stale` until reconciled.

## Completion Report

Report the experiment and hypothesis revision, design-contract path/checksum,
selected nucleus, approval status and identity, scope counts by bucket, highest
risks, assumption states, validation criteria, changed artifacts, stale
handoffs, limitations, and exactly one next action.

Never report `DESIGN_APPROVED`, production scope, final balance, market fit, or
human review unless the corresponding explicit decision and evidence exist.
