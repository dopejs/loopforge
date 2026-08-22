# ADR 0007: Separate User-Level State from Project State

- Status: Accepted
- Date: 2026-08-22

## Context

`.loopforge/` inside a repository holds project state: the event log, derived
snapshot, evidence and run records. [ADR 0003](0003-state-transactions-and-recovery.md)
makes the event log canonical, and [ADR 0004](0004-evidence-identity-and-claims.md)
computes a project fingerprint that deliberately excludes `.loopforge` so that
recording evidence does not invalidate it. Evidence paths are
repository-relative. All of this assumes the directory travels with the
project — copied, committed and read alongside the game it describes.

Some records do not fit that shape, and having nowhere to put them produced a
concrete dead end:

- **Provider credentials.** `docs/cli.md` already states that secrets must not
  live in `.loopforge` project files. With no user-level store, the Workbench
  showed a provider settings page that explained credentials were managed by
  the Agent's configuration and offered no way to reach it. A user holding a
  base URL, a key and a model had nowhere to put them.
- **Operator identity.** The approver recorded on every gate and decision lived
  in the Workbench's `localStorage`, which the Agent cannot read. Approvals
  therefore had to be passed in from the front end on every call, and any
  non-Workbench caller had no identity at all.
- **Recent projects and interface preferences.** Per-person, not per-game, and
  currently only known to the browser context that wrote them.

Storing these per project would duplicate one credential into every game
repository and make "who approved this" depend on which folder is open.

## Decision

Keep project state exactly where it is, and add a user-level store at
`~/.loopforge/loopforge.db`.

The dividing question is whether a record describes the game or the person:

| Belongs to the project (`.loopforge/`) | Belongs to the person (`~/.loopforge/`) |
| --- | --- |
| Event log, derived snapshot | Provider endpoint and credential |
| Evidence, runs, captures | Operator identity |
| Hypotheses, playtest protocols and reports | Recent projects |
| Decisions | Interface preferences |

The user-level store is SQLite rather than a spread of JSON files: the records
are related, several are lists that grow, and schema changes need an explicit
migration path rather than whatever shape a file happened to have. It carries
`PRAGMA user_version` and refuses to operate on a database written by a newer
build.

Project state does **not** move into SQLite. The event log's value comes from
being append-only, hash-chained, diffable and repairable by hand, which ADR
0003 chose deliberately over a database.

The Agent owns the user store. Credentials reach Kura as process environment
overrides at daemon start, so the key exists in exactly one place on disk
rather than being copied into each project's Kura configuration.

## Security boundary

The store is created `0600` in a `0700` directory. That is the whole of the
protection and it is stated plainly in the settings dialog: a key here is
plaintext in an ordinary file, exactly as it would be in JSON. SQLite is not
encryption. A backup or sync folder that copies the file copies the key.

Moving credentials into an OS keychain is a separate decision. It would remove
the plaintext-at-rest exposure but needs a distinct implementation per
platform, and this ADR does not preclude it: the store would then hold a
reference rather than the secret.

## Consequences

- The Workbench can offer provider configuration without ever holding the
  credential — it passes it to the Agent and reads back only whether one is
  set.
- Kura reads its provider configuration at startup, so saving one requires
  restarting the runtime. The surface says so rather than leaving the user to
  wonder why a saved endpoint does not answer.
- The Agent can read the operator identity itself, so an approval no longer
  depends on the front end supplying one.
- A project directory remains self-contained for everything that describes the
  game. Moving a project between machines carries its full history and loses
  only the local credential, which is the correct thing to lose.
- Two processes read this database — the Agent and the desktop shell — so it
  runs in WAL mode and connections are opened per operation rather than held.
