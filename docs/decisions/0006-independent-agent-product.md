# ADR 0006: Make the Loopforge Agent the Product Control Plane

- Status: Accepted
- Date: 2026-08-20
- Supersedes: ADR 0001 product-shape boundary

## Context

Loopforge began as portable Agent Skills plus a deterministic Python CLI. That
shape proved the workflow and state model, but it makes the user or host agent
responsible for composing long-running game-development work. The desktop
workbench later added a direct Kura chat path and a second Kura supervisor in
Tauri. This duplicated lifecycle ownership and left no Loopforge-owned domain
agent between the product UI and the generic runtime.

## Decision

The Loopforge Agent is an independent local application service and the product
control plane. It owns project context, workflow planning, tool selection,
approval waits, session continuity and delegation to deterministic operations.

- The Workbench communicates only with the Loopforge Agent contract.
- The Agent consumes Kura through a Loopforge-owned adapter for generic model,
  session and tool-execution capabilities.
- Kura remains domain-neutral and contains no Loopforge routes, types or state.
- Deterministic state, evidence and gate logic remains reusable core code.
- The CLI is an internal/headless adapter over that core, not the product
  control plane.
- Skills are versioned internal Agent capabilities. Direct installation remains
  a compatibility and evaluation path, not the primary user experience.
- Tauri owns only the Loopforge Agent sidecar lifecycle. The Agent owns its Kura
  runtime lifecycle.

The first implementation is a loopback-only sidecar protected by a per-launch
bearer token stored in project-scoped runtime metadata. Release builds bundle a
standalone Agent executable. The wire contract is versioned independently from
Kura.

## Consequences

Positive:

- One domain control plane owns context and orchestration.
- Workbench behavior no longer depends on Kura-specific routes.
- CLI and Skills remain testable without defining the product boundary.
- Public runtime and rendering libraries stay reusable and domain-neutral.

Negative:

- Packaging includes another sidecar and lifecycle boundary.
- The current Python core remains a transitional internal dependency.
- Crash recovery, upgrades and multi-project scheduling require explicit Agent
  service design rather than being delegated to the UI.

## Revisit when

Revisit process topology only after measured startup, packaging or recovery
failures. Do not move Loopforge domain behavior into Kura to remove a process.
