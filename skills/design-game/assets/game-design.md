# <Game Name> Game Design Document

## Document Identity

- Experiment ID: `<experiment-id>`
- Hypothesis revision: `<revision>`
- Design contract: `<project-relative-path>`
- Source/build identity: `<identity>`
- Platform: `<platform>`
- Team, budget, schedule: `<known-or-unknown>`
- Document status and revision: `<draft-or-approved>` / `<revision>`

## Executive Summary

State the one-sentence game concept, intended player experience, validated
foundation, current investment decision, and what this document makes possible.

## Source Inventory

| Source | Status | Claim supported | Limitation |
|---|---|---|---|
| `<artifact-or-input>` | `<provided/derived/external_evidence/assumption/unknown>` | `<claim>` | `<limitation>` |

## Design Nucleus

State the selected repeated player tradeoff, alternatives considered, why it
changes behavior, and why it fits the intended player and production profile.

## Target Player and Product Context

Define the intended player, audience rejection point, platform/input context,
session context, business model or distribution assumption, team capability,
budget, schedule, and operational constraints. Mark unavailable facts as
`unknown` with an owner and resolution step.

## Player Promise

### Marketing Promise

### First Ten Minutes

### Long-Term Promise

## Player Verbs, Controls, and Goals

List the player actions, control mapping, immediate goals, session goals, and
long-term goals. Explain how theme changes player action, constraint, or
consequence rather than only presentation.

## Moment Loop

Describe goal, actions, choice, risk, feedback, reward, and next constraint at
the 3-30 second scale.

## Session Loop

Describe goal, actions, choice, risk, feedback, reward, and next constraint for
one run, level, match, or chapter.

## Meta Loop

Describe goal, actions, choice, risk, feedback, reward, and next constraint
across sessions. Explain how it amplifies rather than replaces the moment loop.

## Systems

For every retained system, identify the loop and promise served, behavior
change, inputs, outputs, state, dependencies, player feedback, tuning controls,
smallest validation, and deletion condition. Keep stable IDs synchronized with
`design-contract.json`.

## Progression and Economy

Describe resources, sources, sinks, conversions, caps, pacing assumptions,
failure recovery, balancing controls, exploit risks, and telemetry needs. Use
explicit assumptions instead of inventing final balance values.

## Content and Experience Coverage

Describe onboarding, content variation, difficulty, assistance, success,
failure, restart, save/return, completion, replay, and the content throughput
needed to sustain the intended experience.

## UX, Onboarding, and Accessibility

Specify information hierarchy, feedback readability, input remapping, color and
non-color cues, text/audio alternatives, pause and recovery behavior, and the
first-session comprehension path.

## Narrative and World

Describe the setting, character or faction roles, narrative delivery, and how
world fiction affects play. If narrative is not applicable, state why and what
replaces its player-facing function.

## Art and Audio Direction

Define visual hierarchy, readability requirements, representative target,
animation/audio feedback, asset families, provenance constraints, and the
handoff boundary to `$direct-game-art`. Do not authorize a batch before the
representative target is approved.

## Technical and Platform Constraints

Record engine/version, target hardware, input, performance and memory budgets,
save/network needs, observability, fallback paths, integration risks, and
technical acceptance evidence. Unknown values require an owner and test.

## Scope Gate

| ID | Bucket | Proves | Dependencies | Owner | Delete condition |
|---|---|---|---|---|---|
| `<scope-id>` | `<mvp/vertical_slice/later/cut>` | `<promise-or-assumption>` | `<scope-ids>` | `<owner-or-unknown>` | `<condition>` |

Classify every proposed feature. Close dependencies before scheduling; an MVP
item cannot depend on a `later` or `cut` item.

## Vertical Slice

Define the representative start-to-finish path, included systems/content/assets,
onboarding, failure, restart, completion, return, technical and human evidence,
explicit non-goals, milestone owners, rollback points, and Go/Revise/Stop
criteria.

## Production Plan

Define milestones, owners, dependencies, content and asset throughput, review
cadence, test strategy, budget assumptions, and the condition for the next
investment. Do not schedule downstream production before its upstream gate.

## Assumption and Evidence Ledger

| ID | Statement | State | Confidence | Impact | Verification/evidence |
|---|---|---|---|---|---|
| `<assumption-id>` | `<testable-statement>` | `<planned/validated/invalidated/unknown/contradicted>` | `<low/medium/high>` | `<low/medium/high>` | `<method-or-evidence-id>` |

## Risk Register

| ID | Cause | Impact | Mitigation | Early trigger | Owner |
|---|---|---|---|---|---|
| `<risk-id>` | `<cause>` | `<impact>` | `<mitigation>` | `<trigger>` | `<owner-or-unknown>` |

## Validation and Investment Decision

Name the most dangerous assumptions, cheapest complete tests, observable pass
criteria, fail criteria, rollback or deletion rules, evidence owners, and the
condition for the next investment.

## Non-Goals

List explicitly excluded features, claims, platforms, content, and operational
obligations so they are not silently reintroduced.

## Approval

- Status: `pending`
- Approver ID: `<required-after-explicit-approval>`
- Approver name: `<required-after-explicit-approval>`
- Rationale: `<required-after-explicit-approval>`
- Approved at: `<required-after-explicit-approval>`

## Version History

| Revision | Date | Change | Decision/evidence |
|---|---|---|---|
| `<revision>` | `<date>` | `<change>` | `<decision-or-evidence-id>` |
