# Stage and Gate Contracts

## 1. Purpose

This document is the deterministic contract for Loopforge stage transitions.
The workflow document explains why stages exist; this document defines what the
CLI can verify before committing a transition.

The lifecycle applies to one active experiment. A project may retain completed
or killed experiments and start a new experiment without rewriting their
history.

## 2. Lifecycle

```text
UNINITIALIZED
  -> DISCOVERY
  -> PROTOTYPING
       |-> PLAYTEST_REQUIRED
       |     `-> PROTOTYPE_DECISION
       `-> PROTOTYPE_DECISION  (early technical or scope decision)
             |-> KILLED
             |-> PROTOTYPING   (refactor with a new hypothesis revision)
             `-> VERTICAL_SLICE (keep after external playtest only)
  -> PRODUCTION_CANDIDATE
  -> RELEASE_REVIEW
  -> RELEASE_APPROVED

KILLED
  -> DISCOVERY                 (start a new experiment)
```

`KILLED` terminates the active experiment, not the repository. Starting another
experiment creates a new experiment ID and preserves all prior events and
evidence.

## 3. Gate result model

`loopforge gate check <stage>` evaluates every requirement and returns:

- overall `pass` when all required items are satisfied;
- overall `blocked` when an item is missing, stale, invalid, or failed;
- exit code 3 for a structurally valid but blocked gate;
- exit code 2 when project state or evidence is malformed;
- exit code 4 when evaluation requires an unavailable tool;
- exit code 5 when state conflicts or requires reconciliation.

Each requirement includes a stable code, evidence IDs considered, status,
expected subject revision, and a remediation message. Gate evaluation is
read-only.

When several applicable result records exist for the same requirement, source
identity, subject, platform, and profile, the record committed at the greatest
project revision is authoritative. A latest `failed` result blocks the gate;
an older `passed` result cannot mask it. Observation records accumulate rather
than replacing one another, and revocation always takes precedence. If records
cannot be ordered or have conflicting identities, the requirement is `invalid`
and requires reconciliation.

## 4. MVP transition matrix

| From | To | Deterministic requirements | Human requirement |
|---|---|---|---|
| `UNINITIALIZED` | `DISCOVERY` | Valid project initialization and schema-versioned state | None |
| `DISCOVERY` | `PROTOTYPING` | Active experiment; hypothesis schema complete; prototype question, constraints, cheapest validation, and observable keep/kill signals present | Approval of the hypothesis revision |
| `PROTOTYPING` | `PLAYTEST_REQUIRED` | Fresh passing build and smoke-test evidence; reachable tested behavior; restart flow; current runtime capture; known shortcuts recorded | Confirmation that the build is ready for external observation |
| `PROTOTYPING` | `PROTOTYPE_DECISION` | Evidence of technical infeasibility, cost/scope limit, or explicit user abandonment; transition reason is `technical`, `scope`, or `abandon` | Approval to make an early decision |
| `PLAYTEST_REQUIRED` | `PROTOTYPE_DECISION` | Structurally valid external playtest report scoped to the active hypothesis; consent status; raw observations separated from interpretation | Confirmation that the imported evidence is sufficient to consider a decision |
| `PROTOTYPE_DECISION` | `PROTOTYPING` | Decision is `refactor`; cited evidence; revised falsifiable hypothesis with a new revision; prior hypothesis preserved | Identified approver and rationale |
| `PROTOTYPE_DECISION` | `KILLED` | Decision is `kill`; cited supporting and contradicting evidence; limitations and next action recorded | Identified approver and rationale |
| `PROTOTYPE_DECISION` | `VERTICAL_SLICE` | Decision is `keep`; fresh external playtest evidence; technically validated prototype; supporting and contradicting observations; limitations recorded | Identified approver and rationale |
| `KILLED` | `DISCOVERY` | New experiment ID; prior experiment remains immutable | Approval of the new experiment intent |

Transitions after `VERTICAL_SLICE` are outside the MVP. Before implementing
them, extend this table with art-target, integrated playtest, performance,
provenance, legal, and release requirements.

## 5. Early decision restrictions

An early transition from `PROTOTYPING` to `PROTOTYPE_DECISION` exists so that a
prototype that cannot be built, is prohibitively expensive, or is deliberately
abandoned can end honestly.

- An early decision may be `kill` or `refactor`.
- It may not be `keep`.
- It does not satisfy `HUMAN_PLAYTESTED` or `FUN_HYPOTHESIS_SUPPORTED`.
- Failed builds and technical spike reports are evidence, but they do not become
  passing technical validation.

## 6. Evidence authority

Gate requirements declare accepted evidence types and trust levels. MVP
defaults are:

| Requirement | Accepted authority |
|---|---|
| Build and smoke test passed | `tool_generated`; `manually_imported` only when the adapter is unavailable and the gate explicitly permits it |
| Runtime capture exists | `tool_generated` or provenance-complete `manually_imported` |
| External playtest observations | `human_attested` or provenance-complete `manually_imported` |
| Human approval | `human_attested` |
| Technical infeasibility or scope limit | Tool-generated failure records plus human-attested interpretation |

Manual evidence never bypasses schema, checksum, subject, freshness, consent,
or approval requirements.

The `keep`, `kill`, and `refactor` commands are the only supported way to leave
`PROTOTYPE_DECISION`. They record the decision and resulting transition as one
event so a crash cannot leave an approved decision without its corresponding
stage change.

## 7. Approval record

Every human approval contains:

```json
{
  "schema_version": 1,
  "approver_id": "local:user@example",
  "approver_display_name": "Example User",
  "identity_source": "local-declaration",
  "approved_subject": {
    "experiment_id": "exp_example",
    "hypothesis_revision": 2,
    "project_revision": 18
  },
  "decision": "refactor",
  "rationale": "The charge window was understood, but the reward was unclear.",
  "rationale_checksum": "sha256:...",
  "approved_at": "2026-08-18T10:00:00Z"
}
```

The MVP records attribution and intent. It must not describe a local declaration
as authenticated identity.

## 8. Invalidation examples

- Changing gameplay source after a passing smoke test makes that test `stale`.
- Changing only a playtest report interpretation does not invalidate its raw
  recording checksum, but creates a new interpretation record.
- A `refactor` creates a new hypothesis revision; evidence from the previous
  revision remains visible but cannot satisfy the new prototype gate unless the
  requirement explicitly permits cross-revision evidence.
- Changing target platform invalidates platform-specific build, capture, and
  performance evidence.
- Revoking playtest consent invalidates use of the affected sensitive artifact
  and any claim that depends exclusively on it.
