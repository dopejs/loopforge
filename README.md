# Loopforge

Loopforge is a portable game-development toolkit built from Agent Skills and a
deterministic CLI. It helps coding agents move from a game idea to tested,
evidence-backed playable builds without hiding project state inside a chat.

The project is now in early implementation. The Python CLI includes project
initialization, hash-chained event state, locking, reconciliation, read-only
project diagnostics, artifact integrity validation, evidence registration,
hypothesis records, guarded stage
advancement, a Godot build/test adapter, playtest import, and atomic prototype
decisions. `status` also derives scoped quality claims and marks them stale when
the source identity changes. The first repository-local workflow skills are
included. Validation against a real Godot installation and production-stage
release skills are not implemented yet. The production art workflow now covers
representative-target approval, provenance-aware asset manifests, deterministic
technical checks, and runtime visual review. The game-design workflow now
connects a kept prototype to an approved player promise, loop/system contract,
scope gate, production risks, and vertical-slice handoffs.

## Installation

### Prerequisites

- Python 3.11 or newer;
- [uv](https://docs.astral.sh/uv/getting-started/installation/);
- Git;
- Godot 4 only when using the Godot build workflow.

### Clone and verify

```bash
git clone https://github.com/dopejs/loopforge.git
cd loopforge
uv sync --locked
uv run loopforge --help
uv run python -m unittest discover -s tests -v
```

`uv sync --locked` creates an isolated environment from the committed lockfile.
Use this setup when developing Loopforge or changing its Skills.

### Install the CLI

From the cloned repository:

```bash
uv tool install .
loopforge --help
```

To update the tool after pulling a newer revision:

```bash
uv tool install --force .
```

The package has not been published to PyPI, so install it from a reviewed clone
or a pinned Git revision rather than assuming `uv tool install loopforge` refers
to this project.

### Install the Codex Skills

The portable Skills live under [`skills/`](skills/). For a personal Codex
installation, symlink each Skill into `~/.codex/skills` from the repository
root:

```bash
mkdir -p ~/.codex/skills
ln -s "$PWD/skills/loopforge-router" ~/.codex/skills/loopforge-router
ln -s "$PWD/skills/prototype-gameplay" ~/.codex/skills/prototype-gameplay
ln -s "$PWD/skills/build-godot-game" ~/.codex/skills/build-godot-game
ln -s "$PWD/skills/design-game" ~/.codex/skills/design-game
ln -s "$PWD/skills/direct-game-art" ~/.codex/skills/direct-game-art
```

The commands intentionally do not overwrite an existing installation. Remove or
rename an older Skill only after reviewing local changes. Other Agent
Skills-compatible hosts can load the same directories using their host-specific
Skill path.

### Initialize a game project

Run the installed CLI from the root of the game repository:

```bash
loopforge inspect --format json
loopforge init --format json
loopforge doctor --format json
loopforge status --format json
```

Then invoke `$loopforge-router` in the coding agent. It reads durable project
state and routes the next action to gameplay prototyping, Godot implementation,
game design, or art production without treating chat history as project state.

### Uninstall

```bash
uv tool uninstall loopforge
```

Remove only the Skill symlinks that point to this clone. Project-owned
`.loopforge` history and evidence are not removed by uninstalling the CLI.

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
