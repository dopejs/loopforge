# Loopforge cross-repository contracts

These JSON Schemas are Loopforge-owned application contracts. They are
versioned by name rather than by an unbounded compatibility promise: a
Loopforge adapter must reject an unknown contract version and report the
migration path.

The Loopforge Agent is the product control plane. Kura is the generic runtime
source of truth, while Loopforge remains the authority for game-project state,
deterministic tool execution and evidence identity. Deckle
owns visual artifact revisions and geometry; Doper owns native rendering and
editing. Kura, Deckle, and Doper expose domain-neutral public contracts;
Loopforge-owned adapters translate these schemas at each boundary. Public
libraries must not add Loopforge files, routes, types, or state fields.

Initial contracts:

- `loopforge-agent-status-v1`: Workbench-visible Agent readiness, project
  context and nested generic runtime status.
- `game-project-context-v1`: a redacted, read-mostly project snapshot exchanged
  between the Loopforge Core, Agent and desktop client.
- `tool-invocation-v1`: an idempotent request/result envelope for deterministic
  Loopforge tools.
- `visual-artifact-v1`: a Loopforge reference mapped by an application adapter
  to Deckle's public artifact descriptor.
- `event-envelope-v1`: a cross-process event envelope with revision and scope.

The schemas intentionally describe references and diagnostics, not engine
implementation details. Breaking changes require a new `-vN` schema.
The Workbench calls these Agent contracts rather than Kura directly.
