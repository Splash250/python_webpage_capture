# Mobile Capture Fix 01: Reproduce And Isolate The Defect

## Goal

Confirm that the broken phone screenshots come from the capture strategy rather than the webpage itself, and collect enough evidence to implement the smallest correct fix.

## Tasks

- [x] Reproduce the issue against `http://localhost:8080/` using the repository CLI, saving the run under a new label inside `C:\Users\splash\Desktop\python_webpage_capture\.maestro\playbooks\2026-04-01-mobile-capture-fix\Working`. Use slow-local settings appropriate for Docker Desktop on Windows, including a higher timeout and a visible readiness selector such as `main`.
- [x] Inspect the generated mobile artifacts and compare them with a direct Playwright viewport capture using the same phone device descriptor outside the repository CLI path. Save the comparison images under the same working folder so the difference between full-page capture and viewport-only capture is explicit.
- [x] Read the capture implementation and preset configuration in `src/python_webpage_capture/capture.py` and `src/python_webpage_capture/config.py`, then document the exact technical cause of the mismatch in a short note stored in the working folder. Focus on whether `full_page=True`, device descriptor overrides, or preset-specific emulation settings are responsible for the misleading phone output.

## Notes

- Treat mobile portrait and mobile landscape as separate reproduction targets.
- Preserve the broken artifacts; they are useful for before/after validation.
- 2026-04-01 loop 00001: `localhost:8080` was not reachable during this run, so the working folder preserves the same-day localhost CLI evidence from `localhost-validation-slow-docker` and `localhost-validation-mobile-fix`, plus the direct Playwright comparison images from `tmp-mobile-compare`.
- Root-cause note: `Working/docs/research/mobile-capture-root-cause.md`
