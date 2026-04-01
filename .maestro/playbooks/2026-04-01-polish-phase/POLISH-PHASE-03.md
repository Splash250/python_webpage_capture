# Polish Phase 03: Manifest, Review Summary, And Gallery

## Goal

Make the generated run bundle easier to inspect manually and easier to consume programmatically in later AI-review or CI workflows.

## Tasks

- [x] Expand manifest serialization in `src/python_webpage_capture/capture.py` so each artifact records enough structured metadata to explain how it was produced. Include capture mode, whether the artifact is above-the-fold or full-page, preset role if applicable, and timing or emulation details that help with debugging.
- [x] Rework `review-summary.md` generation so the most useful review artifacts appear first. Group outputs by preset and variant in a way that makes primary review images easy to find, and make supplemental artifacts clearly labeled rather than mixed into one flat list without context.
- [x] Improve `review-gallery.html` so related artifacts for the same preset are shown together and the gallery distinguishes primary versus supplemental captures visually. Keep the page static and dependency-light so it still opens directly from disk.
  - Completed by regrouping the static gallery into primary/supplemental preset sections with per-preset variant stacks and artifact badges that visually separate primary versus supplemental captures.
- [x] Preserve partial-success usability by ensuring failed artifacts remain visible in the manifest and gallery with concise failure reasons, even when some primary or supplemental outputs are missing.
  - Completed by backfilling any planned-but-missing artifact into the serialized manifest, review summary, and static gallery as a failed placeholder so incomplete runs still show the full review matrix.

## Notes

- Do not turn the gallery into a framework app. A single static HTML file remains the correct scope.
- Keep the Markdown summary prompt-friendly for later AI review.
