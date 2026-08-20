<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/svg/loopforge-horizontal-dark.svg">
    <img alt="Loopforge" src="brand/svg/loopforge-horizontal-light.svg" width="340">
  </picture>
</p>

# Loopforge

[English](README.md) | [简体中文](README.zh-CN.md)

Loopforge is an independent, local game-development agent. It works inside a
normal game repository, turns ideas into playable experiments, gathers
technical and human evidence, and helps make explicit keep, kill, or refactor
decisions.

The Loopforge Agent is the product control plane. The desktop Workbench is its
primary user interface. The CLI and versioned Skills remain available as
internal execution, automation, and debugging capabilities; users should not
have to start the Agent or orchestrate those capabilities manually.

## The product

The Workbench opens a game repository as a project through the native folder
picker. Selecting a project starts or reconnects its Loopforge Agent
automatically and loads constrained project context without exposing provider
credentials, environment variables, or access tokens.

The interface is organized around the project rather than the Agent process:

- the project menu switches repositories and project-level views;
- the project header contains project identity and necessary actions;
- the main work area hosts mode-specific game-development tools;
- a floating mode toolbar switches between exploration, design, build, and
  test contexts;
- the Agent chat remains available beside the work rather than replacing it.

Project state and evidence stay in the game repository. Chat history is not the
only record of what happened.

## Architecture and ownership

```text
User
  |
  v
Workbench (Tauri + React)
  |-- opens projects and presents tools, evidence, and chat
  |-- owns only the Loopforge Agent sidecar lifecycle
  v
Loopforge Agent
  |-- owns project context, planning, sessions, and tool selection
  |-- invokes internal Skills and deterministic operations
  v
Loopforge core + CLI adapter ----> game repository + .loopforge state
  |
  `----> Kura generic model/session/runtime capabilities
```

The boundaries are deliberate:

- `apps/agent` contains Loopforge's domain Agent and user-visible behavior.
- `apps/workbench` contains the desktop product interface and its narrow native
  boundary.
- `cli` contains deterministic project operations plus a headless compatibility
  and diagnostics adapter. It is not the product control plane.
- `skills` contains versioned Agent capabilities for workflows requiring
  contextual judgment. They are not the primary UI.
- `contracts` contains Loopforge-owned, versioned wire and project schemas.
- Kura supplies generic model, session, and runtime behavior. It contains no
  Loopforge routes, types, files, or domain state.
- Deckle and Doper are public libraries for visual artifacts and native
  rendering. Loopforge-specific behavior belongs in application adapters, not
  in those libraries.

The release application embeds the Loopforge Agent and its pinned Kura sidecar.
The Workbench talks to the Loopforge Agent contract; it does not call Kura or
spawn workflow commands directly.

## Repository layout

```text
loopforge/
├── apps/
│   ├── agent/                 # independent Loopforge Agent
│   └── workbench/             # Tauri + React desktop application
│       └── vendor/kura/       # pinned generic runtime submodule
├── cli/                       # deterministic core and headless adapter
├── contracts/                 # Loopforge-owned versioned schemas
├── skills/                    # internal Agent workflow capabilities
├── tests/                     # Agent, CLI, and Skill tests
├── docs/                      # product, architecture, and decisions
└── dev.sh                     # root development launcher
```

## Develop the Workbench

Prerequisites:

- Git;
- Node.js 22 and pnpm;
- Rust and Cargo;
- Python 3.11+ and [uv](https://docs.astral.sh/uv/);
- Godot 4 only when developing or testing the Godot workflow.

Start the complete native development environment from the repository root:

```bash
git clone https://github.com/dopejs/loopforge.git
cd loopforge
./dev.sh
```

On the first run, the launcher initializes the pinned Kura submodule, installs
Workbench dependencies, and builds missing Agent and Kura sidecars. Later runs
reuse those sidecars and start the native Tauri app with Vite hot module
replacement.

Frontend React and CSS changes update without rebuilding release packages.
Rust or native configuration changes restart the Tauri development process.
Rebuild sidecars only when their code changes:

```bash
./dev.sh --rebuild-agent
./dev.sh --rebuild-kura
./dev.sh --rebuild-sidecars
```

For browser-only interface work:

```bash
cd apps/workbench
pnpm dev
```

Build the release desktop application and its embedded sidecars with:

```bash
git submodule update --init --recursive
cd apps/workbench
pnpm install --frozen-lockfile
pnpm build:desktop
```

## Internal CLI and Skills

The Python package is useful for developing deterministic operations, running
headless automation, and diagnosing project state. It is not required to use a
bundled Workbench release.

```bash
uv sync --locked
uv run loopforge --help
uv run loopforge inspect --format json
uv run loopforge doctor --format json
uv run python -m unittest discover -s tests -v
```

The package also contains the official Loopforge Skills. Developers testing
Skill installation can use an isolated destination:

```bash
uv run loopforge setup --skills-root /tmp/loopforge-skills
```

The package has not been published to PyPI. Do not assume
`uv tool install loopforge` refers to this repository.

## Evidence-backed workflow

Loopforge organizes game development around a repeatable learning loop:

```text
game idea -> falsifiable hypothesis -> smallest playable experiment
           -> technical checks -> human playtest -> keep / kill / refactor
           -> justified investment in design, art, and a vertical slice
```

Its current internal workflow capabilities cover routing, gameplay
prototyping, Godot 4 implementation, game design, and art direction. The
deterministic core records hash-chained events, stage transitions, build and
test evidence, playtest records, and recovery state under `.loopforge`.

Technical correctness, visual quality, playtest observations, and evidence of
fun remain separate claims. Creative, playtest, scope, and release-sensitive
decisions stay with a human reviewer.

## Current scope

Loopforge is in alpha. The independent Agent, Workbench shell, deterministic
core, CLI adapter, workflow contracts, and repository Skills are implemented
and tested. The current engine workflow focuses on Godot 4. Mode-specific
Workbench tools, broader engine adapters, hosted collaboration, and release
production automation are still under development.

## Product principles

- Make the independent Agent the product control plane and the Workbench the
  primary user experience.
- Keep CLI and Skills available behind the Agent boundary instead of requiring
  users to orchestrate them.
- Optimize for learning whether a game idea works, not merely completing a
  feature list.
- Keep state transitions, evidence, validation, and recovery deterministic and
  inspectable.
- Keep Loopforge domain behavior out of generic public libraries.
- Make every meaningful iteration playable or inspectable.
- Preserve human authority over creative direction, playtest interpretation,
  scope, and release decisions.

## Documents

- [Product design](docs/product.md)
- [System architecture](docs/architecture.md)
- [Development workflow](docs/workflow.md)
- [Stage and gate contracts](docs/gates.md)
- [CLI design](docs/cli.md)
- [Skill system](docs/skills.md)
- [Repository Skills](skills/README.md)
- [Roadmap](docs/planning/roadmap.md)
- [MVP plan](docs/planning/mvp.md)
- [Open questions](docs/planning/open-questions.md)
- [Architecture decisions](docs/decisions/)

## License

Copyright 2026 Loopforge contributors. Licensed under the
[Apache License 2.0](LICENSE).
