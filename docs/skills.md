# Skill System Design

## 1. Design goals

Loopforge skills should be portable across Agent Skills-compatible hosts while
being tested first with Codex. Each skill should have one clear job and load
detailed references only when needed.

The skills are not a game-development encyclopedia. They encode workflows,
failure modes, decision criteria, and tool handoffs that an otherwise capable
coding agent is likely to apply inconsistently.

## 2. Initial skill map

### `loopforge-router`

Detect the project stage, engine, and requested concern. Load the smallest set
of relevant skills and explain the selection. It owns routing, not domain
implementation.

### `discover-game`

Turn a rough idea into a player-experience hypothesis, constraints, references,
and cheapest validation plan. Avoid premature feature lists.

### `prototype-gameplay`

Define one experimental question, keep/kill signals, disposable boundaries,
and the smallest playable implementation. Require a complete play loop and
restart path.

### `design-game`

Turn a kept prototype or reviewed idea into a player promise, linked moment,
session, and meta loops, system contracts, scope gates, production risks, and a
validated vertical-slice handoff. Keep assumptions and human approval explicit.

### `run-playtest`

Prepare a neutral protocol, capture observations separately from
interpretations, evaluate evidence limitations, and support a human-confirmed
`keep`, `kill`, or `refactor` decision.

For the MVP this procedure may initially live inside `prototype-gameplay` to
reduce trigger and context fragmentation. `run-playtest` remains the intended
public boundary and becomes a separate installed skill only when evaluation
shows that the split improves routing or context use.

### `direct-game-art`

Define art direction, representative targets, asset families, technical
constraints, manifests, provenance, normalization, engine import, and in-context
review. Delegate image generation to an available tool rather than embedding a
host-specific image API.

### `build-godot-game`

Provide the first engine-specific implementation path: Godot project structure,
runtime patterns, build/test/capture commands, and engine-specific pitfalls.

### `review-game-release`

Review technical, visual, playtest, provenance, and release evidence without
collapsing them into a misleading single quality score.

## 3. Progressive disclosure

Each skill follows this structure only when the contents are needed:

```text
skill-name/
├── SKILL.md
├── agents/openai.yaml
├── references/
├── scripts/
└── assets/
```

- `SKILL.md` contains the core procedure and routing to resources.
- `references/` contains detailed domain knowledge and checklists.
- `scripts/` contains deterministic helpers not already owned by the CLI.
- `assets/` contains templates copied into project outputs.
- `agents/openai.yaml` is optional host metadata and must not be required by the
  portable workflow.

## 4. Skill and CLI boundary

| Concern | Owner |
|---|---|
| Interpret player behavior | Skill + human |
| Decide what prototype to build | Skill + human |
| Validate state schema | CLI |
| Check evidence presence | CLI |
| Judge whether evidence supports hypothesis | Skill + human |
| Run build/test command | CLI adapter |
| Diagnose gameplay implementation | Engine skill + coding agent |
| Record transition and checksum | CLI |
| Generate or edit visual asset | Available media tool |
| Validate dimensions and alpha | CLI/script |

## 5. Portability rules

- Avoid host-only tool names in portable instructions.
- Detect capabilities and provide a manual or artifact-producing fallback.
- Keep shell commands portable where reasonable and declare prerequisites.
- Use repository-relative paths.
- Keep frontmatter limited to broadly supported `name` and `description`; place
  optional host metadata in host-specific files.
- Do not assume subagents exist. When independent review is unavailable, require
  a fresh review pass with write access disabled where the host supports it.
- Do not claim support for a host until trigger and task evaluations pass there.

## 6. Evaluation strategy

Every skill change must run the repository's skill evaluation gate. Evaluation
sets should cover:

- positive and negative trigger prompts;
- incomplete or contradictory user input;
- existing-project and new-project cases;
- missing tools and degraded paths;
- attempts to skip playtesting or evidence gates;
- realistic artifacts, not only hypothetical conversations;
- regression comparison against the previous skill version.

The repository installation consists of `loopforge-router`,
`prototype-gameplay` (including discovery and playtest procedures),
`build-godot-game`, `design-game`, and `direct-game-art`. Remaining entries in
the skill map are target boundaries, not required empty packages.

Outcome metrics include trigger precision, procedural compliance, artifact
quality, unsupported claims, context usage, and successful recovery from missing
inputs.

## 7. Knowledge sourcing

Engine facts should prefer official, versioned engine documentation. Creative
heuristics should identify their limits and be tested against real prototypes
and playtests. Repeated failures become concise skill rules or deterministic
checks; isolated preferences should not become universal doctrine.
