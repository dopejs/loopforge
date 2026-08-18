# Scope and Handoff

Read this reference before approving scope, writing a vertical-slice plan, or
handing work to art and implementation.

## Scope Buckets

| Bucket | Meaning | Admission rule |
|---|---|---|
| `mvp` | Required to validate the design nucleus | Removing it makes the dangerous assumption untestable |
| `vertical_slice` | Required to prove representative final experience or production pipeline | It proves a named promise, quality bar, or throughput risk |
| `later` | Valuable only after the nucleus and slice are supported | It has a trigger for reconsideration and no current dependency blocker |
| `cut` | Harmful, unsupported, redundant, or infeasible | Record the reason so it is not silently reintroduced |

Every retained item needs a stable ID, owner or `unknown`, dependency list,
proof target, validation method, and deletion condition. Scope must be closed
under dependencies: an MVP item cannot depend on a `later` or `cut` item.

## Production Feasibility

Check each approved item against:

- team roles, ownership, parallelism, and unavailable expertise;
- platform input, memory, performance, certification, network, and save needs;
- art/audio asset count, variation method, review cost, and content throughput;
- technology maturity, fallback path, integration risk, and observability;
- schedule, budget, outsourcing, licensing, moderation, support, and live
  operations;
- business model effects on fairness, pacing, content, analytics, and service
  obligations.

Unknown capacity is not permission to assume an open world, real-time
multiplayer, live operations, high-volume branching narrative, or large bespoke
asset roster.

## Vertical Slice Contract

A vertical slice proves the smallest representative experience and production
path. It is not a miniature feature-complete game.

Define:

1. the player promise and dangerous assumptions it must prove;
2. one start-to-finish experience path including onboarding, failure, restart,
   completion, and return;
3. systems and content included by stable contract ID;
4. representative art, audio, UX, performance, and data needs;
5. explicit non-goals and placeholders;
6. milestone deliverables, owners, evidence, and rollback points;
7. human playtest protocol and technical validation;
8. Go, revise, and stop criteria for the next investment.

## Handoff Rules

- **Prototype:** hand off one falsifiable question, constraints, pass/fail
  signals, and the cheapest complete loop to `$prototype-gameplay`.
- **Art:** hand off approved player hierarchy, state readability, scope IDs,
  content quantities, platform framing, and performance budget to
  `$direct-game-art`. Do not prescribe asset batches before its representative
  target is approved.
- **Implementation:** hand off system IDs, inputs/outputs, dependencies,
  invariants, failure/restart behavior, budgets, and acceptance evidence to the
  engine Skill.
- **Review:** a downstream change to the hypothesis, nucleus, platform, business
  model, or scope invalidates affected handoffs. Reconcile the contract before
  continuing production.

Human approval covers the cited revision only. It does not authenticate market
claims, approve release, or waive technical, legal, art, and playtest gates.
