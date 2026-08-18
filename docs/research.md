# Reference Research

## 1. Purpose

This document records public projects that informed Loopforge's initial design.
Repository popularity is only a discovery signal; it is not evidence that each
included skill is correct or that the generated games are good.

Star counts below were observed on 2026-08-18 and will naturally drift.

## 2. Primary references

### awesome-gamedev-agent-skills

- Repository: <https://github.com/gamedev-skills/awesome-gamedev-agent-skills>
- Observed stars: 531
- License: Apache-2.0
- Useful ideas: engine/task router, discipline and genre composition,
  progressive disclosure, prototype keep/kill criteria, asset manifests,
  in-engine asset validation.
- Limitation: broad knowledge coverage is stronger than end-to-end project
  state and human playtest management.

### GodotMaker

- Repository: <https://github.com/RandallLiuXin/GodotMaker>
- Observed stars: 508
- License: BUSL 1.1 at time of review; verify before reuse.
- Useful ideas: Socratic GDD workflow, playable release units, explicit stage
  state, worker/verifier separation, Godot E2E interaction, screenshot-based
  visual QA, rejection-to-fix loop.
- Limitation: strongly coupled to its runtime, agent conventions, and Godot 2D
  workflow. Design concepts may be studied, but code or text reuse requires
  license review.

### game-creator

- Repository: <https://github.com/PlayableIntelligence/game-creator>
- Observed stars: 317
- License: no repository license was detected during review; do not copy code or
  text without permission.
- Useful ideas: gameplan and architecture decisions across sessions, browser
  game templates, Playwright interaction, deterministic time control, visual
  regression, mobile checks, asset and audio pipelines.
- Limitation: some architectural rules are overly universal and the workflow is
  centered on browser games.

## 3. Secondary references

### GameBlocks

- Repository: <https://github.com/xt4d/GameBlocks>
- Observed stars: 414
- License: MIT
- Useful idea: reuse small, documented gameplay modules instead of repeatedly
  inventing foundational 3D systems.

### roblox-game-skill

- Repository: <https://github.com/brockmartin/roblox-game-skill>
- Observed stars: 135
- Useful ideas: capability detection, offline degradation, server authority,
  persistence safety, security and monetization checks.
- Limitation: platform-specific and not a complete art or playtest workflow.

### skills-for-antigravity

- Repository: <https://github.com/omer-metin/skills-for-antigravity>
- Observed stars: 128
- Useful ideas: discipline taxonomy covering game design, combat, level design,
  narrative, environment art, pixel art, and audio.
- Limitation: many skills rely on verbose expert-persona claims and generic
  reference patterns. Use the taxonomy, not the voice or unsupported authority.

### antigravity-skills

- Repository: <https://github.com/rmyndharis/antigravity-skills>
- Observed stars: 1,331
- Useful ideas: compact engine-specific implementation references.
- Limitation: repository-level stars reflect a broad general-purpose collection;
  its individual game skills often describe capabilities rather than enforce
  executable workflows.

## 4. Resulting design choices

Loopforge combines, without copying:

- the router and composable discipline model from dedicated skill collections;
- the persistent staged verification loop demonstrated by GodotMaker;
- the automated browser-game testing patterns demonstrated by game-creator;
- a new first-class human playtest and evidence model;
- a portable, deterministic CLI rather than a required proprietary agent.

Before reusing any implementation or substantial text, contributors must verify
the source's current license and attribution requirements.
