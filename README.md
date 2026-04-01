# python_webpage_capture

Minimal Python scaffold for a Playwright-driven webpage screenshot CLI.

## Repository Layout

```text
src/python_webpage_capture/
tests/
```

The project uses a `src/` layout so future CLI and capture modules stay isolated from test-time import side effects.

## Current Status

This phase establishes the repository scaffold and the first working capture path:

- packaging via `pyproject.toml`
- Playwright Python dependency management
- documented browser bootstrap with `playwright install`
- source package directory under `src/`
- multi-preset Chromium capture engine with per-preset failure isolation
- optional dark-mode and JavaScript-disabled review variants with readiness controls
- per-run JSON manifests with preset, emulation, and output status metadata
- per-run Markdown review summaries with relative screenshot references for prompt-ready review bundles
- per-run static HTML galleries for fast local inspection directly from disk
- run-level status classification plus artifact-safe logging for complete success, partial success, and total failure cases
- basic unittest coverage
- repository hygiene files such as `.gitignore`

The current playbook phase now writes a machine-readable manifest, a compact Markdown review bundle summary, and a static HTML gallery alongside the screenshots.

## Quickstart

Create a virtual environment, install the package in editable mode, and download the Chromium runtime used by the capture pipeline:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
python -m playwright install chromium
```

For a clean-machine bootstrap, the repository requires both steps:

1. `python -m pip install -e .` installs the Python package and the Playwright library.
2. `python -m playwright install chromium` downloads the browser binary used by later screenshot runs.

If you want all Playwright browser targets instead of the single default runtime for this project, run `python -m playwright install`.

Start a local site on `http://localhost:8080/`, then run the CLI against it. The examples below are the primary local workflows supported by the current implementation.

Default localhost capture with the full preset matrix:

```powershell
python -m python_webpage_capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label local-smoke `
  --timeout-ms 30000
```

The package also keeps the explicit module path available if you want to target the CLI module directly:

```powershell
python -m python_webpage_capture.cli --url http://localhost:8080/ --output-dir runs --run-label local-smoke
```

Installed entrypoint form:

```powershell
python-webpage-capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label local-smoke
```

Mobile-focused review pass that limits output to the primary phone viewport and its supplemental landscape companion:

```powershell
python-webpage-capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label mobile-review `
  --preset mobile-portrait `
  --preset mobile-landscape `
  --ready-selector main `
  --ready-wait-ms 500
```

If the page renders async UI, add readiness guards so the capture waits for the content you actually care about:

```powershell
python -m python_webpage_capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label local-ready `
  --ready-selector main `
  --ready-selector [data-test-id="dashboard-loaded"] `
  --ready-js-predicate "window.__APP_READY__ === true" `
  --ready-wait-ms 750 `
  --dark-mode `
  --disable-javascript-pass
```

When you need a narrower workflow on a slow localhost page, the CLI can now filter presets, override capture mode, and expose the existing navigation settle controls directly:

```powershell
python-webpage-capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label local-focused `
  --preset standard-desktop `
  --preset mobile-portrait `
  --exclude-preset standard-desktop `
  --capture-mode full-page `
  --navigation-wait-until domcontentloaded `
  --post-navigation-wait-ms 1200 `
  --ready-selector main `
  --ready-wait-ms 500
```

When you want dual output from specific presets, `--capture-mode both` upgrades every selected preset to a full-page primary artifact and adds a companion viewport artifact for that same preset. In the generated bundle, that companion viewport image is the above-the-fold review capture:

```powershell
python-webpage-capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working `
  --run-label local-dual-output `
  --preset standard-desktop `
  --preset tablet-portrait `
  --capture-mode both `
  --dark-mode
```

## Generated Output

`--output-dir` must resolve under the repository root so runs stay contained in the project workspace.
Reusable defaults live in `src/python_webpage_capture/config.py`, which centralizes the deterministic device preset, wait strategy, timeout default, and output naming rules used by the runner.
The capture matrix is also defined there as named presets for large desktop, standard desktop, laptop, tablet portrait, tablet landscape, mobile portrait, and mobile landscape, with explicit viewport dimensions retained even when a Playwright device mapping is attached.
The runner launches Playwright Chromium once per run, opens the target URL for each preset, waits for the page to settle, and writes stable sortable screenshots such as `01-large-desktop-1728x1117-default-full-page.png`.
Each preset now declares its own explicit primary `capture_mode` in `src/python_webpage_capture/config.py`, and the preset model can also carry an opt-in flag for an additional above-the-fold companion artifact when a preset is configured for dual output.
Presets now also carry stable taxonomy metadata so the review bundle can distinguish primary review checkpoints from supplemental coverage without removing any of the current device families.
The current taxonomy treats Standard Desktop, Tablet Portrait, and Mobile Portrait as the primary review presets, while Large Desktop, Laptop, Tablet Landscape, and Mobile Landscape remain available as supplemental context.
Desktop and tablet presets use `full_page` capture, while mobile presets default to `viewport` capture to avoid the distorted stitched output that is common when full-page screenshots are taken under phone emulation.
That default makes AI review artifacts more trustworthy because the mobile screenshots reflect the emulated device viewport the reviewer is supposed to assess rather than a synthetic stitched page that can introduce false layout defects.
Each preset runs inside a standardized browser context with explicit viewport values, a deterministic default locale/timezone (`en-US` and `UTC`), Playwright device emulation where applicable, reduced-motion media emulation, and extra waits for network idle, font readiness, and render-settle before capture.
Screenshot filenames always encode the preset stem, variant slug, and capture type so each artifact stays understandable on its own during later review.
Optional flags can add dark-mode and no-JavaScript artifact variants, required visible selectors via `--ready-selector`, and an extra per-run `--ready-wait-ms` pause before the screenshot is taken.
Preset scope can also be narrowed with repeatable `--preset` and `--exclude-preset` flags, while `--capture-mode` can force `viewport`, `full-page`, or `both` artifacts without editing `config.py`.
`--capture-mode both` is the current dual-output workflow: it upgrades the selected presets, including mobile presets, to a full-page primary capture plus a companion viewport artifact, which the manifest and gallery label as an above-the-fold companion capture.
For slower Docker-backed pages, `--navigation-wait-until` and `--post-navigation-wait-ms` let you tune the initial navigation and settle window from the command line instead of changing source defaults.
When a local page keeps streaming work after the DOM is visible, `--ready-js-predicate` can wait for an app-specific browser condition such as `window.__APP_READY__ === true` without hard-coding another sleep into the runner.
Every run also writes `capture-plan.json` into the run directory with the input URL, capture timestamp, run-level status, concise event logs, per-preset family, review role, viewport, `capture_mode`, emulation details, screenshot output paths, and success or failure status for each artifact.
It also writes `review-summary.md`, which summarizes the run metadata, enabled variants, primary review presets, preset taxonomy, reviewer rubric, failure reasons, and relative artifact paths so the whole folder can be dropped into an AI review prompt with minimal cleanup even after a broken run.
For local inspection, it writes `review-gallery.html`, a dependency-light static gallery that links directly to the generated screenshots and still shows failed capture slots plus run-level error context when a preset or the entire run does not render successfully, along with each artifact's preset family and review role.

Example run folder:

```text
.maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working/
\-- local-smoke/
    |-- 01-large-desktop-1728x1117-default-full-page.png
    |-- 02-standard-desktop-1440x900-default-full-page.png
    |-- 03-laptop-1280x800-default-full-page.png
    |-- 04-tablet-portrait-820x1180-default-full-page.png
    |-- 05-tablet-landscape-1180x820-default-full-page.png
    |-- 06-mobile-portrait-390x844-default-viewport.png
    |-- 07-mobile-landscape-844x390-default-viewport.png
    |-- capture-plan.json
    |-- review-gallery.html
    \-- review-summary.md
```

When optional variants are enabled, matching artifacts are written with the same sortable stem, for example `06-mobile-portrait-390x844-dark-viewport.png` and `02-standard-desktop-1440x900-no-js-full-page.png`.

## AI Reviewer Workflow

The generated run folder is designed to be handed to an AI reviewer as a self-contained bundle.
Use the repository outputs in this order so the reviewer sees the run context before judging screenshots:

1. Start with `review-summary.md`. It is the best human-readable entry point because it already includes the run status, enabled variants, selected primary review presets, preset taxonomy, reviewer rubric, and relative paths to every artifact grouped by review role and variant.
2. Inspect the primary review presets listed in `review-summary.md` first: Standard Desktop, Tablet Portrait, and Mobile Portrait in the default matrix. Those are the main decision points for design review. Use the supplemental presets after that to confirm edge cases, wider breakpoints, and orientation-specific behavior.
3. Open `review-gallery.html` when you want a fast visual sweep or need to click through screenshots locally. The gallery is best for spotting obvious regressions, checking whether expected artifacts exist, and reviewing failed capture slots without parsing JSON.
4. Use `capture-plan.json` as the machine-readable source of truth. It records the exact URL, run label, run status, capture counts, preset metadata, review roles, emulation details, artifact paths, timing configuration, and any run or artifact errors. Reach for it when the reviewer needs to verify what was supposed to be captured or when a summary/gallery view looks suspicious.

Recommended handoff format:

1. Share the entire run directory when possible so the reviewer has the screenshots plus `review-summary.md`, `review-gallery.html`, and `capture-plan.json` together.
2. If you cannot share the whole folder, provide `review-summary.md` and the referenced screenshots first.
3. Include `capture-plan.json` when the review needs exact file names, capture counts, preset metadata, or failure diagnostics.
4. Mention whether the run is `complete-success`, `partial-success`, or `total-failure` so the reviewer knows whether missing screenshots indicate product issues or capture issues.

How to interpret the outputs:

- `review-summary.md`: reviewer-oriented narrative and artifact index. Use this in the prompt.
- `capture-plan.json`: exact serialized run record. Use this to resolve ambiguity.
- `review-gallery.html`: local browsing surface. Use this for quick scanning, not as the sole source of run metadata.

Example reviewer prompt:

```text
Review this screenshot bundle for layout regressions and visual quality.
Use review-summary.md as the run overview, then inspect the screenshots for:
- hierarchy and scan order
- spacing and alignment consistency
- overflow, clipping, or truncation
- mobile/tablet adaptation versus desktop
- CTA prominence and readability

Call out issues by preset name and screenshot filename.
```

## Validation Checklist

Use this checklist after changing the CLI, preset matrix, artifact serialization, or review-bundle formatting. It is intentionally tied to the current implementation so contributors can confirm the real workflow without reverse-engineering the code.

1. Run the automated suite first:

```powershell
python -m unittest discover -s tests
```

2. If you changed browser-facing capture behavior, rerun a local smoke capture against a real local page:

```powershell
python -m python_webpage_capture `
  --url http://localhost:8080/ `
  --output-dir .maestro/playbooks/2026-04-01-polish-phase/Working `
  --run-label local-verify `
  --ready-selector main
```

3. Confirm the CLI summary matches the requested run inputs before the browser work starts:
   - selected presets are listed by name
   - `Capture mode override` reflects `default`, `viewport`, `full-page`, or `both`
   - `Variant passes` reflects whether `--dark-mode` or `--disable-javascript-pass` was enabled
   - `Planned artifact count` matches the selected presets and any extra dual-output captures

4. Inspect the generated run directory and verify the expected repository artifacts exist:
   - `capture-plan.json`
   - `review-summary.md`
   - `review-gallery.html`
   - screenshot files named like `02-standard-desktop-1440x900-default-full-page.png`

5. Validate the artifact contents in this order:
   - `review-summary.md` should show the run status, capture counts, enabled variants, preset taxonomy, and relative screenshot paths
   - `capture-plan.json` should include the exact CLI inputs, `capture_counts`, per-capture preset metadata, `artifact_capture_type`, and any errors
   - `review-gallery.html` should render the same run status and expose every successful or failed capture slot locally

6. When `--capture-mode both` is used, confirm the selected presets emit both a `*-full-page.png` primary artifact and a `*-viewport.png` companion artifact in the same run folder, including mobile presets when they were selected for that run.

7. When optional variants are enabled, confirm the filenames and summaries use the real variant slugs:
   - `default`
   - `dark`
   - `no-js`

8. Treat the run as healthy only if the CLI ends with `Complete success` and `capture-plan.json` reports `run_status` = `complete-success`. If it reports `partial-success` or `total-failure`, use the recorded failure reasons before assuming the product UI regressed.

## Development

Validate the project locally after changes with:

```powershell
python -m unittest discover -s tests
```

For a full manual verification pass after the automated tests, rerun the local smoke capture:

```powershell
python -m python_webpage_capture --url http://localhost:8080/ --output-dir .maestro/playbooks/2026-04-01-playwright-screenshot-pipeline/Working --run-label local-verify
```
