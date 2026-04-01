# Playwright Screenshot Pipeline 01: Scaffold And CLI

## Goal

Establish a Python-based Playwright project that accepts a target URL and produces a reproducible screenshot run directory for downstream AI review.

## Tasks

- [x] Create the initial project scaffold under `C:\Users\splash\Desktop\python_webpage_capture` for a Python CLI tool, including source package directories, a `README.md`, a `.gitignore`, and dependency/config files (`pyproject.toml` preferred; `requirements.txt` acceptable only if it materially simplifies the setup). Keep the structure minimal and focused on screenshot capture rather than a general web framework.
  - Added a `src/python_webpage_capture` package, packaging metadata in `pyproject.toml`, a minimal README, repository ignore rules, and a unittest smoke test to keep the scaffold verifiable.
- [x] Add Playwright Python as the browser automation dependency and define a documented install/bootstrap path that includes browser installation (`playwright install`). Make the task complete only when a new contributor can follow the repository docs and install the project from a clean machine.
  - Added `playwright>=1.53,<2` to `pyproject.toml`, documented clean-machine setup with `python -m pip install -e .` plus `python -m playwright install chromium`, and covered both expectations with unittest checks.
- [x] Implement a first CLI entrypoint that accepts at minimum `--url`, `--output-dir`, `--run-label`, and `--timeout-ms`, validates the URL, resolves output paths safely under the repository, and prints a concise summary of the planned run before capture begins.
  - Added `python_webpage_capture.cli` with argument parsing, URL validation, repository-bounded output path resolution, run-label checks, and a concise pre-capture plan summary.
  - Wired the `python-webpage-capture` console script in `pyproject.toml`, documented direct and installed CLI usage in `README.md`, and added unittest coverage for valid and invalid plan construction paths.
- [x] Add a configuration module for reusable defaults so device presets, waits, and output naming rules are not hard-coded inside the CLI parser. Keep defaults deterministic and ready for later expansion in subsequent phases.
  - Added `src/python_webpage_capture/config.py` with frozen dataclasses for timeout, device preset, waits, and output naming defaults, then updated the CLI to consume that module instead of embedding those values in parser logic.
  - Extended unittest coverage for default propagation and deterministic config values, and documented the shared defaults module in `README.md`.

## Notes

- Prefer `src/` layout if there is no strong reason not to.
- Use ASCII-only filenames and predictable path names.
- Treat `http://localhost:8080/` as the primary local-development example in docs and examples.
