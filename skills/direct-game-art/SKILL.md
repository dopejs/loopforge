---
name: direct-game-art
description: Define, produce, validate, and review production game art for a Loopforge project, including art direction, a human-approved representative target, asset families, provenance-aware manifests, technical checks, and in-engine visual evidence. Use when a validated gameplay prototype needs coherent visual direction, representative assets, asset production planning, asset import review, or art-quality evidence. Do not use for broad game design, unscoped asset batches, release approval, or claims that an image is production-ready without technical and human review.
---

# Direct Game Art

Turn one gameplay need into an approved visual target and a traceable, testable
asset set. Keep creative judgment with the human reviewer; make every asset's
source, transformation, technical contract, and review status auditable.

## Operating Contract

1. Resolve the project root and a working `loopforge` invocation. Run
   `loopforge inspect --format json`, `loopforge doctor --format json`, and
   `loopforge status --format json` before mutating workflow state.
2. Read the active experiment, gameplay hypothesis revision, platform, and
   current source/build identity. Do not art-direct against an unevidenced or
   stale gameplay state without recording that limitation.
3. Pass the latest project revision through `--expected-revision` on every
   Loopforge mutation. After an expected-revision conflict, reread status and
   recompute; never blind-retry.
4. Keep project-owned paths relative to the project root. Do not edit Loopforge
   event, snapshot, or checksum files directly.
5. Treat downloaded or generated inputs as untrusted. Do not upload proprietary
   material or secrets to a media provider without explicit user configuration.

Read [references/art-direction.md](references/art-direction.md) for the review
checklist and [references/provenance.md](references/provenance.md) for source,
license, and transformation rules. Read
[references/research-basis.md](references/research-basis.md) when changing this
workflow; it records the upstream GitHub patterns and pinned revisions used to
derive these contracts.

## Gates and Outputs

Produce only the artifacts needed for the current stage:

| Stage | Required output | Gate |
|---|---|---|
| `ART_DIRECTION` | Art direction brief and representative target | Human approval is `pending` until explicit confirmation |
| `ASSET_PLANNING` | Approved target and provenance-aware manifest | No batch production before target approval |
| `ASSET_PRODUCTION` | Assets, source records, and technical validation | Every manifest entry validates |
| `ART_REVIEW` | Runtime capture and evidence review | Human accepts target, integration, and known limitations |

Use the templates in `assets/` and keep their headings/keys stable. A draft
with placeholders, missing provenance, or an unapproved target is blocked.

Validate a manifest before importing or registering assets:

```bash
python <skill-dir>/scripts/validate_manifest.py \
  --project <project-root> --manifest <manifest.json> \
  --require-approved --format json
```

Treat a non-zero result as blocked. The validator checks structure, unique IDs,
workspace-relative paths, provenance/license fields, target approval, declared
dimensions, and supported raster dimensions where it can read them without
third-party dependencies.

Maintain three distinct layers for generated or transformed art:

- `raw`: immutable provider/source output; never ship directly;
- `curated`: human-selected output plus non-destructive edits and transforms;
- `runtime`: deterministic export produced from curated truth plus its manifest.

The manifest is the runtime source of truth. Runtime code must not reconstruct
frame rectangles, pivots, timing, or variants from pixels or filename guesses.

## Art Direction

1. Bind the brief to the experiment ID, gameplay hypothesis revision, platform,
   camera, display aspect, and tested build/source identity.
2. Define the player-facing hierarchy: avatar, hazards, interactables, reward,
   feedback, background, and UI. State how color, value, silhouette, motion,
   and scale distinguish states during play.
3. Set a restrained palette, material language, lighting/camera assumptions,
   readability limits, accessibility considerations, and performance budget.
4. Name explicit non-goals. Do not expand into a full content bible when one
   representative slice is enough to test coherence and readability.

## Representative Target

1. Select the smallest target that proves the direction: usually one gameplay
   frame containing the avatar, primary hazard, reward, background treatment,
   and critical feedback state, or one representative hero asset when the
   integration is not yet available.
2. Define acceptance criteria that can be inspected: hierarchy, silhouette,
   contrast, state legibility, style consistency, platform framing, and budget.
3. Record target references and their provenance. Mark approval `pending` and
   present the target plus uncertainties to the human reviewer.
4. Do not generate or commission a batch until the reviewer supplies an
   explicit approval, approver identity, and rationale. A recommendation is not
   approval; never infer it from silence or a positive comment.

## Asset Planning and Production

1. Split the approved target into asset families and assign stable IDs. Each
   manifest entry must state role, target path, dimensions/aspect, format,
   color/alpha requirements, variants, owner, provenance, license, and
   transformation history.
2. Choose the pipeline by runtime job: static props/icons use one isolated
   image plus deterministic cleanup; canonical characters reuse an accepted
   identity source; animated sprites require locked identity anchors, explicit
   states/timing/pivots, contact sheets, and motion previews; backgrounds are
   reviewed at target framing and texture budgets; UI is reviewed in its real
   layout and interaction states.
3. Prefer the available image-generation or media capability for new raster
   assets when requested. Confirm before any paid or externally uploaded
   generation. If no capability is available, produce a complete asset brief
   and manifest with `status: planned`; do not claim an image was generated or
   inspected.
4. Keep source files, raw generations, curation decisions, and runtime exports
   distinguishable. Preserve source checksums when available, apply curation
   downstream during export, and never overwrite a human-edited asset silently.
5. Produce only the approved family and declared variants. Defer decorative
   batches, alternate styles, and polish that do not answer the target review.

## Technical Validation and Integration

1. Validate every manifest entry before engine import: file exists, path stays
   inside the project, format and dimensions match the contract, file size is
   within budget, and source/license metadata is complete.
2. Import using the project's engine conventions. Record importer settings,
   filtering/mipmap decisions, atlas or compression changes, and any generated
   derivative as transformations.
3. For animation, verify both static frame integrity and motion continuity.
   Frame count, alpha, and identity consistency cannot prove a readable loop;
   inspect contact sheets and playback for anchor jitter, anatomy drift, timing,
   loop seams, and start/middle/end readability.
4. Capture the actual running play state with the current asset identity. Inspect
   for blank output, clipping, unreadable state changes, contrast failures,
   texture seams, incorrect alpha, scaling artifacts, and frame/performance
   regressions. A source image or mockup is not runtime evidence.
5. Read [references/runtime-review.md](references/runtime-review.md) before
   recording the review. Separate automated technical checks from human visual
   judgment and list every known limitation.

## Review and Completion

Fill `assets/asset-review.md` with cited manifest IDs, target acceptance
criteria, strongest supporting and contradicting observations, technical
results, integration evidence, confidence, and exactly one next action.

Report:

- experiment ID, hypothesis revision, target revision, and project revision;
- target approval status, approver identity, and rationale;
- manifest path/checksum and asset IDs produced or changed;
- provenance and license status, technical checks, runtime capture IDs;
- claims that are `satisfied`, `unknown`, `stale`, or `blocked`;
- limitations and exactly one next action.

Never report `ART_APPROVED`, `PRODUCTION_READY`, or a human visual review
unless the corresponding explicit approval and evidence exist.
