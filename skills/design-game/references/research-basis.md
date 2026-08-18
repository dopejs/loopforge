# GitHub Research Basis

Snapshot date: 2026-08-18. Stars are discovery signals, not quality guarantees.
Repositories were inspected at the pinned commits below. No upstream prose,
templates, or code is copied into this Skill.

| Repository | Stars | License | Pinned commit | Relevant pattern |
|---|---:|---|---|---|
| [Roobyx/awesome-game-design](https://github.com/Roobyx/awesome-game-design) | 620 | CC0-1.0 | `f801ec04347163123be112a4c5875b5f934ed0b2` | Broad game-design literature and method discovery; separate creative heuristics from validated practice |
| [2DGD-F0TH/2DGD_F0TH](https://github.com/2DGD-F0TH/2DGD_F0TH) | 455 | CC BY-NC-SA | `b88cdf5d44f5fde5f1bc5b0f439c1eb366580f87` | GDD lifecycle, mechanics consolidation, flow, fairness, difficulty, economy, accessibility, testing, and production topics |
| [DY-2026/GameDesignOS](https://github.com/DY-2026/GameDesignOS) | 344 | MIT | `ada4bf9e60c2c90a4c84866e4bfd191e3767d164` | Player promise, design-nucleus alternatives, assumption/evidence boundaries, scope gates, human decisions, and validation plans |
| [gheja/game-design-documents](https://github.com/gheja/game-design-documents) | 66 | Unspecified | `e381c9a0ab38b8d0fe89b4eb05cc457b8ce13891` | Historical GDD examples as evidence that document form varies with team and project |
| [LazyHatGuy/GDDMarkdownTemplate](https://github.com/LazyHatGuy/GDDMarkdownTemplate) | 58 | Unspecified | `c06d8bd1fc951e6b82132b7147964f3bdf5f07e0` | Modular Markdown coverage for overview, mechanics, levels, interface, AI, art, technology, and management |
| [SCKOROT/game-design-document-creater](https://github.com/SCKOROT/game-design-document-creater) | 19 | MIT | `39e9e99dc2db50dded11fb34fd0c76a11d677e84` | Agent Skill routing, team-size-aware scope, GDD review, MVP/vertical-slice separation, and deterministic checks |

## Adopted

- Compare design nuclei before expanding a feature list.
- Define player promise before systems and connect moment, session, and meta
  loops.
- Keep evidence, derived reasoning, assumptions, unknowns, and contradictions
  separate.
- Make every system state its behavior change, feedback, validation, and
  deletion condition.
- Gate scope into MVP, representative vertical slice, later, and cut.
- Treat production feasibility, content throughput, accessibility, economy,
  failure, and restart as design concerns.
- Require explicit human approval and testable Go/No-Go conditions before
  downstream production expansion.

## Deliberately Not Adopted

- A universal GDD table of contents; document depth depends on decision and
  production risk.
- Automatic certainty from an attractive pitch, popular reference game, or
  repository Star count.
- Large multi-agent studio hierarchies and provider-specific integrations.
- Mandatory market research when it cannot change a current design decision.
- Copying reference-game IP, content, terminology, or unverified balance values.
- Treating a 100-point document score as a substitute for evidence and review.
