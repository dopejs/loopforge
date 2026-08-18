# Product Design

## 1. Problem

Coding agents can generate game code quickly, but speed alone creates several
failure modes:

- The project advances before the core loop has been validated.
- A design document is mistaken for evidence that a mechanic is fun.
- Art and content are produced before expensive assumptions are tested.
- Build state, decisions, and failures remain trapped in conversation history.
- Automated tests prove that the game works, then overstate that it is good.
- A long workflow cannot be resumed reliably after interruption.

Game-development knowledge alone does not solve these problems. The product
must join creative workflows with deterministic state and evidence management.

## 2. Product thesis

Loopforge is not an autonomous game studio and does not promise to manufacture
a good game. It gives an existing coding agent a disciplined way to:

1. frame a player-experience hypothesis;
2. create the cheapest playable experiment that can test it;
3. collect technical, visual, and human evidence;
4. make an explicit `keep`, `kill`, or `refactor` decision;
5. advance only when the next investment is justified.

The product consists of two primary parts:

- **Skills** provide game-design heuristics, production workflows, review
  methods, and tool-selection guidance.
- **CLI** provides persistent state, schemas, gates, evidence capture, command
  execution, and recovery.

Codex, Claude Code, or another compatible coding agent is the executor. The
first supported and tested host will be Codex.

## 3. Target users

### Primary

- Solo developers who can describe a game but need a reliable development
  process.
- Software engineers entering game development without production experience.
- Small teams using coding agents to accelerate prototypes and vertical slices.
- Skill authors who need reusable, testable game-development workflows.

### Not initially targeted

- AAA production pipelines requiring proprietary editor integrations.
- Live-service operations, matchmaking, anti-cheat, or economy management.
- Console certification.
- Fully unattended production of commercial games.

## 4. Jobs to be done

### From idea to experiment

> Help me turn an imprecise idea into one falsifiable gameplay hypothesis and a
> small playable prototype.

### From prototype to decision

> Help me run the prototype, observe what happens, collect playtest evidence,
> and decide whether to keep, kill, or refactor it.

### From validated loop to vertical slice

> Help me add coherent art, audio, UI, level structure, and engineering quality
> without losing the validated experience.

### Across sessions

> Show exactly where the project stands, what evidence is missing, why a
> decision was made, and what can be resumed safely.

## 5. Product boundaries

Loopforge should:

- manage game-development stages and their evidence;
- expose small, composable game-development skills;
- support deterministic tools through a portable CLI;
- preserve normal engine projects rather than inventing a closed format;
- allow human approval at creative and release-sensitive gates;
- degrade cleanly when image, audio, browser, or engine tools are unavailable.
- report evidence as missing, stale, failed, invalid, or satisfied rather than
  treating artifact presence as proof.

Loopforge should not:

- declare a game fun from automated checks alone;
- hard-code subjective design judgments in CLI rules;
- require a proprietary model or agent runtime;
- silently advance past missing human evidence;
- generate large content sets before a representative target is accepted;
- replace the game engine, source control, or build system.

## 6. Success measures

The first product experiments should measure:

- Time from idea intake to first playable prototype.
- Percentage of sessions resumable without reconstructing chat history.
- Percentage of stage transitions backed by complete evidence.
- Number of invalid or premature transitions prevented by the CLI.
- Rate at which prototype decisions cite observed behavior rather than opinion.
- Skill trigger accuracy and completion rate on representative tasks.
- Frequency with which users can understand `loopforge status` without reading
  internal files.

The product must not use repository stars, generated file count, or lines of
code as measures of game quality.

## 7. Non-goals for the MVP

- A graphical project dashboard.
- A hosted service or multi-tenant backend.
- A custom conversational agent.
- Multi-model scheduling or autonomous background queues.
- Complete support for Godot, Unity, Unreal, Roblox, and web engines at once.
- Production-quality generation of every art and audio category.
- Automated interpretation of biometric or large-scale telemetry.
