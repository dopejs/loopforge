# GitHub Research Basis

Snapshot date: 2026-08-18. Star counts are discovery signals, not quality
guarantees. Repositories were read at the pinned commits below; no upstream code
or prose is copied into this Skill.

| Repository | Stars | License | Pinned commit | Relevant pattern |
|---|---:|---|---|---|
| [Donchitos/Claude-Code-Game-Studios](https://github.com/Donchitos/Claude-Code-Game-Studios) | 24,068 | MIT | `984023ddac0d5e27624f2baacde6105e45de375f` | Art-direction ownership, explicit gate verdicts, per-asset specs and audits |
| [htdt/godogen](https://github.com/htdt/godogen) | 5,488 | MIT | `05cebffc8b10c5817e8a3db495b82e7b6004ab84` | Canonical references, cost confirmation, generated 2D/3D asset operations |
| [aldegad/sprite-gen](https://github.com/aldegad/sprite-gen) | 716 | Apache-2.0 | `345604183b5427a15e2567ab6958a6eef1e30bad` | Locked identity anchor, raw/curated/runtime separation, deterministic post-processing, manifest SSoT, motion QA |
| [gamedev-skills/awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills) | 534 | Apache-2.0 | `9ca5296b219049c5b68494e1f3c274ead6d727b3` | Portable Skill layout, progressive disclosure, engine-specific handoffs |
| [ybuild-ai/ai-game-art-pipeline-skill](https://github.com/ybuild-ai/ai-game-art-pipeline-skill) | 284 | MIT | `ed4a2ce1a94370d5962c7d079cd9404a863e02c` | Choose pipeline by runtime job, canonical reuse, smallest vertical slice, target-device QA |

## Adopted

- Approve one representative target before batch production.
- Lock canonical identity before character variants or animation.
- Treat generated images as raw inputs, not final assets.
- Apply deterministic cleanup, curation, packing, and manifest generation.
- Make the manifest authoritative for runtime rectangles, pivots, timing, and
  variants.
- Review assets at actual in-game scale and inspect animation as motion.
- Keep provider selection behind the available media capability.

## Deliberately Not Adopted

- Provider-specific pricing, API names, environment variables, or paid model
  assumptions; Loopforge remains provider-neutral.
- A universal chroma color; it can destroy colors in the subject and must be
  chosen per asset.
- One fixed sprite pipeline for every art family.
- Large studio-agent hierarchies; Loopforge keeps one human approval boundary
  and delegates technical integration to engine skills.
- Upstream frontmatter extensions that are not portable across Agent Skills
  hosts.
