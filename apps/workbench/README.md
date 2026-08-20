# Loopforge Workbench

The desktop client is a Tauri 2 + React shell around the independent local
Loopforge Agent. React invokes a narrow native API and never calls Kura, spawns
shell commands or reads runtime internals. Tauri owns the Agent sidecar
lifecycle; the Agent owns its generic Kura runtime.

The first slice provides Agent health, redacted Loopforge project context and
chat. Deckle and Doper integrations should be added behind adapters after their
public facade contracts are pinned in this repository's `contracts/` directory.
The project context remains in `.loopforge/agent/context.json`; Kura has no
Loopforge-specific route, type, or persisted state.

Run the browser-only web shell with Vite hot module replacement:

```bash
pnpm install
pnpm dev
```

Run the native Tauri shell with the same frontend hot module replacement:

```bash
pnpm dev:desktop
```

Neither development command builds sidecars or packages an app. The native
command reuses `resources/loopforge-agent` and `resources/dope-cli` when they
exist. Run `pnpm build:agent` and `pnpm build:kura` once when full Agent
functionality is needed. Rust changes
cause Tauri to rebuild and restart the development app; React and CSS changes
do not.

The Tauri supervisor owns only the Loopforge Agent sidecar lifecycle. Add a
game project with the native folder picker; selecting a project starts or
reconnects its Agent automatically. The Agent owns Kura and uses the
deterministic Python core internally. The CLI remains available for headless
automation and debugging.

## Embedded sidecar build

`vendor/kura` is a git submodule pinned by the parent repository. The desktop
release command builds the independent Loopforge Agent plus the pinned Kura
runtime, places both in the Tauri resource bundle and removes Kura's Cargo
target directory afterwards:

```bash
git submodule update --init --recursive
pnpm build:desktop
```

At runtime Tauri resolves the Agent binary and the Agent resolves its bundled
Kura dependency. `LOOPFORGE_AGENT_BIN` overrides the Agent in development.
`LOOPFORGE_KURA_BIN` is the preferred development override;
`LOOPFORGE_DOPE_BIN` remains supported for compatibility. The binary is still
named `dope-cli` because that is the current upstream Kura package name.
