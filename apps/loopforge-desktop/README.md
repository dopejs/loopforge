# Loopforge Workbench

The desktop client is a Tauri 2 + React shell around the local Kura
daemon. React invokes a narrow native proxy, which validates loopback-only Kura
URLs before exchanging HTTP JSON. React does not spawn shell commands or read
daemon internals.

The first slice provides daemon health, redacted Loopforge project context and
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

Neither development command builds a release daemon or packages an app. The
native command reuses `resources/dope-cli` when it already exists, or a daemon
selected through `LOOPFORGE_KURA_BIN`. Run `pnpm build:kura` once when daemon
functionality is needed and no development binary is available. Rust changes
cause Tauri to rebuild and restart the development app; React and CSS changes
do not.

The Tauri supervisor owns daemon lifecycle. Select a game project directory in
the desktop client and start Kura there; end users do not need a separately
installed daemon. The current alpha still uses the Python CLI for authoritative
project initialization, context sync, and headless automation. A future
self-contained package must embed that capability instead of reimplementing
Loopforge event replay in the UI or Tauri layer.

## Embedded Kura build

`vendor/kura` is a git submodule pinned by the parent repository. The
desktop release command builds the pinned `dope-cli` release binary, places it
in the Tauri resource bundle and removes the Cargo target directory afterwards:

```bash
git submodule update --init --recursive
pnpm build:desktop
```

At runtime the native supervisor resolves the bundled binary itself.
`LOOPFORGE_KURA_BIN` is the preferred development override;
`LOOPFORGE_DOPE_BIN` remains supported for compatibility. The binary is still
named `dope-cli` because that is the current upstream Kura package name.
