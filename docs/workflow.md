# Development Workflow

## 1. Guiding loop

Loopforge organizes development around evidence-producing iterations:

```text
hypothesis
  -> cheapest playable experiment
  -> technical and visual verification
  -> human observation
  -> keep / kill / refactor
  -> next justified investment
```

The workflow is deliberately not a linear checklist from GDD to release. Early
stages may loop many times, and killing a prototype is a successful outcome when
it prevents larger waste.

## 2. Stage contracts

### Discovery

**Purpose:** Convert an idea into a bounded player-experience hypothesis.

Required outputs:

- intended player and platform;
- player fantasy and core verb;
- moment-to-moment loop;
- one falsifiable hypothesis;
- constraints and explicit non-goals;
- comparable games and the specific qualities being referenced;
- cheapest proposed validation.

Exit condition: the hypothesis can be tested without building the intended full
game.

### Prototyping

**Purpose:** Build the smallest playable experiment that answers one question.

Required outputs:

- prototype brief;
- observable keep and kill signals;
- playable build;
- basic controls and restart flow;
- build and smoke-test evidence;
- list of shortcuts and disposable assumptions.

Prototypes should remain isolated from production code unless explicitly
promoted. Visuals may be greybox assets, but feedback necessary to understand
the mechanic must be present.

Exit condition: a fresh player can reach the behavior being tested.

If the prototype cannot be built, exceeds an explicit cost or scope limit, or
is deliberately abandoned, it may move directly to `PROTOTYPE_DECISION` with
technical and human-attested evidence. This early path can result in `kill` or
`refactor`, never `keep`.

### Playtest required

**Purpose:** Observe player behavior rather than asking for design approval.

Minimum evidence:

- playtest protocol and consent status;
- participant context;
- session notes or recording reference;
- comprehension time;
- confusion, failure, and abandonment points;
- spontaneous strategies or experimentation;
- replay behavior;
- observer interpretation separated from raw observations.

Automated agents may inspect controls, state transitions, and visible behavior.
They cannot satisfy the external human playtest requirement.

Exit condition: evidence has been registered, passes structural gate checks,
and a human confirms that it is sufficient to consider a decision. The CLI does
not decide whether the observations support the hypothesis.

### Prototype decision

Allowed decisions:

- `keep`: evidence justifies investing in a vertical slice;
- `kill`: the tested hypothesis is unsupported or too expensive;
- `refactor`: a specific changed hypothesis will be tested next.

`keep` requires external human playtest evidence. A decision reached through
the early technical or scope path may only be `kill` or `refactor`.

Every decision records:

- evidence considered;
- strongest supporting and contradicting observations;
- confidence and known limitations;
- responsible human approver;
- next action.

### Vertical slice

**Purpose:** Demonstrate the intended final experience at narrow content scope.

Required concerns:

- validated core loop;
- representative art target and asset manifest;
- coherent audio and feedback;
- one representative level or session;
- production architecture for the slice;
- automated tests, performance budget, and runtime captures;
- external playtest of the integrated experience.

Exit condition: the slice is technically stable and players can experience its
intended quality without developer explanation.

### Production candidate

**Purpose:** Prove that content can be produced repeatedly without losing
quality or breaking budgets.

Required outputs include content pipeline evidence, regression coverage,
platform-specific budgets, provenance records, and scope/release projections.

### Release review

**Purpose:** Verify the candidate against technical, product, legal, and human
acceptance criteria.

Release approval remains a human gate.

## 3. Evidence model

Every claim should point to an artifact:

| Claim | Minimum useful evidence |
|---|---|
| Builds successfully | command, exit code, log, artifact checksum |
| Core loop works | automated interaction or recorded manual reproduction |
| Layout is coherent | native-resolution screenshots or frame sequence |
| Performance is acceptable | target hardware/profile and measured budget |
| Art is consistent | approved target, contact sheet, in-engine capture |
| Players understand it | observed external playtest behavior |
| Players want to continue | replay or continuation behavior plus limitations |
| Ready to release | all applicable gates plus human approval |

Absence of evidence must be reported as `unknown`, not inferred as success.
Related evidence that no longer matches the active source or hypothesis is
reported as `stale`. Failed evidence remains part of the record but cannot
satisfy a passing requirement. Detailed statuses and transition requirements
are defined in [gates.md](gates.md).

## 4. Rollback and recovery

- Every committed mutation records a revisioned, hash-linked event. Current
  state is a reconstructable projection of that event history.
- A failed command leaves the current stage unchanged.
- A `refactor` decision creates a new hypothesis revision; it does not rewrite
  the history of the prior test.
- A prototype decision and its resulting stage transition are committed as one
  event; a `refactor` event also carries the new hypothesis revision.
- Generated assets retain their source and transformation history.
- Release and publishing commands require a preflight and a post-action readback.
- Revision conflicts leave state unchanged and require the caller to reread
  status before retrying.
- Read-only validation never repairs state. Explicit reconciliation reports a
  dry-run plan before modifying derived files or quarantining incomplete data.
