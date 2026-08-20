# ADR 0001: Use Skills and a Deterministic CLI

- Status: Superseded by ADR 0006
- Date: 2026-08-18

## Context

Loopforge needs reusable game-development expertise, persistent state,
repeatable tool execution, evidence gates, and cross-session recovery. A custom
agent runtime could provide these capabilities, but existing coding agents
already supply planning, repository access, tool use, and code modification.

## Decision

Build Loopforge as:

1. portable Agent Skills for judgment-heavy game-development workflows; and
2. a deterministic local CLI for state, evidence, adapters, gates, and recovery.

Use Codex as the first tested executor. Do not build a separate agent runtime in
the initial product.

## Consequences

Positive:

- Smaller implementation and operational surface.
- Clear separation between probabilistic judgment and deterministic checks.
- Better portability across compatible coding agents.
- Local-first state and straightforward debugging.
- The product can validate its method before building hosted infrastructure.

Negative:

- Long workflows require an interactive coding-agent session or manual resume.
- Host capabilities differ and require graceful degradation.
- Unattended scheduling and remote wake-up are deferred.

## Revisit when

At least one validated use case requires background queues, remote wake-up,
multi-project scheduling, multi-tenant access, or independent model routing.
