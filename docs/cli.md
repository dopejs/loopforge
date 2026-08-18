# CLI Design

## 1. Purpose

The `loopforge` CLI is a deterministic project-state and evidence tool. It does
not contain an LLM, judge subjective quality, or replace the coding agent.

The current alpha implements `setup`, `init`, `inspect`, `doctor`, `status`,
`validate`, `history`, `reconcile`, `hypothesis create/show`, `gate check`,
`advance`, `run build/test`, `capture screenshot`, `playtest create/import`,
`decide`, and `evidence add/list`. Real Godot runtime validation and
production-stage skills remain planned work; their contracts below describe the
target MVP interface.

## 2. Command principles

- Commands are composable and safe to rerun.
- Read-only commands never mutate project state.
- Mutating commands validate preconditions before writing.
- Human and model-friendly output are both supported.
- Failures return non-zero exit codes and leave actionable diagnostics.
- Commands do not advance stages implicitly after unrelated work.

Proposed global options:

```text
--project <path>
--format human|json
--quiet
--verbose
--no-color
--expected-revision <revision>
```

`--expected-revision` applies to mutations and provides optimistic concurrency
control. A mismatch leaves state unchanged and returns exit code 5. Agent-driven
workflows should pass the revision returned by the latest read command.

## 3. MVP commands

### Product installation

```bash
uv tool install git+https://github.com/dopejs/loopforge.git
loopforge setup --host codex
loopforge setup --host codex --dry-run
loopforge setup --host codex --uninstall
```

`setup` installs the Skills bundled in the Loopforge distribution into the
Codex Skills directory. It resolves that directory from `CODEX_HOME` or
`~/.codex`, and accepts `--skills-root` for another host adapter or an isolated
test environment. Installation is idempotent and records a management marker
in each Skill. Local changes and unmanaged conflicts are rejected by default;
`--force` preserves a timestamped backup before replacement or uninstall.

The JSON result is part of the CLI envelope contract and reports each Skill's
action (`install`, `update`, `skip`, or `uninstall`), digest, destination, and
backup path when one was created.

### Project lifecycle

```bash
loopforge init
loopforge inspect
loopforge status
```

- `init` creates schema-versioned `.loopforge` state without modifying engine
  source files.
- `inspect` detects engine, version, available commands, and relevant tooling.
- `status` displays the current stage, active experiment, derived quality
  claims, and next allowed actions. Claims have `satisfied`, `failed`, `stale`,
  or `unknown` status and cite applicable evidence and decision event IDs.

### Hypotheses and stages

```bash
loopforge hypothesis create --file hypothesis.md
loopforge hypothesis show
loopforge gate check <stage>
loopforge advance <stage>
```

- `gate check` is read-only and explains every pass, fail, or unknown result.
- `advance` requires a passing gate and records an append-only transition.
- If `--expected-revision` is omitted, mutating commands use the revision they
  observed as their implicit precondition. This keeps the convenient form safe
  under concurrent agent sessions.
- No `--force` option should bypass creative or human gates in the MVP.

### Execution evidence

```bash
loopforge run build
loopforge run test
loopforge capture screenshot
loopforge evidence add --type <type> --file <path> [--result passed|failed|observation]
loopforge evidence list
```

Engine adapters provide actual build and test commands. Each run records the
command, environment summary, timestamps, exit code, log path, and artifacts.
The current adapter supports Godot projects through headless `build` and `test`
operations. A missing Godot executable returns exit code 4; screenshot capture
is still a manual evidence path.

### Playtests and decisions

```bash
loopforge playtest create --protocol playtest.md
loopforge playtest import --file report.json
loopforge decide keep --evidence <id>...
loopforge decide kill --evidence <id>...
loopforge decide refactor --file revised-hypothesis.md --evidence <id>...
```

Decision commands require an identified approver and a written rationale. The
CLI validates completeness, not the correctness of the creative conclusion.
`decide` records the decision and its resulting stage transition in one event;
`refactor` also stores the new hypothesis revision in that event.

### Diagnostics

```bash
loopforge doctor
loopforge validate
loopforge history
loopforge reconcile --dry-run
loopforge reconcile --yes
```

- `doctor` checks state and referenced-artifact integrity, required executables,
  Godot 4 compatibility, main-scene configuration, completed runs without
  evidence, and uncommitted run artifacts. It is read-only: errors produce a
  non-zero exit, while recoverable orphan-run findings remain warnings.
- `validate` checks event/snapshot consistency and verifies the existence and
  checksums of registered evidence, hypothesis, revised-hypothesis, and playtest
  protocol artifacts. It is read-only and reports one or more structured
  diagnostics when an artifact has been removed or changed.
- `history` presents transitions, decisions, and relevant run records.
- `reconcile --dry-run` reports how event history, derived state, incomplete
  records, and orphan runs differ without writing.
- `reconcile --yes` performs only the reported recovery actions and requires
  explicit confirmation for quarantine or cleanup.

## 4. Output contract

JSON output should follow a stable envelope:

```json
{
  "schema_version": 1,
  "command": "gate check",
  "ok": false,
  "observed_revision": 18,
  "data": {
    "gate": "PROTOTYPE_DECISION",
    "result": "blocked"
  },
  "diagnostics": [
    {
      "code": "PLAYTEST_EVIDENCE_MISSING",
      "severity": "error",
      "message": "At least one external playtest report is required."
    }
  ]
}
```

Diagnostic codes are stable API values. Human messages may improve without
breaking callers.

For `--format json`:

- stdout contains exactly one JSON envelope and no progress text;
- logs and optional progress output go to stderr;
- timestamps use UTC RFC 3339 and identifiers are opaque strings;
- project-owned paths are repository-relative and use `/` separators;
- enums and field meanings remain stable within a schema version;
- diagnostics use a deterministic order: severity, code, then subject;
- every command publishes a schema for its `data` object;
- unknown fields may be added compatibly, while removing or changing existing
  fields requires a new envelope schema version.

Read-only commands return `observed_revision`. Successful mutations also return
`committed_revision`.

## 5. Exit codes

Initial convention:

| Code | Meaning |
|---:|---|
| 0 | Command succeeded |
| 1 | Operational failure |
| 2 | Invalid arguments or schema |
| 3 | Gate not satisfied |
| 4 | Required tool unavailable |
| 5 | State conflict or reconciliation required |

Exit code 3 means the project and command are valid but the requested gate is
blocked. Malformed state or evidence returns code 2 rather than code 3.

## 6. Adapter interface

An engine adapter should provide:

```text
detect(project) -> confidence + evidence
version(project) -> version
capabilities(project) -> build/test/run/capture support
build(project, profile) -> run record
test(project, suite) -> run record
launch(project, mode) -> process metadata
capture(project, request) -> artifact record
```

Adapters must not claim capabilities they cannot verify. Unsupported actions
return a structured diagnostic and a manual fallback.

Every adapter operation also obeys an execution contract:

- commands are argument arrays rather than interpolated shell strings where
  the platform permits it;
- working directory, filtered environment, executable identity, adapter
  version, timeout, and cancellation reason are recorded;
- secrets are redacted before command, environment, or logs are persisted;
- stdout and stderr are captured separately with configurable size limits;
- timeout or cancellation terminates child processes and records whether cleanup
  could be verified;
- an interrupted or ambiguous process result never registers passing evidence;
- manual fallback evidence is marked `manually_imported` and remains subject to
  the gate's trust requirements.

## 7. Configuration

Project configuration should be minimal and versioned. For MVP version 1,
machine-written state and the canonical project configuration use JSON. YAML may
be accepted later as a human-authored import format, but the CLI must normalize
it to the canonical JSON model before validation or persistence.

```json
{
  "schema_version": 1,
  "engine": "godot",
  "target_platforms": ["web"],
  "profiles": {
    "prototype": { "build": "debug" },
    "release": { "build": "release" }
  }
}
```

Secrets never belong in `.loopforge` project files. Use environment variables or
host-native secret storage for future publishing integrations.

Configuration and state migrations must be explicit, testable, and
non-destructive. Unknown newer versions block mutation. Upgrade commands create
a recoverable backup and preserve the original event history.
