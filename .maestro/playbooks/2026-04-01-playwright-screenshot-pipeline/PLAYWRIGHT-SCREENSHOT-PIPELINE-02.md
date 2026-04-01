# Playwright Screenshot Pipeline 02: Device Matrix And Capture Engine

## Goal

Implement the actual screenshot runner so a single URL can be captured across major desktop, laptop, tablet, and mobile layouts with stable, AI-review-friendly artifacts.

## Tasks

- [x] Define a capture matrix in code rather than inline literals. Include named presets for at least these viewport families: large desktop, standard desktop, laptop, tablet portrait, tablet landscape, mobile portrait, and mobile landscape. Use Playwright device descriptors where useful, but keep final viewport values explicit in the saved metadata for review reproducibility.
  Note: Implemented centralized `CAPTURE_MATRIX` presets in `src/python_webpage_capture/config.py` with explicit viewport dimensions, stable sortable filenames, optional Playwright device descriptor mappings, and tests covering family coverage plus resolved viewport metadata expectations.
- [x] Implement the capture engine that launches Playwright Chromium, opens the provided URL, waits for the page to stabilize, and saves screenshots for each preset. Capture full-page screenshots by default, and ensure the implementation can survive slower local pages by honoring `--timeout-ms`.
  Note: Implemented `run_capture_plan()` in `src/python_webpage_capture/capture.py`, updated the CLI to execute real runs instead of summary-only planning, and added mocked capture-engine tests covering per-preset full-page output, timeout-aware stabilization waits, and failure isolation so one broken preset does not stop the rest.
- [x] Make capture output deterministic and AI-friendly by standardizing browser state before each shot: set viewport/device emulation from the preset, use a consistent locale/timezone unless explicitly overridden, disable motion where practical (`prefers-reduced-motion` or equivalent), and wait for fonts/network/rendering to settle before capturing.
  Note: Added deterministic context construction in `src/python_webpage_capture/capture.py` with explicit viewport overrides layered on top of Playwright device descriptors, default `en-US`/`UTC` browser state plus CLI overrides, reduced-motion media emulation and animation-suppression init script, and extra font/render settle waits covered by expanded fake-Playwright tests.
- [x] Add support for optional variants that are useful for design review, with flags that can be turned on without changing code: dark mode capture, a second pass with JavaScript disabled if needed for debugging, and per-run custom waits or selectors to ensure above-the-fold content is visible before screenshots are taken.
  Note: Added CLI flags for `--dark-mode`, `--disable-javascript-pass`, repeatable `--ready-selector`, and `--ready-wait-ms`; updated the capture engine to run stable baseline plus optional dark and no-JS passes with variant-specific filenames and readiness waits; and expanded unittest coverage for plan parsing, selector waits, variant browser-state overrides, and formatted run output.
- [x] Persist one machine-readable manifest per run that records the input URL, timestamp, each preset name, viewport dimensions, emulation choices, output file paths, and whether each screenshot succeeded or failed.
  Note: Added per-run JSON manifest writing in `src/python_webpage_capture/capture.py` using the configured metadata filename, recording run URL/timestamp plus per-capture preset, variant, emulation, output-path, and status/error fields; expanded tests to verify successful and failed entries are persisted; and updated README status/usage notes to document the new artifact.

## Notes

- Prefer failure isolation: one broken preset should not erase the rest of the run.
- Default screenshot names should be stable and sortable, for example `01-desktop-1440x900.png`.
- If a preset maps to a Playwright named device, still record the resolved viewport and user agent in metadata.
