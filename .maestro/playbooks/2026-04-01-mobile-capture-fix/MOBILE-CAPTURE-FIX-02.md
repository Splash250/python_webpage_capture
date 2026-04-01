# Mobile Capture Fix 02: Implement Preset-Aware Screenshot Behavior

## Goal

Change the screenshot pipeline so mobile captures are reviewable and faithful to device emulation without regressing desktop and tablet coverage.

## Tasks

- [x] Add preset-level capture-mode metadata in `src/python_webpage_capture/config.py` so screenshot behavior is explicit in configuration rather than hard-coded in the capture engine. Keep desktop and tablet presets as full-page captures, and switch mobile presets to viewport-only capture.
- [x] Update `src/python_webpage_capture/capture.py` to honor the preset-level capture mode when calling `page.screenshot(...)`. Also persist that information into the manifest so downstream review tooling can tell whether each artifact is full-page or viewport-only.
- [x] Update repository tests in `tests/test_package.py` so the capture mode is asserted per preset and the mobile defect does not silently reappear in a later refactor.
- [x] Update `README.md` to explain why mobile presets do not use full-page capture by default and how that choice improves the trustworthiness of AI design review artifacts.

## Notes

- Keep the fix narrow. Do not redesign the entire capture pipeline in this phase.
- If the implementation introduces a new term such as `full_page`, use the same term consistently in config, manifest, and tests.

## Completion Notes

- 2026-04-01: Added preset-level `capture_mode` metadata, wired it into Playwright screenshot calls, serialized it into the manifest, updated regression coverage, and documented why mobile defaults to viewport capture for more trustworthy review artifacts.
