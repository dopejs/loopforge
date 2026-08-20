<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/svg/loopforge-horizontal-dark.svg">
    <img alt="Loopforge" src="brand/svg/loopforge-horizontal-light.svg" width="340">
  </picture>
</p>

# Loopforge

[English](README.md) | [简体中文](README.zh-CN.md)

Loopforge is a portable game-development toolkit built from Agent Skills and a
deterministic CLI. It helps coding agents move from a game idea to tested,
evidence-backed playable builds without hiding project state inside a chat.

Loopforge combines workflow Skills with a local state and evidence engine. The
coding agent remains the executor; Loopforge makes the work resumable,
reviewable, and explicit about what has or has not been proven.

## Local agent workbench

Loopforge is evolving into a Kura-powered local game-development workbench:

- `loopforge agent` manages a project-specific test daemon under
  `.loopforge/agent/data` without touching production data;
- the Tauri + React client uses a native proxy for project status, agent chat,
  and future visual tools;
- Deckle (`@dopejs/deckle-*`) owns visual artifacts, canvases, and revisions;
- Doper (`@dopejs/doper`) owns high-performance native rendering, scrolling,
  editing, and input;
- versioned JSON Schemas in `contracts/` belong to Loopforge and are translated
  by application-owned adapters into the public Deckle, Doper, and Kura
  contracts. Those libraries do not depend on Loopforge domain types. Kura is
  the runtime source of truth, while Loopforge remains authoritative for
  game-project state and evidence.

In an initialized game project, the first local-workbench workflow is:

```bash
loopforge agent start --format json
loopforge agent status --format json
loopforge agent context --format json
```

`agent context` exposes only constrained project metadata such as the project
path, stage, revision, and capabilities. It does not include environment
variables, provider credentials, or access tokens.

To build the desktop client from source, initialize its pinned Kura submodule:

```bash
git submodule update --init --recursive
cd apps/loopforge-desktop
pnpm install
pnpm build:desktop
```

The release build embeds the submodule's `dope-cli` binary as a Tauri resource,
so end users do not install a daemon separately. `dope-cli` is Kura's current
upstream package name; the product UI and repository use the Kura name.

For frontend iteration, use `pnpm dev:desktop`. It runs the native shell with
Vite hot module replacement and does not rebuild Kura or produce release
packages. Use `pnpm dev` when only the browser shell is needed.

## What Loopforge provides

### An evidence-backed game workflow

Loopforge organizes work around a repeatable learning loop rather than a
feature checklist:

```text
game idea -> falsifiable hypothesis -> smallest playable experiment
           -> technical checks -> human playtest -> keep / kill / refactor
           -> justified investment in design, art, and a vertical slice
```

Every stage has required outputs and gates. A prototype can be killed or
refactored without pretending that unfinished work is a failure.

### Five production Skills

- `loopforge-router` reads project state and selects the next applicable
  workflow.
- `prototype-gameplay` turns an idea into a bounded prototype, playtest, and
  explicit decision.
- `build-godot-game` implements and verifies a small Godot 4 gameplay loop.
- `design-game` delivers a complete, user-facing game design document (GDD), a
  synchronized scoped contract, and an evidence-aware review for a kept
  prototype.
- `direct-game-art` defines art direction, representative targets, asset
  manifests, provenance, and runtime visual review.

### A deterministic project CLI

The `loopforge` CLI stores project state in `.loopforge` and provides:

- hash-chained events, file locking, snapshots, and recovery checks;
- hypothesis records, stage gates, and atomic keep/kill/refactor decisions;
- Godot build and test commands with structured run evidence;
- evidence registration with checksums and source identity tracking;
- `status`, `doctor`, `validate`, and JSON output for agent automation.

### Guardrails for production work

Loopforge keeps technical correctness, visual quality, playtest observations,
and evidence of fun separate. It refuses unsafe state transitions, detects
stale artifacts, preserves local Skill changes during updates, and leaves
creative and release-sensitive decisions with a human reviewer.

### Current scope

The project is in alpha. The CLI, workflow contracts, and repository Skills are
implemented and tested; the current engine workflow focuses on Godot 4.
Full real-engine validation, broader engine adapters, hosted collaboration,
and release-production automation are not yet part of the MVP.

## Installation

### Prerequisites

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/getting-started/installation/);
- Git;
- Godot 4 only when using the Godot build workflow.

### Install Loopforge

```bash
uv tool install git+https://github.com/dopejs/loopforge.git
loopforge setup --host codex
```

The package includes all official Loopforge Skills. `loopforge setup` copies
them into the shared Agent Skills directory at `~/.agents/skills`. It is safe
to run repeatedly: unchanged Skills are skipped and updates are applied only to
installations managed by Loopforge.

Run the command from the root of a game repository to initialize it:

```bash
loopforge inspect --format json
loopforge init --format json
loopforge doctor --format json
loopforge status --format json
```

Then invoke `$loopforge-router` in Codex. It reads durable project state and
routes the next action to gameplay prototyping, Godot implementation, game
design, or art production.

### Update

```bash
uv tool install --force git+https://github.com/dopejs/loopforge.git
loopforge setup --host codex
```

Before changing files, inspect what an update would do:

```bash
loopforge setup --host codex --dry-run
```

Loopforge refuses to overwrite a Skill that has local changes or an unmanaged
Skill with the same name. After reviewing the conflict, `--force` preserves the
existing directory as a timestamped backup before installing the bundled copy.
For reproducible environments, append a reviewed tag or commit to the Git URL,
for example `git+https://github.com/dopejs/loopforge.git@<commit>`.

### Uninstall

Remove the managed Skills before removing the CLI:

```bash
loopforge setup --host codex --uninstall
uv tool uninstall loopforge
```

Uninstall also refuses to remove locally modified Skills. `--force` moves each
modified Skill to a timestamped backup instead of deleting it. Uninstalling the
CLI and Skills does not remove project-owned `.loopforge` history or evidence.

### Develop from source

Clone the repository only when developing Loopforge or changing its Skills:

```bash
git clone https://github.com/dopejs/loopforge.git
cd loopforge
uv sync --locked
uv run loopforge --help
uv run python -m unittest discover -s tests -v
```

To test the repository Skills without replacing a personal installation, use a
temporary Skills root:

```bash
uv run loopforge setup --skills-root /tmp/loopforge-skills
```

The package has not been published to PyPI, so do not assume
`uv tool install loopforge` refers to this project.

## Product principles

- Optimize for learning whether a game idea works, not merely for completing a
  feature list.
- Keep creative judgment in skills and human review.
- Keep state transitions, validation, evidence, and recovery in the CLI.
- Use existing coding agents instead of building a proprietary agent runtime.
- Make every meaningful iteration playable or inspectable.
- Distinguish technical correctness, visual quality, human playtesting, and
  evidence of fun.

## Documents

- [Product design](docs/product.md)
- [System architecture](docs/architecture.md)
- [Development workflow](docs/workflow.md)
- [Stage and gate contracts](docs/gates.md)
- [CLI design](docs/cli.md)
- [Skill system](docs/skills.md)
- [Repository skills](skills/README.md)
- [Reference research](docs/research.md)
- [Roadmap](docs/planning/roadmap.md)
- [MVP plan](docs/planning/mvp.md)
- [Open questions](docs/planning/open-questions.md)
- [ADR 0001: Product shape](docs/decisions/0001-product-shape.md)
- [ADR 0002: Quality claims](docs/decisions/0002-quality-claims.md)
- [ADR 0003: State and recovery](docs/decisions/0003-state-transactions-and-recovery.md)
- [ADR 0004: Evidence and claims](docs/decisions/0004-evidence-identity-and-claims.md)
- [ADR 0005: CLI language](docs/decisions/0005-cli-language.md)

## Working definition

> Loopforge helps an existing coding agent repeatedly turn game ideas into
> playable experiments, collect evidence, and make explicit keep, kill, or
> refactor decisions.
