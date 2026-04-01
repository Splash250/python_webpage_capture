"""CLI entrypoint for deterministic screenshot capture runs."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from python_webpage_capture.capture import format_capture_run_result, run_capture_plan
from python_webpage_capture.config import (
    DEFAULTS,
    VALID_NAVIGATION_WAIT_UNTIL,
    get_capture_preset,
)
from python_webpage_capture.models import CapturePlan

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise argparse.ArgumentTypeError(
            "URL must include an http or https scheme and a hostname."
        )
    return value


def validate_run_label(value: str) -> str:
    if not value.strip():
        raise argparse.ArgumentTypeError("Run label must not be empty.")
    if any(separator in value for separator in ("/", "\\")):
        raise argparse.ArgumentTypeError("Run label must not contain path separators.")
    return value


def resolve_output_dir(raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = REPOSITORY_ROOT / candidate

    resolved = candidate.resolve(strict=False)
    if not resolved.is_relative_to(REPOSITORY_ROOT):
        raise argparse.ArgumentTypeError(
            f"Output directory must stay under repository root: {REPOSITORY_ROOT}"
        )
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python-webpage-capture",
        description="Run a deterministic Playwright screenshot capture across device presets.",
    )
    parser.add_argument("--url", required=True, type=validate_url, help="Target URL.")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=resolve_output_dir,
        help="Output directory under the repository root.",
    )
    parser.add_argument(
        "--run-label",
        required=True,
        type=validate_run_label,
        help="Stable label for the capture run directory.",
    )
    parser.add_argument(
        "--timeout-ms",
        default=DEFAULTS.timeout_ms,
        type=int,
        help=f"Navigation timeout in milliseconds. Default: {DEFAULTS.timeout_ms}.",
    )
    parser.add_argument(
        "--preset",
        action="append",
        default=[],
        help="Capture only the named preset or slug. Repeatable.",
    )
    parser.add_argument(
        "--exclude-preset",
        action="append",
        default=[],
        help="Exclude the named preset or slug from the run. Repeatable.",
    )
    parser.add_argument(
        "--capture-mode",
        choices=["default", "viewport", "full-page", "both"],
        default="default",
        help=(
            "Override artifact mode for the selected presets. "
            "Use default to keep preset-defined modes."
        ),
    )
    parser.add_argument(
        "--navigation-wait-until",
        choices=sorted(VALID_NAVIGATION_WAIT_UNTIL),
        default=DEFAULTS.waits.navigation_wait_until,
        help=(
            "Playwright navigation completion target. "
            f"Default: {DEFAULTS.waits.navigation_wait_until}."
        ),
    )
    parser.add_argument(
        "--post-navigation-wait-ms",
        default=DEFAULTS.waits.post_navigation_wait_ms,
        type=int,
        help=(
            "Extra wait in milliseconds immediately after navigation stability checks. "
            f"Default: {DEFAULTS.waits.post_navigation_wait_ms}."
        ),
    )
    parser.add_argument(
        "--locale",
        default=DEFAULTS.locale,
        help=f"Browser locale override. Default: {DEFAULTS.locale}.",
    )
    parser.add_argument(
        "--timezone-id",
        default=DEFAULTS.timezone_id,
        help=f"Browser timezone override. Default: {DEFAULTS.timezone_id}.",
    )
    parser.add_argument(
        "--dark-mode",
        action="store_true",
        help="Capture an additional dark-mode variant for each preset.",
    )
    parser.add_argument(
        "--disable-javascript-pass",
        action="store_true",
        help="Capture an additional pass with JavaScript disabled for debugging.",
    )
    parser.add_argument(
        "--ready-selector",
        action="append",
        default=[],
        help="CSS selector that must become visible before screenshots are taken. Repeatable.",
    )
    parser.add_argument(
        "--ready-js-predicate",
        help=(
            "JavaScript expression that must evaluate truthy in the page before "
            "screenshots are taken, for stubborn local apps."
        ),
    )
    parser.add_argument(
        "--ready-wait-ms",
        default=0,
        type=int,
        help="Extra per-run wait in milliseconds after readiness checks complete.",
    )
    return parser


def build_capture_plan(argv: list[str] | None = None) -> CapturePlan:
    args = build_parser().parse_args(argv)
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be a positive integer.")
    if args.post_navigation_wait_ms < 0:
        raise SystemExit("--post-navigation-wait-ms must be zero or a positive integer.")
    if args.ready_wait_ms < 0:
        raise SystemExit("--ready-wait-ms must be zero or a positive integer.")

    plan = CapturePlan(
        url=args.url,
        output_dir=args.output_dir,
        run_label=args.run_label,
        timeout_ms=args.timeout_ms,
        device_preset=DEFAULTS.primary_preset,
        preset_include=tuple(args.preset),
        preset_exclude=tuple(args.exclude_preset),
        capture_mode=args.capture_mode.replace("-", "_"),
        navigation_wait_until=args.navigation_wait_until,
        post_navigation_wait_ms=args.post_navigation_wait_ms,
        locale=args.locale,
        timezone_id=args.timezone_id,
        capture_dark_mode=args.dark_mode,
        capture_no_javascript=args.disable_javascript_pass,
        ready_selectors=tuple(args.ready_selector),
        ready_js_predicate=args.ready_js_predicate,
        ready_wait_ms=args.ready_wait_ms,
        screenshot_filename=DEFAULTS.output_naming.screenshot_filename,
        metadata_filename=DEFAULTS.output_naming.metadata_filename,
        review_summary_filename=DEFAULTS.output_naming.review_summary_filename,
        gallery_index_filename=DEFAULTS.output_naming.gallery_index_filename,
    )
    try:
        plan.capture_presets
    except (KeyError, ValueError) as error:
        raise SystemExit(error.args[0]) from error
    return plan


def _planned_variant_slugs(plan: CapturePlan) -> tuple[str, ...]:
    variants = ["default"]
    if plan.capture_dark_mode:
        variants.append("dark")
    if plan.capture_no_javascript:
        variants.append("no-js")
    return tuple(variants)


def _format_selected_preset_outputs(plan: CapturePlan) -> str:
    return ", ".join(
        f"{preset.name} ({', '.join(capture_type.replace('_', '-') for capture_type in preset.output_capture_types)})"
        for preset in plan.capture_presets
    )


def _format_supplemental_artifacts(plan: CapturePlan) -> str:
    selected_presets = plan.capture_presets
    variant_count = len(_planned_variant_slugs(plan))
    supplemental_entries: list[str] = []

    extra_capture_count = sum(
        max(0, len(preset.output_capture_types) - 1) for preset in selected_presets
    ) * variant_count
    if extra_capture_count:
        supplemental_entries.append(f"{extra_capture_count} companion viewport captures")
    if plan.capture_dark_mode:
        supplemental_entries.append(f"{len(selected_presets)} dark-mode artifacts")
    if plan.capture_no_javascript:
        supplemental_entries.append(f"{len(selected_presets)} no-JavaScript artifacts")

    if not supplemental_entries:
        return "(none)"
    return ", ".join(supplemental_entries)


def format_plan_summary(plan: CapturePlan) -> str:
    preset = get_capture_preset(plan.device_preset)
    selected_presets = plan.capture_presets
    selected_primary_presets = ", ".join(
        preset.name
        for preset in selected_presets
        if preset.review_preset_role == "primary"
    )
    capture_mode_label = plan.capture_mode.replace("_", "-")
    variant_slugs = _planned_variant_slugs(plan)
    artifact_count = sum(
        len(preset.output_capture_types) for preset in selected_presets
    ) * len(variant_slugs)
    return "\n".join(
        [
            "Screenshot run configuration:",
            f"URL: {plan.url}",
            f"Output directory: {plan.output_dir}",
            f"Run label: {plan.run_label}",
            f"Run directory: {plan.run_dir}",
            f"Timeout (ms): {plan.timeout_ms}",
            f"Primary preset: {preset.name}",
            f"Primary viewport: {preset.viewport.width}x{preset.viewport.height}",
            f"Selected presets: {', '.join(preset.name for preset in selected_presets)}",
            f"Resolved preset outputs: {_format_selected_preset_outputs(plan)}",
            (
                "Selected primary review presets: "
                f"{selected_primary_presets if selected_primary_presets else '(none)'}"
            ),
            (
                "Excluded presets: "
                f"{', '.join(plan.preset_exclude) if plan.preset_exclude else '(none)'}"
            ),
            f"Capture mode override: {capture_mode_label}",
            f"Variant passes: {', '.join(variant_slugs)}",
            f"Planned artifact count: {artifact_count}",
            f"Supplemental artifacts: {_format_supplemental_artifacts(plan)}",
            f"Locale: {plan.locale}",
            f"Timezone: {plan.timezone_id}",
            f"Dark mode variant: {'enabled' if plan.capture_dark_mode else 'disabled'}",
            f"JavaScript-disabled pass: {'enabled' if plan.capture_no_javascript else 'disabled'}",
            f"Ready selectors: {', '.join(plan.ready_selectors) if plan.ready_selectors else '(none)'}",
            (
                "Ready JS predicate: "
                f"{plan.ready_js_predicate if plan.ready_js_predicate else '(none)'}"
            ),
            f"Ready wait (ms): {plan.ready_wait_ms}",
            f"Wait until: {plan.navigation_wait_until}",
            f"Post-navigation wait (ms): {plan.post_navigation_wait_ms}",
            f"Screenshot filename: {plan.screenshot_filename}",
            f"Metadata filename: {plan.metadata_filename}",
            f"Review summary filename: {plan.review_summary_filename}",
            f"Gallery index filename: {plan.gallery_index_filename}",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    plan = build_capture_plan(argv)
    print(format_plan_summary(plan))
    run_result = run_capture_plan(plan)
    print(format_capture_run_result(run_result))
    return 0 if not run_result.failed_captures else 1


if __name__ == "__main__":
    raise SystemExit(main())
