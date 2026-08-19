# Loopforge Brand Assets

Logo and usage guidelines for Loopforge. The mark is a tilted (−12°) ribbon
lemniscate — "loop" as an infinity symbol with a woven over/under crossing —
paired with a Space Grotesk Bold wordmark (outlined to paths).

## Files

| File | Use |
| --- | --- |
| `svg/loopforge-horizontal-dark.svg` | Primary lockup (mark + wordmark), for dark backgrounds |
| `svg/loopforge-horizontal-light.svg` | Primary lockup, for light backgrounds |
| `svg/loopforge-badge-dark.svg` | App icon / avatar, dark rounded square |
| `svg/loopforge-badge-light.svg` | App icon, light rounded square |
| `svg/loopforge-mark.svg` | Mark only, transparent background (true transparent weave) |
| `svg/loopforge-mark-mono-ink.svg` | Single-color mark, `#0D1420`, for light backgrounds |
| `svg/loopforge-mark-mono-paper.svg` | Single-color mark, `#F4F6FA`, for dark backgrounds |
| `svg/loopforge-favicon.svg` | Simplified mark (no weave, heavier stroke) for ≤32 px |
| `png/badge-dark-512.png`, `png/badge-dark-180.png` | Raster app icons |
| `png/favicon-32.png`, `png/favicon-16.png` | Raster favicons |

## Construction

- 96-unit grid. The loop is a Gerono lemniscate, 54 × 42 units, rotated −12°.
- Stroke width 10 units, round caps and joins.
- The weave is a single over-pass on the upper-right diagonal. In
  `loopforge-mark.svg` the knockout under the over-pass is real transparency
  (SVG mask), so the mark works on any background.
- Wordmark: Space Grotesk Bold (OFL), converted to outlines — renders
  identically everywhere; do not re-set it in a live font.

## Color

| Token | Value | Use |
| --- | --- | --- |
| Ember gradient | `#FF6B00` → `#FF9E1B` → `#FFD25F` (bottom-left → top-right) | Mark |
| Ink | `#0D1420` | Wordmark on light, mono mark |
| Ink surface | `#141C2C` | Dark badge fill |
| Paper | `#F4F6FA` | Wordmark on dark, mono mark |
| Hairline | `#E4E1D9` | Light badge border |

## Rules

- **Clearspace:** at least 25% of the mark width on all sides.
- **Minimum size:** full lockup 120 px wide; mark with weave 48 px; below
  48 px use `loopforge-favicon.svg`; single-color printing uses the mono
  variants (they drop the weave and gradient by design).
- **Do not** re-tint the gradient, remove or change the −12° tilt, add
  shadows/effects, redraw the weave below 48 px, or place the ember mark on
  warm/orange backgrounds (use mono-paper instead).

## Regenerating

PNG exports are Chromium screenshots of the SVGs at exact pixel sizes with a
transparent background. The wordmark outlines were extracted from the Space
Grotesk variable font (wght 700) with fontTools. If the wordmark text ever
changes, re-extract outlines — never substitute a different font.
