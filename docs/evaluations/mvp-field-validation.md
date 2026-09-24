# MVP Field Validation Handoff

The engineering checks for M0–M3 do not substitute for the external sessions
required by `docs/planning/mvp.md` §8. Record these runs against real project
state and real people before describing the MVP as generally useful.

## Run A: Representative prototype

Use the one-screen risk/reward Godot fixture as a starting game. A coding agent
must first make or adapt a normal project from an approved hypothesis; the
existing fixture alone proves the engine path, not the agent's creative work.
Build, start and capture the exact version that a participant will play. Record
the active experiment, hypothesis revision, source/build identity and evidence
IDs before recruitment.

Obtain an external participant's consent for the minimum anonymous behavioral
notes needed by the declared keep/kill signals. Give only the neutral default
prompt from `prototype-gameplay`: “Please play until you choose to stop.” Do
not teach controls, explain the hypothesis or coach a strategy. Record ordered
actions, confusion, failures, abandonment, assistance and voluntary replay.
Keep the raw observations separate from interpretation and record retention or
deletion handling. Import only a report bound to the recorded protocol and
tested build.

The human approver then reviews supporting and contradictory observations,
limitations and the original thresholds. One run should exercise a defensible
`keep` or bounded `refactor` path. Do not choose the outcome in advance of the
observations.

## Run B: Unseen prototype prompt

Choose a second small gameplay question that was not used to tune the fixture,
Skill eval set or Run A. Preserve the raw prompt and the agent's first
hypothesis before implementation. Use a separate project and participant so
the artifact and observation trail cannot be confused with Run A. Exercise an
honest `kill` path if the declared kill signals occur; if they do not, record
the outcome supported by the observations and use another run for the expected
kill-path validation.

`m2-unseen-prototype.md` records one candidate prompt before implementation;
`examples/echo-lantern` contains the resulting technical prototype. Its
mechanics and screenshot have been checked, but the hypothesis is not approved
in a project history and it has not been played by an external participant.

## Independent review

Give a reviewer who did not implement either game the approved hypotheses,
protocols, registered build and capture evidence, de-identified raw reports,
decision reviews and event histories. Ask whether each conclusion follows the
declared signals and raw behavior, whether contradictory observations or
coaching were omitted, and whether any reported claim exceeds its evidence.
Record the reviewer's findings and any corrected decision as separate artifacts.
Never add participant names or media to the repository merely for review.

Completion evidence is two project histories reaching their respective
decisions, both sets of validated protocol/report artifacts and evidence IDs,
and an independent findings record. Until these exist, the engineering
milestones can be locally verified while the MVP product hypothesis remains
untested with external players.
