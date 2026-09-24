# Milestone 2 Skill Evaluation

- Date: 2026-09-23
- Result: **PASS**
- Skills: `loopforge-router`, `prototype-gameplay`, `build-godot-game`
- Gate: every task must score at least `0.90` for correctness and procedure
  following; a changed Skill must also lose no more than `0.05` against HEAD on
  either dimension.

## Method

Each task came from the checked-in JSON evalset. An independent model received
the exact Skill files named by that task and produced a text-only planning
answer without tools. A separate model turn received the shared `skill-eval`
rubric, prompt, expected behavior, and output, and returned correctness,
procedure-following, and conciseness scores.

The router was evaluated HEAD versus the working tree because its instructions
changed. The other two Skills were unchanged and were evaluated at the current
version. Evalset structure, referenced files, unique task IDs, and explicit
negative-trigger coverage are enforced by
`tests/skills/test_m2_evalsets.py`.

## Router regression gate

The `skill-eval` aggregate gate passed all six OLD→NEW comparisons.

| Task | Correctness | Procedure | Conciseness |
|---|---:|---:|---:|
| discovery routing | 0.86 → 1.00 | 0.72 → 0.99 | 0.82 → 0.98 |
| stale prototype recovery | 0.72 → 1.00 | 0.88 → 1.00 | 0.86 → 0.97 |
| decision routing | 0.95 → 1.00 | 0.98 → 1.00 | 0.97 → 0.96 |
| vertical-slice art routing | 0.95 → 0.96 | 0.97 → 0.99 | 0.94 → 0.97 |
| approved-design art routing | 0.83 → 1.00 | 0.80 → 1.00 | 0.90 → 0.98 |
| unrelated software negative | 1.00 → 1.00 | 1.00 → 1.00 | 0.96 → 0.98 |

NEW averages were `0.993` correctness, `0.997` procedure following, and
`0.973` conciseness. The minimum NEW correctness was `0.96`; the minimum NEW
procedure score was `0.99`. No correctness or procedure regression exceeded
the allowed `0.05`.

The recovery task initially exposed that the router could validate a stale
snapshot but could not actually perform previewed reconciliation. The final
version now publishes `loopforge_reconcile`, requires preview-before-apply from
intact history, and rereads revisioned status afterward. The decision task also
made evidence IDs, approver identity, rationale, and unknown release approval
explicit.

## Current-version procedural gate

| Skill / task | Correctness | Procedure | Conciseness |
|---|---:|---:|---:|
| prototype-gameplay / hypothesis | 0.99 | 0.99 | 0.96 |
| prototype-gameplay / playtest | 1.00 | 1.00 | 0.96 |
| prototype-gameplay / early decision | 0.99 | 0.97 | 0.93 |
| prototype-gameplay / recovery | 0.99 | 0.99 | 0.96 |
| prototype-gameplay / consent and mixed evidence | 1.00 | 1.00 | 0.91 |
| prototype-gameplay / production-GDD negative | 1.00 | 1.00 | 0.98 |
| build-godot-game / implement loop | 0.98 | 0.99 | 0.92 |
| build-godot-game / verification limits | 1.00 | 1.00 | 0.94 |
| build-godot-game / failure recovery | 1.00 | 1.00 | 0.94 |
| build-godot-game / non-Godot negative | 1.00 | 1.00 | 0.99 |

Across these ten tasks, averages were `0.995` correctness, `0.994` procedure
following, and `0.949` conciseness. Minimum correctness was `0.98`; minimum
procedure following was `0.97`.

## Residual observations

- Some answers include more downstream reporting detail than the prompt needs;
  this affects conciseness, not correctness or procedure.
- The early-decision answer could distinguish the advance into
  `PROTOTYPE_DECISION` from atomic decision recording more explicitly. Its
  procedure score remains `0.97`, above the gate.
- These evaluations measure routing and procedure. Real engine behavior is
  independently covered by `tests/cli/test_engine_integration.py`.
