# M0–M3 Acceptance Audit

- Date: 2026-09-24
- Scope: the engineering exit criteria in `docs/planning/roadmap.md` for
  Milestones 0 through 3.
- Product validation remains separate: `docs/planning/mvp.md` also calls for
  two actual external prototype sessions and an independent review of the raw
  observations. Those human activities have not been recorded in this repo;
  `mvp-field-validation.md` contains the handoff for arranging them.

| Milestone | Exit evidence | Remaining verification |
|---|---|---|
| M0 design baseline | `docs/product.md`, `docs/architecture.md`, `docs/workflow.md`, `docs/cli.md`, `docs/skills.md`, `docs/research.md`, the MVP plan and accepted ADRs define product ownership and non-goals. | None for the design baseline. |
| M1 state and evidence CLI | `tests/cli/test_milestone1.py` exercises initialization, replayable hash-chained history, corrupted state, stale revisions, lock contention, evidence freshness and reconciliation. A stale snapshot is backed up byte for byte before replacement; missing evidence prevents reconciliation. The Windows CI job passed on the committed snapshot. | None for the M1 code and automated gate. |
| M2 prototype workflow | `tests/cli/test_engine_integration.py` uses a real Godot 4 process for import, startup, failure, deterministic gameplay behavior and an actual recorded play-state frame. Godot source errors fail a run even with process exit code zero. Godot gates require tool-generated build and startup evidence plus a verified image and a human readiness rationale. Skill evaluation is in `m2-skill-evaluation.md`. Codex also created a distinct small game and verified its mechanics and CLI build/test path in `m2-unseen-prototype.md`; its hypothesis was approved and technical evidence rerun against that revision. The Linux Xvfb CI job passed on the committed snapshot. | The new game has not received a separate playtest-readiness approval, so it has not reached that stage; a Loopforge Agent live-model run is also unrecorded. Neither is counted as a passing human-playtest claim. |
| M3 human playtest loop | `contracts/loopforge-playtest-protocol-v1.schema.json` and `loopforge-playtest-report-v1.schema.json` define recorded protocol and report shapes. Agent, CLI and Workbench tests cover import, consent, separate raw observations and interpretation, evidence citations, early kill/refactor, and keep restrictions. Consent revocation invalidates claims and retries report deletion after an I/O failure. Skill evaluation is in `m3-skill-evaluation.md`. | Actual external participant observations and independent conclusion review remain pending under the MVP verification strategy. |

## Negative paths explicitly exercised

- Generic manual evidence cannot register an external playtest report; Godot
  manual build/test claims cannot satisfy its adapter gate.
- A missing or modified latest artifact is `invalid` at a stage gate and cannot
  reveal an older passing record as the current result.
- Text posing as an image cannot satisfy visual review. The real-engine fixture
  records a frame and verifies visible player and hazard pixels.
- A mismatched build identity, changed source, absent protocol, missing consent,
  malformed report, revoked report or absent approver blocks the relevant gate
  or decision.
- Reconciliation refuses to mask missing evidence, and an interrupted report
  deletion remains visible and retryable.

The skill evaluations test planning and routing behavior. They do not replace
the external participant and reviewer required to establish whether the
prototype conclusions match actual play.

## Local verification on 2026-09-24

- Python with Godot 4.7.2 available: `unittest discover` ran 590 tests, passed,
  with 17 skipped because the general suite lacked a Kura binary and live-model
  provider. A separate run against the pinned Kura binary passed all 18
  real-daemon integration tests. The CI jobs split these dependencies out.
- Real Godot engine integration: 9 tests passed, including recorded play-state
  pixels, a script parse error with exit code zero, and latest-artifact
  invalidation.
- Linux ARM64 (Ubuntu 24.04 VM, Godot 4.3, Xvfb and Mesa): all 9 real-engine
  integration tests passed, including runtime capture. The initial run exposed
  missing XCursor, Xinerama and XInput libraries; the CI install step now
  includes those packages. This local VM run does not replace the x86_64 CI job.
- Workbench: 260 tests passed; TypeScript typecheck and production Vite build
  passed.
- Tauri: 21 Rust tests passed.
- Changed Core and focused test files checked with Ruff; `git diff --check`, contract JSON parse,
  CI YAML parse, source distribution and wheel builds passed.

## Committed CI snapshot

[CI run 35959405346](https://github.com/dopejs/loopforge/actions/runs/35959405346)
passed all six jobs on the isolated branch at `7cae534`: Python, pinned-Kura
integration plus the approval-timeout contract, Workbench typecheck/build/tests,
Tauri check/tests, Windows revision/locking/recovery, and Linux Godot 4.3/Xvfb
runtime capture. The branch is a CI-only draft PR containing the current mixed
worktree snapshot; it has not been merged into `main`.

Full-repository Ruff and Rust formatting checks are not green in the shared
working tree and were not counted as passing verification. The local Ruff run
reported 217 issues; CI does not currently run that check.
