# Prototype Evidence Review

Read this reference when preparing a playtest, interpreting observations, or
recommending a prototype decision.

## Observation Standard

Record what happened before explaining why:

- Good raw observation: "Participant paused for 11 seconds, tried movement keys,
  then used charge after the hazard crossed twice."
- Bad raw observation: "The controls were confusing."

Keep timestamps or stable ordering when possible. Record coaching, technical
interruptions, and observer intervention because they limit interpretation.
Do not omit negative or null results.

## Consent and Privacy

Collect the minimum data needed for the hypothesis. Prefer anonymous behavioral
notes over audio, video, names, or contact details. Bind the report to a consent
status before import.

- `obtained`: the participant agreed to the recorded data.
- `not_required`: use only when a written local policy established before
  recruitment says no consent is required and no participant-linked data is
  collected. Do not select it merely for convenience.
- declined or withdrawn: stop collection and do not import or cite the report.

Never upload or retain sensitive artifacts merely because the workflow can
reference them. State retention and deletion constraints in the interpretation.

## Evidence Review Structure

Review each declared signal against cited observations:

1. Supporting evidence: behavior that matches a keep signal.
2. Contradicting evidence: behavior that matches a kill signal or weakens the
   causal interpretation.
3. Confounds: coaching, prior familiarity, defects, frame-rate problems,
   observer effects, or a build mismatch.
4. Sampling limits: one participant, relationship to the team, experience bias,
   accessibility mismatch, or session length.
5. Confidence: `low`, `medium`, or `high`, justified by evidence quality rather
   than enthusiasm.

A single session can support a prototype workflow decision. It cannot establish
general market preference or universal fun.

## Decision Rules

- Recommend `keep` only with a fresh external report tied to the tested build,
  voluntary behavior matching keep signals, and no invalidating confound.
- Recommend `kill` when kill signals recur, comprehension fails within the
  declared window, voluntary replay is absent where it was required, or the
  technical/scope cost invalidates the approach.
- Recommend `refactor` only when the evidence identifies one changed,
  falsifiable hypothesis. Do not use it as a vague request for more polish.
- Report mixed evidence as mixed. Do not average contradictions into a single
  score or upgrade uncertainty to success.
