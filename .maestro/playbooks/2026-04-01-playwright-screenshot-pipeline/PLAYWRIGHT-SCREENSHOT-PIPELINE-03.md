# Playwright Screenshot Pipeline 03: Review Packaging And Reporting

## Goal

Turn raw screenshots into a review package that an AI model or human reviewer can understand quickly without guessing which image corresponds to which layout or state.

## Tasks

- [x] Generate a review bundle for each run that includes the screenshots plus a compact Markdown summary file describing the URL, run label, capture timestamp, preset list, and any enabled variants such as dark mode. The Markdown should be structured so it can be pasted directly into an AI prompt with minimal cleanup.
  Added `review-summary.md` generation per run with YAML front matter, compact run metadata, preset list, and relative screenshot artifact paths, and exposed the summary path in the run result and manifest.
- [x] Add a derived index artifact that makes the screenshot set easier to inspect locally, such as a simple HTML gallery or contact-sheet-style page generated from the manifest. Keep it static and dependency-light so it can be opened directly from disk.
  Added `review-gallery.html` generation per run, exposed its path in the run result and manifest, and rendered a static card gallery with relative screenshot links plus failed-capture placeholders for direct local inspection.
- [x] Include reviewer guidance in the generated summary so the output is immediately usable for design critique. The rubric should direct the reviewer to comment on hierarchy, spacing, visual balance, CTA prominence, text density, awkward wrapping, overflow/clipping, and mobile/tablet adaptation.
  Added a dedicated reviewer guidance section to `review-summary.md` with a prompt-ready design critique rubric covering hierarchy, spacing, balance, CTA emphasis, text density, wrapping, clipping, and responsive adaptation.
- [x] Add robust logging and run-level error reporting so failed captures still produce a usable summary. The summary and manifest should clearly distinguish complete success, partial success, and total failure, with concise failure reasons per preset.
  Added run-level status classification, event logs, and synthesized per-preset failure records for aborted runs so `capture-plan.json`, `review-summary.md`, and `review-gallery.html` are still emitted for complete success, partial success, and total failure cases.

## Notes

- The generated review summary should prefer relative paths within the run folder so the package is portable.
- Keep the output focused on design review rather than regression diffing; that can be layered in later.
