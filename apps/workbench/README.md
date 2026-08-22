# Loopforge Workbench

The desktop client is a Tauri 2 + React shell around the independent local
Loopforge Agent. React invokes a narrow native API and never calls Kura, spawns
shell commands or reads runtime internals. Tauri owns the Agent sidecar
lifecycle; the Agent owns its generic Kura runtime.

The shell reads Agent health, redacted project context, streamed chat with its
history, engine run history and the provider inventory. Deckle and Doper
integrations should be added behind adapters after their public facade contracts
are pinned in this repository's `contracts/` directory. The project context
remains in `.loopforge/agent/context.json`; Kura has no Loopforge-specific
route, type, or persisted state.

## Workspaces

The shell implements the Workbench design: a mode rail, a project sidebar, the
active workspace and the Agent panel. What each workspace shows depends on
whether anything can actually serve it:

| Workspace | Source |
| --- | --- |
| Chat | Streams from Kura, with conversation history owned by the Agent |
| Terminal | Engine run history written by the deterministic core |
| Test | The same run history, narrowed to test runs, and can start one |
| Tasks | Project stage and derived quality claims |
| Provider settings | Kura's provider inventory and model-role routing |
| Canvas, Flow, Diff, Assets, Profiler | Designed chrome over placeholder data |

The remaining five carry a visible preview marker, so nothing on screen can be
mistaken for project data. `isWired()` in `src/modes.ts` is the single record of
which workspaces are real; move a mode into it once its data exists.

Several of these departed from the design once the real data was known, and
deliberately so:

- **Test** was designed with per-suite pass/fail counts and a frame-rate curve.
  The core runs the engine headless and captures process output, so that
  structure does not exist; producing it would mean parsing engine logs into
  numbers the runtime never reported.
- **Tasks** was designed as a four-column task board, which is a generic
  agent-product shape. Loopforge has no task model — it has a stage machine and
  orthogonal quality claims, and those are what decides keep, kill or refactor.
- **Add provider** was designed as a wizard over thirty sources. Kura exposes a
  fixed set of providers and the user configures one, so a catalogue would have
  offered choices that cannot be made.

Settings follows the same rule: Appearance, Language, General, Shortcuts and
Provider are real, while Permissions explains that the Agent owns that
configuration rather than showing controls that do nothing.

`chat` is the launch workspace.

## Interface language

The Workbench ships eight locales — English, Simplified Chinese, Traditional
Chinese, Japanese, Korean, Spanish, French and Arabic. It follows the operating
system language until a language is chosen in Settings.

`src/i18n/locales/en.ts` is the source of truth: every other catalogue is typed
as `Messages`, so a missing translation is a compile error, and the tests in
`src/i18n/locale.test.ts` additionally assert that no message is blank and that
interpolation placeholders match English in every locale.

Arabic renders right-to-left. The stylesheet uses CSS logical properties
throughout so the layout mirrors without a second stylesheet; use
`margin-inline`, `border-inline-*` and `inset-inline-*` rather than their
physical equivalents when adding styles. Filesystem paths keep `direction: ltr`
even in an RTL interface.

The design specifies Instrument Sans and JetBrains Mono from Google Fonts. The
app has no `font-src` in its CSP and runs fully offline, so the stylesheet falls
back to the closest system faces. Vendor the font files locally and extend the
CSP if the exact faces become a requirement.

Run the browser-only web shell with Vite hot module replacement:

```bash
pnpm install
pnpm dev
```

Run the native Tauri shell with the same frontend hot module replacement:

```bash
pnpm dev:desktop
```

`pnpm build:desktop` always rebuilds the Kura sidecar from the pinned
submodule commit, so a packaged app never ships a stale daemon. `./dev.sh`
reuses an existing sidecar to keep the frontend loop fast, but only when
`resources/kura.build.json` records the submodule commit that is currently
checked out; after a submodule bump it rebuilds automatically. Force one with
`./dev.sh --rebuild-kura`.

Neither development command builds sidecars or packages an app. The native
command reuses `resources/loopforge-agent` and `resources/kura` when they
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
`LOOPFORGE_DOPE_BIN` remains supported for compatibility. Upstream renamed the
daemon binary from `dope-cli` to `kura` (Cargo package `kura-cli`) and switched
its environment prefix from `DOPE_*` to `KURA_*` with no back-compat, so the
supervisor sets `KURA_ENV`/`KURA_DATA_DIR`/`KURA_BIND_ADDR`. The old binary
name is still probed so an existing bundle keeps working.
