# Loopforge Operating Contract

Read this reference before executing transitions or recovering a failed
Loopforge command.

## Revision Discipline

Use JSON output for decisions. Capture `observed_revision` or
`committed_revision` from every command and pass it to the next mutation. A
revision conflict means another writer changed the project; reread state and
re-evaluate every precondition.

Do not edit `events.jsonl`, `state.json`, or stored artifact checksums. Event
history is canonical and state is derived.

## Transition Commands

### Discovery to prototyping

```bash
loopforge hypothesis create --file <hypothesis.md> \
  --approver-id <id> --approver-name <name> --rationale <reason> \
  --expected-revision <revision> --format json
loopforge gate check PROTOTYPING --format json
loopforge advance PROTOTYPING --expected-revision <revision> --format json
```

### Prototype to playtest

```bash
loopforge run build --expected-revision <revision> --format json
loopforge run test --expected-revision <revision> --format json
loopforge capture screenshot --file <capture> \
  --expected-revision <revision> --format json
loopforge gate check PLAYTEST_REQUIRED --format json
loopforge advance PLAYTEST_REQUIRED \
  --expected-revision <revision> --format json
```

`run build` is an import/load check and `run test` is a startup smoke check for
the current Godot adapter. Neither proves gameplay, performance, visual quality,
or fun.

### Playtest to decision

```bash
loopforge playtest create --protocol <protocol.md> \
  --expected-revision <revision> --format json
loopforge playtest import --file <report.json> \
  --expected-revision <revision> --format json
loopforge gate check PROTOTYPE_DECISION --format json
loopforge advance PROTOTYPE_DECISION \
  --expected-revision <revision> --format json
```

### Early decision

```bash
loopforge advance PROTOTYPE_DECISION --reason <technical|scope|abandon> \
  --approver-id <id> --approver-name <name> --rationale <reason> \
  --expected-revision <revision> --format json
```

The early path requires applicable evidence and cannot produce `keep`.

### Record decision

```bash
loopforge decide <keep|kill> --evidence <id> [--evidence <id> ...] \
  --approver-id <id> --approver-name <name> --rationale <reason> \
  --expected-revision <revision> --format json

loopforge decide refactor --file <revised-hypothesis.md> \
  --evidence <id> [--evidence <id> ...] \
  --approver-id <id> --approver-name <name> --rationale <reason> \
  --expected-revision <revision> --format json
```

## Failure Recovery

| Condition | Required response |
|---|---|
| CLI unavailable | Report the missing prerequisite; do not simulate persistent state |
| Project uninitialized | Run `init`, then reread status |
| Snapshot missing/stale | Run `validate` and `reconcile --dry-run`; apply only an exact derived-state rebuild |
| Event/hash/artifact invalid | Stop mutation and report the diagnostic; do not repair history or update checksums |
| Exit code 3 | Gate is blocked; satisfy the named requirements instead of bypassing it |
| Exit code 4 | Required tool is unavailable; use a documented manual-evidence fallback only when the gate permits it |
| Exit code 5 | Reread status and recompute the operation against the new revision |
| Interrupted engine run | Run `doctor`; preserve orphan diagnostics and rerun as a new run ID |
| Source changed | Treat affected evidence as stale and regenerate it |
| No external participant | Remain at `PLAYTEST_REQUIRED` |
| Consent declined/withdrawn | Stop collection; do not import or cite the affected report |
| Early path selected | Permit only `kill` or `refactor` |

Never use direct file edits, stale evidence, fabricated approvals, or a relabeled
manual artifact to force a gate.
