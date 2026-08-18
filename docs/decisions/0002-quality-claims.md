# ADR 0002: Keep Quality Claims Separate

- Status: Accepted
- Date: 2026-08-18

## Context

Game projects can build successfully while being visually broken, hard to
understand, or uninteresting. A single `complete` or `passed` state hides these
different claims and encourages automated systems to overstate success.

## Decision

Represent quality as separate evidence-backed, derived claims:

- `TECHNICALLY_VALIDATED`
- `VISUALLY_REVIEWED`
- `HUMAN_PLAYTESTED`
- `FUN_HYPOTHESIS_SUPPORTED`
- `RELEASE_APPROVED`

No automated test, visual model, or coding agent may satisfy the external human
playtest claim by itself.

Claims are evaluated against the active experiment and project revision. They
report `satisfied`, `failed`, `unknown`, or `stale` and cite their supporting and
contradicting evidence. They are not persisted as permanent Boolean truth. The
applicability rules are defined in ADR 0004.

## Consequences

- Status output is more honest but slightly more complex.
- Gates can require the exact kind of evidence appropriate to the next stage.
- Users can distinguish missing evidence from failed evidence.
- A release can be blocked without invalidating unrelated technical work.
