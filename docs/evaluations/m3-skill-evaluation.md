# Milestone 3 Skill Evaluation

- Date: 2026-09-23
- Result: **PASS**
- Skill: `prototype-gameplay` external playtest and decision procedures
- Gate: no correctness or procedure-following regression greater than `0.05`
  from HEAD; every current task must score at least `0.90` on both dimensions.

## Method

Nine checked-in planning tasks were run once against the HEAD Skill files and
once against the final working-tree files. For every version/task pair, one
independent model received the exact `skill_files` plus the task prompt and
produced text without tools. A separate model turn received the shared
`skill-eval` rubric, expected behavior and output and returned correctness,
procedure-following and conciseness scores. The standard aggregate gate passed.

## Results

| Task | Correctness OLD → NEW | Procedure OLD → NEW | Conciseness OLD → NEW |
|---|---:|---:|---:|
| hypothesis | 1.00 → 1.00 | 1.00 → 1.00 | 0.97 → 0.98 |
| neutral external playtest | 1.00 → 1.00 | 1.00 → 1.00 | 0.93 → 0.98 |
| early technical decision | 1.00 → 1.00 | 1.00 → 1.00 | 0.97 → 0.95 |
| interrupted-state recovery | 1.00 → 1.00 | 1.00 → 1.00 | 0.98 → 0.99 |
| consent withdrawal and mixed evidence | 1.00 → 1.00 | 1.00 → 1.00 | 0.94 → 0.98 |
| production-GDD negative trigger | 1.00 → 1.00 | 1.00 → 1.00 | 0.99 → 1.00 |
| report-contract preflight | 1.00 → 1.00 | 1.00 → 1.00 | 0.99 → 0.99 |
| post-playtest decision | 1.00 → 1.00 | 1.00 → 1.00 | 0.95 → 0.99 |
| privacy minimization | 1.00 → 1.00 | 1.00 → 1.00 | 0.98 → 0.98 |

NEW averages were `1.000` correctness, `1.000` procedure following and `0.982`
conciseness. Minimum NEW correctness was `1.00`; minimum NEW procedure
following was `1.00`. No task regressed beyond the allowed threshold.

## Procedure decision

The playtest procedure remains inside `prototype-gameplay`. The expanded
positive, negative, recovery, consent, report-contract, decision and privacy
tasks found no trigger or context failure that justifies installing a separate
`run-playtest` Skill. Keeping one Skill also preserves the active hypothesis,
declared thresholds, tested-build identity and decision context without a
second handoff.

## Deterministic checks added beside the evaluation

- The Skill preflight rejects unknown report fields, blank list entries,
  missing build identity and unbounded content instead of cleaning them.
- The Core, Agent and Workbench use the same thirteen-field report vocabulary.
- A protocol binds the exact source/build identity; changed source or a report
  mismatch blocks import.
- Consent withdrawal is an append-only revocation event, removes stored report
  contents and makes the evidence ineligible for gates, claims and decisions.
- Decisions require intact, in-scope cited evidence and a non-blank human
  approver and rationale; `keep` still requires current external evidence.
