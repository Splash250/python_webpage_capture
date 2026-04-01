# Polish Phase 02: Stability Controls And CLI Ergonomics

## Goal

Reduce capture flakiness on slow local pages and make common workflows accessible through the CLI rather than through code edits.

## Tasks

- [x] Extend the capture plan and CLI in `src/python_webpage_capture/cli.py`, `src/python_webpage_capture/models.py`, and related modules to support explicit workflow controls such as capture-mode selection, preset inclusion or exclusion, and improved settle timing for slow environments.
  - Added CLI flags for preset inclusion/exclusion, capture-mode overrides, and navigation/post-navigation settle controls, then threaded the resolved preset set through manifests and run summaries.
- [x] Improve readiness logic in `src/python_webpage_capture/capture.py` so the runner can combine navigation completion, visible selector checks, font readiness, and a final settle window in a predictable sequence. Prefer configuration-driven waits over ad hoc sleeps.
  - Consolidated readiness into a single configuration-driven sequence derived from the capture plan: optional navigation follow-up states, visible selectors, font readiness, render settle, then configured timeout windows at the end.
- [x] Add at least one advanced readiness option suitable for stubborn local pages, such as a custom JavaScript readiness predicate or a more explicit network-idle/settle configuration, while keeping defaults simple for normal runs.
  - Added `--ready-js-predicate` to the CLI and capture plan so stubborn local pages can wait on an app-specific browser condition without changing defaults or introducing another fixed sleep. The predicate is recorded in the manifest, shown in the pre-run summary, documented in `README.md`, and covered by unit tests across plan building and runner readiness sequencing.
- [x] Make CLI output more actionable by surfacing the selected presets, capture modes, output directory, and any supplemental artifacts before the run starts, then reporting partial-success conditions clearly at the end.
  - Expanded the pre-run summary with resolved preset outputs, variant passes, planned artifact counts, and supplemental artifact breakdowns; the final run report now distinguishes complete, partial, and total failures with capture counts and a focused failed-artifact section.

## Notes

- Optimize for Docker-backed localhost pages first; that is the highest-friction environment in this repository.
- Avoid adding flags that are redundant with existing configuration unless they materially improve day-to-day usage.
