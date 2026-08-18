# Game Design Framework

Use this reference for `TRIAGE`, `DESIGN_CONTRACT`, and substantial `REVIEW`
work. The goal is a causal design model, not a long feature inventory.

## Design Nucleus

The design nucleus is the repeated tradeoff that makes the game behave
differently. A theme, genre label, control scheme, or content quantity is not a
nucleus by itself.

For each credible option record:

| Field | Requirement |
|---|---|
| Repeated tradeoff | What the player repeatedly chooses between |
| Behavior change | How it changes action, timing, routing, planning, or expression |
| Audience desire | The motivation it serves and likely rejection point |
| Proven foundation | Which prototype observation or user constraint supports it |
| Assumptions | What remains unproved and its impact |
| Cheapest test | The smallest observation that could reject it |
| Production profile | Platform, team, content, technology, and operational needs |

Select a nucleus because it creates the intended behavior under feasible
constraints, not because its pitch sounds novel.

## Player Promise

Define three connected promises:

1. **Marketing:** the concrete identity, action, conflict, and visible payoff
   that cause the intended player to care.
2. **First ten minutes:** the action and consequence a new player must actually
   experience without facilitator explanation.
3. **Long term:** the mastery, expression, discovery, relationship, or strategic
   change that makes repetition meaningful.

Each system must serve at least one promise. Monetization, progression, and
content cadence must not contradict the promised emotion or fairness model.

## Loop Model

Use three time scales where applicable:

| Loop | Typical scale | Design question |
|---|---|---|
| Moment | 3-30 seconds | What does the player perceive, decide, do, and understand now? |
| Session | One run, level, match, or chapter | How do risk, difficulty, and stakes develop and resolve? |
| Meta | Across sessions | How does knowledge, capability, expression, or possibility change? |

For every loop define:

```text
goal -> action -> choice -> risk -> feedback -> reward -> next constraint
```

Reject loops that only add rewards, menus, or numbers without changing the
next decision. Preserve restart and recovery paths; failure without a readable
cause or useful next choice is not a complete loop.

## System Contract

Every retained system answers:

- Which loop and player promise does it serve?
- What player behavior changes because it exists?
- What are its inputs, outputs, state, and dependencies?
- How does the player perceive success, failure, and uncertainty?
- What balancing knobs exist without assuming final values?
- What is the smallest validation and explicit deletion condition?

For economy and progression also record sources, sinks, conversions, caps,
failure recovery, pacing assumptions, exploit risks, and telemetry needs.

## Experience Coverage

The design must account for:

- onboarding and control discovery;
- readable success, failure, and state transitions;
- difficulty and assistance without relying only on hidden numerical changes;
- accessibility of critical information beyond color alone;
- pause, restart, save, disconnect, and return behavior when applicable;
- bounded content variation and the throughput needed to sustain it;
- theme expressed through player action and consequence, not only exposition.

## Evidence Boundary

Classify important statements as:

- `provided`: direct user constraint or project fact;
- `derived`: reasoning traceable to provided facts;
- `external_evidence`: current cited source;
- `assumption`: testable belief with confidence and impact;
- `unknown`: material information not yet available;
- `contradicted`: available evidence conflicts with the claim.

Do not convert an assumption into a requirement merely by repeating it in the
GDD. When evidence changes, update the assumption and every dependent system or
scope item.
