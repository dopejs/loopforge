# ADR 0004: Scope Evidence and Derive Quality Claims

- Status: Accepted
- Date: 2026-08-18

## Context

A checksum proves that an artifact has not changed. It does not prove that the
artifact was produced from the current code, tests the active hypothesis, uses
the intended platform, or remains applicable after a refactor. Without explicit
scope and freshness rules, an old passing build or screenshot could satisfy a
gate after the project has materially changed.

Loopforge also distinguishes technical, visual, playtest, and release claims.
Persisting these claims as permanent Boolean flags would make them stale when
their supporting evidence becomes inapplicable.

## Decision

Every evidence record is immutable and identifies both its provenance and the
subject to which it applies. Quality claims are derived from currently
applicable evidence; they are not stored as permanent truth values.

An evidence record contains at least:

- evidence ID, schema version, type, and creation time;
- registration project revision;
- result classification such as `passed`, `failed`, or `observation`;
- producer and trust level;
- active experiment ID and hypothesis revision where applicable;
- source revision or project fingerprint;
- engine, adapter, target platform, and profile where applicable;
- artifact path, content checksum, media type, and size;
- originating command/run ID;
- provenance, license, consent, and privacy metadata when applicable;
- explicit supersession or revocation references.

Supported trust levels for the MVP are:

- `tool_generated`: produced and registered by a Loopforge-controlled command;
- `manually_imported`: supplied by a user with recorded provenance;
- `human_attested`: an observation or approval explicitly attributed to a
  person.

Manual registration preserves evidence but does not automatically grant it the
same gate authority as tool-generated evidence. Each gate states which trust
levels it accepts.

## Source identity

For Git repositories, the source identity includes the commit ID and whether
the worktree was dirty. A dirty worktree additionally records a digest of the
relevant modified and untracked project files, excluding `.loopforge` state and
declared generated outputs.

For repositories without Git, the engine adapter produces a deterministic
project fingerprint over its declared relevant inputs. If a reliable source
identity cannot be produced, the evidence is marked `unscoped` and may only
satisfy gates that explicitly allow unscoped manual evidence.

## Applicability and freshness

Evidence is applicable only when its subject, source identity, engine context,
platform, and profile match the requirement being evaluated. A gate requirement
has one of these statuses:

- `satisfied`: applicable evidence meets the structural requirement;
- `failed`: applicable evidence records a failing result;
- `missing`: no acceptable evidence exists;
- `stale`: related evidence exists but no longer matches the current subject;
- `invalid`: the evidence or referenced artifact fails schema or integrity
  validation;
- `not_applicable`: the requirement does not apply to this transition.

Absence, staleness, or invalidity never becomes success. A failed result remains
valuable evidence but does not satisfy a passing requirement.

For replaceable result evidence, such as builds and smoke tests, the applicable
record with the greatest registration project revision is authoritative within
the same subject, source identity, platform, and profile. A newer failure cannot
be hidden by citing an older pass. Human observations are cumulative unless
explicitly superseded or revoked. Revocation takes precedence over registration
order.

Freshness is event-based rather than time-based unless a gate explicitly sets a
time limit. Changes to relevant source inputs, hypothesis revision, adapter
version, build profile, or target platform invalidate affected evidence. Pure
documentation changes do not invalidate engine evidence unless the adapter's
fingerprint includes them.

## Derived claims

The CLI derives quality claims from the active project revision and evidence:

- `TECHNICALLY_VALIDATED`
- `VISUALLY_REVIEWED`
- `HUMAN_PLAYTESTED`
- `FUN_HYPOTHESIS_SUPPORTED`
- `RELEASE_APPROVED`

Each claim reports `satisfied`, `failed`, `unknown`, or `stale`, plus applicable
evidence IDs and decision event IDs. The CLI checks structural requirements and
applicability. Skills and humans interpret whether subjective evidence supports
or contradicts a creative conclusion; the CLI does not infer that judgment from
an artifact alone.

`FUN_HYPOTHESIS_SUPPORTED` requires a human-approved decision citing external
playtest evidence. Automated tests or visual inspection cannot produce it.

## Human identity and privacy

A human approval records an approver identifier, display name, identity source,
timestamp, approved subject and revision, rationale, and rationale checksum.
For the local MVP this is an attribution record, not cryptographic proof of
identity. Output must describe it honestly.

Playtest evidence records consent status and whether it contains personal data,
audio, or video. Raw sensitive artifacts should remain outside version control
by default. Records may point to them, but must include retention and deletion
metadata and must not upload them without explicit configuration.

## Consequences

Positive:

- Old evidence cannot silently validate changed code or a revised hypothesis.
- Manual fallbacks remain useful without being overstated.
- Quality claims show uncertainty and staleness instead of permanent success.
- Gate failures can explain exactly which evidence must be regenerated.

Negative:

- Adapters must define relevant inputs and source fingerprint behavior.
- Dirty-worktree hashing adds cost and requires exclusions.
- Evidence schemas and status output become more detailed.
