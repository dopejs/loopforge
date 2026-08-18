# Asset Provenance

Use this reference when authoring or validating manifest entries.

## Minimum Record

Every asset records:

- source kind: `human`, `generated`, `licensed`, `public-domain`, or `derived`;
- source URI or project-relative source path;
- creator/provider and model/tool when applicable;
- creation or acquisition date;
- license/SPDX identifier or `proprietary` with the controlling policy;
- prompt/reference identifiers for generated work, without secrets;
- parent asset IDs and ordered transformations for derivatives;
- checksum when the source or runtime file exists;
- restrictions, attribution, and expiration/retention obligations.

`unknown`, a search-result page, or "found online" is not sufficient for an
asset intended to ship. Keep an entry `planned` or `blocked` until provenance is
resolved.

## Transformations

Record deterministic and manual changes separately. Examples include chroma
removal, crop, alpha cleanup, color-space conversion, downscale algorithm,
palette mapping, compression, atlas packing, pivot edits, and human paintover.

Raw generated output remains immutable. Store human curation as selections and
non-destructive transforms where possible, then build runtime output from that
curated truth. Never export directly from raw after a human has curated a
different result.

## Security and Provider Use

- Confirm before paid generation or uploading proprietary references.
- Keep credentials out of prompts, manifests, logs, and command history.
- Treat downloaded files as untrusted; validate type and dimensions before use.
- Do not assume a provider's terms grant commercial rights. Record the terms or
  policy snapshot used for the decision.
