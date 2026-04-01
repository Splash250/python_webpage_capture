# Polish Phase 01: Capture Modes And Preset Strategy

## Goal

Make screenshot behavior explicit and review-oriented by supporting intentional capture modes and a clearer preset strategy instead of relying on hard-coded assumptions.

## Tasks

- [x] Refactor preset configuration in `src/python_webpage_capture/config.py` so each preset explicitly defines its primary capture behavior. Support a normalized concept such as `capture_mode` or equivalent with values that cover at least viewport-only, full-page, and optional dual-output behavior where needed.
  - Added explicit `capture_mode` declarations for every preset plus `include_above_the_fold_capture` metadata so dual-output intent can be represented without changing current capture behavior.
- [x] Add support in the repository code for generating above-the-fold artifacts in addition to the preset's primary capture when enabled. Keep naming deterministic and sortable so each preset can produce related outputs without ambiguity.
  - Extended the runner to emit one artifact per declared `output_capture_type` from a single page load, so presets can add a secondary viewport capture without changing the current default matrix.
  - Added `capture_type` metadata to the manifest, review summary, gallery, and CLI result output, and applied deterministic `-viewport` suffixes for supplemental above-the-fold artifacts.
- [x] Review the existing preset list and adjust taxonomy only where it improves clarity without destabilizing the current tool. Preserve the current desktop, laptop, tablet, and mobile families, but make it possible to mark some presets as primary review presets and others as supplemental.
  - Added explicit `family` and `review_preset_role` metadata to every preset so the matrix keeps the full desktop/laptop/tablet/mobile coverage while distinguishing primary review checkpoints from supplemental captures.
  - Classified Standard Desktop, Tablet Portrait, and Mobile Portrait as primary review presets and exposed that taxonomy in the manifest, Markdown review summary, HTML gallery, and CLI plan summary.
- [x] Update artifact naming conventions so output files encode enough context for later review, including preset identity and capture type, without requiring the reviewer to read the manifest first.
  - Changed screenshot artifact naming to always include the preset stem, variant slug, and capture type so standalone files remain reviewable without opening `capture-plan.json`.

## Notes

- Keep mobile viewport capture as the safe default unless there is strong evidence to change it.
- Do not remove the existing preset coverage; refine it.
