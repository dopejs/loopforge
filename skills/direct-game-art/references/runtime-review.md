# Runtime Art Review

Use this reference after technical validation and engine import.

## Evidence Set

Review the exact current runtime export, not a source image or mockup. Record:

- project/source identity and manifest checksum;
- asset IDs and runtime paths visible in the capture;
- target device, viewport, scale, and graphics settings;
- still capture of the representative composition;
- motion capture or preview for animation/VFX;
- importer, memory, draw-call, texture, and frame-time results where applicable.

## Review Order

1. Confirm the capture is current and shows the tested state.
2. Check framing, clipping, alpha, scaling, filtering, seams, and missing assets.
3. Check gameplay hierarchy in color and grayscale; verify critical states do
   not rely only on hue.
4. Check animation pivots, anchor stability, anatomy/identity, timing, and loop
   seams as motion.
5. Compare measured technical cost with the declared budget.
6. Separate objective defects, subjective concerns, and unknowns.

Automated image or manifest checks establish technical facts only. A human
reviewer owns aesthetic acceptance. Record `approved`, `concerns`, or `rejected`
with cited evidence and rationale.
