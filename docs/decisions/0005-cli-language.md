# ADR 0005: Implement the CLI in Python

- Status: Accepted
- Date: 2026-08-18

## Context

The MVP needs a cross-platform local CLI with atomic filesystem operations,
process control, JSON Schema-compatible data handling, engine adapters, and a
low-friction installation path in coding-agent environments. The design called
for a small Python and TypeScript `init/status` spike before choosing a language.

## Spike result

The local environment provided Python 3.14, `uv`, and a complete standard
library path for `argparse`, JSON, filesystem, locking, hashing, and subprocess
control. Python can implement the runtime without third-party dependencies;
`uv` can provide isolated development and build environments.

Node 22 and npm were available, and a JavaScript `init/status` proof of concept
ran successfully. TypeScript was not installed, so the TypeScript path required
adding a compiler, package metadata, and a dependency installation step before
the equivalent typed CLI could be tested. That packaging path is viable, but it
adds setup work before the first state and recovery milestone.

## Decision

Implement the MVP CLI in Python 3.11 or newer. Keep the runtime dependency-free
where practical and use `uv` for development, tests, and packaging. The CLI
package lives under `cli/loopforge`, with a console entry point named
`loopforge`.

Use explicit subprocess argument arrays, platform-specific locking adapters,
JSON as the canonical persisted format, and standard-library tests for the core
state and recovery logic.

## Consequences

Positive:

- The first milestone has no runtime dependency installation beyond Python.
- Filesystem and subprocess behavior can be tested immediately on the target
  development environment.
- Python's packaging ecosystem leaves room for a future PyPI distribution.

Negative:

- Users need a supported Python runtime unless a standalone binary is added.
- A later browser-heavy adapter may find TypeScript more convenient.
- Python version and platform support must be documented and tested.

## Revisit when

Reconsider the implementation language only if installation friction becomes a
measured MVP failure, a required adapter cannot be maintained in Python, or a
standalone distribution is required and cannot be delivered acceptably through
the existing packaging path.
