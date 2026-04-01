# Playwright Screenshot Pipeline 04: Verification, Examples, And Hardening

## Goal

Prove the script works end to end against a real URL input and leave the repository with enough documentation and checks that future changes do not quietly break screenshot generation.

## Tasks

- [x] Add automated coverage for the non-browser logic: CLI argument parsing, output path resolution, capture matrix generation, and manifest/report serialization. Use lightweight tests that run quickly and do not require a live external site.
  - Added direct unit coverage for `resolve_output_dir`, capture variant generation order, and manifest/review/gallery serialization without invoking Playwright or a live page.
- [x] Add at least one smoke-test path for the browser workflow that can run against a simple local page or fixture. The test should verify that invoking the tool with a URL creates a run folder, writes the manifest, and produces at least one screenshot artifact.
  - Added a real-browser smoke test that serves a tiny local HTML fixture over `127.0.0.1`, invokes `main([...])`, and asserts the run folder, manifest, and screenshot artifacts are produced.
  - The test skips with explicit setup guidance when Playwright or the Chromium runtime has not been installed yet, keeping the suite deterministic on fresh machines while still exercising the full path once bootstrapped.
- [x] Expand `README.md` with a practical quickstart: installation, Playwright browser setup, example invocations against `http://localhost:8080/`, explanation of the generated folder structure, and an example workflow for feeding the output into an AI reviewer.
  - Expanded the README quickstart with bootstrap commands, module and installed-entrypoint examples, readiness/dark-mode/no-JS sample usage, a concrete run-folder tree, and a prompt-ready AI review workflow based on `review-summary.md` and `capture-plan.json`.
- [x] Add one convenience command or script for common usage, such as `python -m ... --url http://localhost:8080/`, and document the exact command developers should run to validate the project locally after changes.
  - Added `src/python_webpage_capture/__main__.py` so common runs can use `python -m python_webpage_capture --url http://localhost:8080/ ...` without referencing `cli.py` directly.
  - Documented the exact local validation command in `README.md`, including the automated test command and a matching manual smoke-capture command for localhost verification.

## Manual Follow-Up

- Review a sample run in the generated gallery and confirm the chosen presets cover the layouts you care about most.
- Decide whether dark mode should be enabled by default or remain opt-in for this project.
- Decide whether later CI work should add baseline diffing via Chromatic, Percy, or a Playwright-only approach.
