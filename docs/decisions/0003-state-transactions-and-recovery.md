# ADR 0003: Use an Event Log and Derived State Snapshot

- Status: Accepted
- Date: 2026-08-18

## Context

Loopforge commands may update the current stage, hypothesis revision, evidence
index, and run history. A process can be interrupted between filesystem writes,
and two coding-agent sessions may invoke the CLI at the same time. Atomic file
replacement prevents partial files, but it does not make a multi-file update
atomic or prevent a later writer from overwriting an earlier update.

The project state must remain inspectable, recoverable, and auditable without a
hosted database.

## Decision

Use an append-only project event log as the canonical record of committed
Loopforge mutations. Treat `state.json` as a derived snapshot that can be
reconstructed by replaying the event log.

Each committed event contains at least:

- `schema_version` and an opaque event ID;
- a strictly increasing project revision;
- event type and timestamp;
- previous-event hash and event hash;
- command/run ID and producer metadata;
- the subject IDs affected by the event;
- the event payload required to rebuild state.

Mutating commands follow this protocol:

1. acquire an exclusive project lock;
2. read and validate the event log and current derived state;
3. compare the caller's optional `expected_revision` with the current revision;
4. validate every precondition without writing;
5. stage artifacts and immutable run records;
6. append and durably flush one complete event as the commit point;
7. atomically replace the derived `state.json` snapshot;
8. release the lock.

If the process stops after step 6, the event is committed and the snapshot is
stale. Read-only commands replay events in memory and report the stale snapshot;
they do not repair it. A later mutation may rebuild the snapshot while holding
the lock. `loopforge reconcile` provides an explicit repair path.

If the process stops before step 6, the mutation is not committed. Staged files
remain unreferenced and may be reported by `doctor` or removed by an explicit
cleanup operation.

The event log is stored as `events.jsonl`. The CLI must detect a malformed or
partially written final record. It must not silently discard committed-looking
data; reconciliation reports the proposed action before changing any file.

Runs use immutable or atomically replaced per-run records with a lifecycle of
`started`, `completed`, `failed`, or `interrupted`. A successful external
process does not change project stage until its evidence-registration event is
committed.

## Concurrency rules

- Every mutation requires the exclusive project lock.
- Read-only commands may run without the lock but must report the revision they
  observed.
- Agent-driven mutations should pass `--expected-revision`.
- A revision mismatch or live lock conflict returns exit code 5.
- Stale locks are never removed from age alone. The CLI verifies owner process
  metadata where the platform permits it and otherwise requires reconciliation.
- Filesystem locking must have tested behavior on every supported platform.

## Recovery rules

- `validate` is read-only and reports log, snapshot, schema, hash-chain, and
  reference inconsistencies.
- `reconcile --dry-run` reports the repair plan without writing.
- `reconcile` may rebuild derived state, mark orphan runs interrupted, or
  quarantine an incomplete final event after explicit confirmation.
- Reconciliation creates a byte-for-byte recoverable backup before truncating,
  quarantining, or replacing any existing state record.
- Unknown schema versions block mutation and are never guessed.
- Schema upgrades create a backup, write new-version events or snapshots
  atomically, and preserve the original event history.
- Downgrades are unsupported unless a version-specific migration explicitly
  provides them.

## Consequences

Positive:

- Cross-session state can be reconstructed and audited.
- An interrupted snapshot write does not lose a committed decision.
- Revision checks prevent silent lost updates between agent sessions.
- Recovery behavior can be tested independently from engine adapters.

Negative:

- Event replay, locking, hash validation, and reconciliation add MVP work.
- JSON Lines requires careful handling of a torn final append.
- Derived state may be temporarily stale after a crash and must be reported
  clearly.
