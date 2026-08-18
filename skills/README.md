# Loopforge Repository Skills

These portable Agent Skills implement the first prototype workflow described
in [the skill system design](../docs/skills.md):

- `loopforge-router` inspects durable state and routes one next action;
- `prototype-gameplay` turns one idea into a hypothesis, playable experiment,
  external playtest, and human-confirmed decision;
- `build-godot-game` implements and verifies the smallest Godot 4 loop;
- `design-game` turns validated gameplay learning into a complete user-facing
  GDD plus a human-approved player promise, loop/system contract, bounded
  scope, risks, and validation plan;
- `direct-game-art` turns an approved gameplay direction into a human-approved
  representative target, traceable asset manifest, validated runtime assets,
  and in-engine visual evidence.

The skills call the standalone `loopforge` CLI for state, evidence, gates, and
decisions. They do not replace human creative judgment or claim that automated
checks prove fun.
