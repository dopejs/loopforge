# Open Questions

These decisions should be resolved with short spikes or explicit product
choices before their dependent implementation begins. They are not blockers for
the current design baseline.

## 1. CLI implementation language

Decision: Python 3.11 or newer. See
[ADR 0005](../decisions/0005-cli-language.md) for the spike result and revisit
criteria.

The original candidates were:

- **Python:** fast schema and CLI development, natural fit for Godot automation
  and media scripts, simple installation in agent environments.
- **TypeScript:** strong package distribution through npm, good fit for browser
  game adapters, and direct compatibility with many coding-agent SDKs.
- **Go or Rust:** convenient single binaries, but higher initial development
  cost and less reuse from reference workflows.

Decision criteria:

- installation friction in Codex environments;
- atomic filesystem and process-control ergonomics;
- JSON Schema and YAML support;
- packaging for macOS, Linux, and Windows;
- ability to test engine adapters without global dependencies.

The MVP implementation uses a standard-library runtime and `uv` for isolated
development, tests, and packaging. TypeScript remains a valid future choice for
browser-heavy adapters but is not part of the MVP CLI.

## 2. First engine adapter

Current preference: Godot 4 2D.

Reasons:

- normal local project files;
- open-source engine and command-line execution;
- headless build and test potential;
- suitable for small prototypes;
- screenshot and runtime inspection options.

Unknowns to validate:

- reliable runtime interaction in CI and local Codex environments;
- cross-platform binary discovery;
- stable screenshot capture;
- test framework choice and version compatibility;
- whether web export is necessary for external playtesting in the MVP.

Recommended next action: create a disposable fixture with movement,
win/fail/restart, a headless smoke test, and a screenshot. Record exact setup and
failure cases before accepting an engine ADR.

## 3. Repository license

The repository currently has no license.

Decision criteria:

- intended open-source contribution model;
- whether commercial use and hosted derivatives should be allowed;
- compatibility with referenced code and future dependencies;
- whether skills, CLI code, templates, and bundled assets need different terms.

Until a license is chosen, do not copy implementation or substantial text from
external repositories. Research documents may link to and summarize sources.

## 4. Distribution model

Possible first channels:

- install the CLI from PyPI or npm;
- install skills from the Git repository;
- package Codex-specific integration as an optional plugin later;
- provide repository-local skills for teams that pin versions.

The portable skill source should remain independent of any one marketplace.

## 5. State and schema tooling

Decision for MVP version 1:

- JSON for canonical project configuration, machine-written state, evidence,
  and append-only records;
- YAML may be added later as a human-authored import format, but is not a second
  canonical representation;
- JSON Schema as the canonical validation format where practical.

The append-only event log, derived snapshot, locking, revision, reconciliation,
and migration rules are defined in
[ADR 0003](../decisions/0003-state-transactions-and-recovery.md). Evidence
identity and freshness are defined in
[ADR 0004](../decisions/0004-evidence-identity-and-claims.md).

## 6. Minimum human playtest evidence

The product must distinguish a workflow gate from a scientific claim. A single
external playtest may be sufficient to exercise the MVP workflow but is not
enough to generalize that a game is fun.

The MVP should record:

- participant relationship and relevant experience;
- whether the participant received help;
- raw behavioral observations;
- replay or continuation behavior;
- known sampling limitations;
- the human approver's confidence.

Do not encode a universal minimum participant count until real project data
supports it.

## 7. Skill packaging granularity

The initial map proposes seven skills. It may be too fragmented for early
testing.

Decision for the initial MVP experiment:

- implement `loopforge-router`;
- implement `prototype-gameplay` with discovery references included;
- implement `build-godot-game`;
- keep the discovery and playtest procedures within `prototype-gameplay` for
  the first end-to-end evaluations;
- split `discover-game` or `run-playtest` into separately installed skills only
  when observed context, trigger, or maintenance problems justify it.

This keeps the architecture composable without creating empty taxonomy.
