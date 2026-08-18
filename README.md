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
