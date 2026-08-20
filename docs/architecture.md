# System Architecture

## 1. Overview

Loopforge separates its domain Agent from deterministic workflow operations and
from the generic Kura runtime.

```text
User
  |
  v
Tauri + React desktop client
  |-- owns only the Loopforge Agent sidecar lifecycle
  |-- calls the versioned Loopforge Agent API
  v
Loopforge Agent
  |-- owns project context, sessions, planning and tool selection
  |-- loads internal Skills and requests human approvals
  |-- delegates generic execution to Kura
  |                         |
  |                         v
  |                 Kura daemon
  |                 |-- owns generic model/session/runtime capabilities
  |                 `-- contains no Loopforge routes, types or state
  |
Loopforge Core + internal CLI
  |-- validates state and schemas
  |-- writes project state and Agent context
  |-- runs engine/build/test adapters
  |-- records evidence and decisions
  |-- enforces transition gates
  v
Normal game repository + .loopforge state
```

The versioned schemas in [`../contracts`](../contracts) are owned by Loopforge,
including the Workbench-to-Agent wire contract.
Application adapters map them to public Kura, Deckle, and Doper contracts; the
public libraries do not import Loopforge types or expose Loopforge-named APIs.
React never spawns subprocesses, calls Kura or imports runtime internals. Tauri
starts the Loopforge Agent but does not orchestrate Kura. Deckle and Doper are
consumed through public packages and Loopforge-owned adapters. The desktop app
bundles the Loopforge Agent and pins Kura as a reviewed runtime dependency. The
Agent, not the UI, owns Kura lifecycle and requests.

## 2. Component responsibilities

### Agent layer

Owns the domain behavior visible to users:

- project opening and redacted context assembly;
- session continuity, planning and tool selection;
- workflow routing and approval requests;
- delegation to deterministic core operations and generic Kura capabilities;
- recovery status and versioned Workbench APIs.

### Skill layer

Owns work that requires context-sensitive judgment:

- game discovery and design interviews;
- hypothesis and prototype framing;
- art direction and asset-family planning;
- level, system, audio, UI, and game-feel guidance;
- interpretation of technical and playtest evidence;
- recommendations for `keep`, `kill`, or `refactor`;
- review instructions and escalation rules.

Skills are internal Agent capabilities. They may call scripts and deterministic
core adapters, but should not duplicate schemas or state-transition logic.

### Core and CLI layer

Owns work requiring deterministic behavior:

- project initialization and inspection;
- state-machine transitions;
- append-only event commits and derived state snapshots;
- schema validation;
- evidence registration and checksums;
- build, test, capture, and report adapters;
- stage gates and human-approval records;
- idempotent resume and failure recovery;
- revision checks, project locking, and reconciliation;
- machine-readable output and exit codes.

The CLI remains a compatibility, debugging and headless automation adapter over
the same deterministic behavior consumed by the Agent. It is not the product
control plane and does not decide whether evidence proves that a game is fun.

### Adapter layer

Adapters isolate host and engine differences:

- engine detection and version reading;
- build and test commands;
- screenshot or frame capture;
- editor or runtime launch;
- image, audio, and 3D tooling availability;
- optional host-specific conventions.

The MVP will implement one engine adapter rather than a shallow abstraction
over every engine.

### Human layer

Humans own decisions that cannot be delegated safely:

- selecting a product direction among meaningful alternatives;
- accepting the representative art direction;
- providing or approving external playtest evidence;
- confirming `keep`, `kill`, or significant scope changes;
- approving a release candidate.

The local MVP records human attribution and intent. It does not claim that a
locally entered identity is cryptographically authenticated.

## 3. Proposed repository structure

```text
loopforge/
├── apps/
│   ├── agent/
│   │   └── loopforge_agent/
│   └── workbench/
├── docs/
├── skills/
│   ├── loopforge-router/
│   ├── discover-game/
│   ├── prototype-gameplay/
│   ├── run-playtest/
│   ├── design-game/
│   ├── direct-game-art/
│   ├── build-godot-game/
│   └── review-game-release/
├── cli/                     # internal/headless compatibility adapter
├── contracts/
├── tests/
│   ├── cli/
│   ├── skills/
│   └── fixtures/
└── examples/
```

This is a target shape, not a requirement to create empty directories before
implementation needs them.

## 4. Project-local state

Loopforge-managed game projects use a `.loopforge/` directory:

```text
.loopforge/
├── project.json
├── events.jsonl
├── state.json
├── lock
├── hypotheses/
├── evidence/
│   ├── builds/
│   ├── tests/
│   ├── captures/
│   └── playtests/
├── reports/
├── runs/
└── staging/
```

### State rules

- Files use explicit schema versions.
- `events.jsonl` is the canonical record of committed mutations.
- `state.json` is a derived snapshot and carries the project revision from
  which it was built.
- Mutating commands use an exclusive project lock and revision comparison.
- Event append is the commit point; derived files use atomic replacement.
- Append-only records use JSON Lines with sequence and hash-chain validation.
- Large artifacts may remain outside `.loopforge/`; evidence records store a
  stable path, checksum, timestamp, producer, subject revision, source identity,
  trust level, and relevant environment metadata.
- Project-owned paths are repository-relative. External artifacts use an
  explicit URI or normalized absolute path and may become unavailable.
- State must be reconstructable from the event log and referenced records; no
  hidden cloud database is required.
- Unknown schema versions fail visibly instead of being guessed.

The full transaction and recovery protocol is defined in
[ADR 0003](decisions/0003-state-transactions-and-recovery.md). Evidence identity
and freshness rules are defined in
[ADR 0004](decisions/0004-evidence-identity-and-claims.md).

## 5. State model

The lifecycle applies to one active experiment:

```text
UNINITIALIZED
  -> DISCOVERY
  -> PROTOTYPING
       |-> PLAYTEST_REQUIRED
       |     `-> PROTOTYPE_DECISION
       `-> PROTOTYPE_DECISION  (early technical or scope decision)
             |-> KILLED
             |-> PROTOTYPING   (refactor)
             `-> VERTICAL_SLICE (keep after playtest only)
  -> PRODUCTION_CANDIDATE
  -> RELEASE_REVIEW
  -> RELEASE_APPROVED

KILLED
  -> DISCOVERY               (new experiment)
```

An early decision may only `kill` or `refactor`; `keep` requires external human
playtest evidence. `KILLED` terminates an experiment, not the repository. The
complete transition requirements are defined in [gates.md](gates.md).

Quality claims are orthogonal derived results rather than a single `complete`
state:

```text
TECHNICALLY_VALIDATED
VISUALLY_REVIEWED
HUMAN_PLAYTESTED
FUN_HYPOTHESIS_SUPPORTED
RELEASE_APPROVED
```

This prevents a passing build from being misrepresented as a validated game.
Each claim reports `satisfied`, `failed`, `unknown`, or `stale` and cites the
evidence used to derive it.

## 6. Portability

The core format should follow the open Agent Skills convention. Host-specific
files are optional adapters:

```text
integrations/
├── codex/
├── claude-code/
└── generic/
```

Portable skills should describe capabilities instead of assuming exact tool
names. For example, request an available image-generation capability and define
a fallback that produces an asset brief and manifest.

## 7. Security and operational constraints

- Default to workspace-scoped writes.
- Print commands and artifact paths in machine-readable run records.
- Never upload proprietary source or assets without explicit configuration.
- Treat downloaded assets and scripts as untrusted inputs.
- Execute adapter commands as argument arrays rather than interpolated shell
  strings where practical; record working directory and filtered environment.
- Record asset provenance and license terms.
- Redact secrets from commands, environment summaries, and logs.
- Keep sensitive playtest recordings outside version control by default and
  record consent, retention, and deletion metadata.
- Require explicit confirmation for destructive cleanup, publishing, store
  uploads, payment integrations, and irreversible migrations.
- Ensure interrupted commands can be safely retried or clearly marked as
  requiring reconciliation.

## 8. Evolution threshold

Loopforge uses Kura for local runtime capabilities instead of building an
independent agent service. Unattended queues, remote wake-up, multi-project
scheduling, multi-tenant access, or model routing must remain Kura capabilities
behind the versioned boundary. Loopforge should add only game-domain contracts,
deterministic tools, and evidence workflows; replacing or bypassing Kura would
require a new architecture decision.
