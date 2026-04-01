# Polish Phase 05: Developer Documentation And Review Workflow

## Goal

Leave the repository with a clear, practical workflow for generating polished screenshot bundles and handing them off for AI design review.

## Tasks

- [x] Update `README.md` with polished usage examples that cover the primary local workflows: default localhost capture, mobile-focused review, capture-mode overrides, and any new above-the-fold or dual-output options added during this phase.
  - Added examples for the default localhost matrix run, a mobile-only review pass, an explicit capture-mode override workflow, and `--capture-mode both` dual-output usage that maps to the current above-the-fold companion viewport artifacts.
- [x] Document the recommended AI-review handoff format using the actual repository outputs. Explain which files a reviewer should inspect first, how to interpret the manifest and summary, and when to use the gallery versus the Markdown summary.
  - Expanded the README handoff guidance to prioritize `review-summary.md`, explain when to inspect primary versus supplemental presets, position `capture-plan.json` as the source of truth for exact run metadata and failures, and reserve `review-gallery.html` for fast local visual scanning.
- [x] Add a concise "validation checklist" section to `README.md` or another repository doc so future contributors can verify the capture pipeline after changes without reverse-engineering the expected workflow.
  - Added a `Validation Checklist` section to `README.md` with the real smoke-test command, expected CLI summary fields, required bundle artifacts, and explicit `complete-success` validation criteria.
- [x] Ensure the documentation reflects the real CLI and artifact structure produced by the polished implementation rather than an aspirational design that diverges from the code.
  - Corrected the README dual-output wording so `--capture-mode both` now explicitly matches the implementation: every selected preset, including mobile presets, is upgraded to a full-page primary artifact plus a companion viewport artifact.

## Manual Follow-Up

- Review whether `mobile-landscape` should remain part of the default artifact set or move behind an opt-in flag.
- Decide whether a future phase should add CI-facing visual diff tooling on top of the polished screenshot bundle.
