"""Playwright-backed capture engine for the screenshot pipeline."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
import json
from pathlib import Path
from typing import Any, Literal

from python_webpage_capture.config import (
    CapturePreset,
)
from python_webpage_capture.models import CapturePlan, ReadinessCheck


def _get_playwright_api() -> tuple[object, type[Exception]]:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    return sync_playwright, PlaywrightError


def _resolve_device_profile(playwright: Any, preset: CapturePreset) -> dict[str, Any]:
    if not preset.device_descriptor:
        return {}

    devices = getattr(playwright, "devices", {})
    return dict(devices.get(preset.device_descriptor, {}))


@dataclass(frozen=True)
class CaptureVariant:
    slug: str
    color_scheme: str
    java_script_enabled: bool


CaptureArtifactType = Literal["viewport", "full_page"]


def _build_capture_variants(plan: CapturePlan) -> tuple[CaptureVariant, ...]:
    variants = [
        CaptureVariant(
            slug="default",
            color_scheme="light",
            java_script_enabled=True,
        )
    ]
    if plan.capture_dark_mode:
        variants.append(
            CaptureVariant(
                slug="dark",
                color_scheme="dark",
                java_script_enabled=True,
            )
        )
    if plan.capture_no_javascript:
        variants.append(
            CaptureVariant(
                slug="no-js",
                color_scheme="light",
                java_script_enabled=False,
            )
        )
    return tuple(variants)


def _build_screenshot_path(
    run_dir: Path,
    preset: CapturePreset,
    variant: CaptureVariant,
    capture_type: CaptureArtifactType,
) -> Path:
    capture_type_slug = capture_type.replace("_", "-")
    return run_dir / f"{preset.artifact_stem}-{variant.slug}-{capture_type_slug}.png"


def _build_context_options(
    playwright: Any,
    plan: CapturePlan,
    preset: CapturePreset,
    variant: CaptureVariant,
) -> dict[str, Any]:
    options = _resolve_device_profile(playwright, preset)
    options.update(
        viewport={
            "width": preset.viewport.width,
            "height": preset.viewport.height,
        },
        locale=plan.locale,
        timezone_id=plan.timezone_id,
        is_mobile=preset.is_mobile,
        has_touch=preset.has_touch,
        color_scheme=variant.color_scheme,
        java_script_enabled=variant.java_script_enabled,
    )
    return options


def _apply_deterministic_page_state(page: Any, variant: CaptureVariant) -> None:
    page.emulate_media(
        color_scheme=variant.color_scheme,
        reduced_motion="reduce",
    )
    page.add_init_script(
        """
        () => {
            const style = document.createElement('style');
            style.setAttribute('data-python-webpage-capture', 'reduce-motion');
            style.textContent = `
                *,
                *::before,
                *::after {
                    animation-delay: 0s !important;
                    animation-duration: 0s !important;
                    animation-iteration-count: 1 !important;
                    scroll-behavior: auto !important;
                    transition-delay: 0s !important;
                    transition-duration: 0s !important;
                    caret-color: transparent !important;
                }
            `;
            document.documentElement.appendChild(style);
        }
        """
    )


def _wait_for_fonts(page: Any, timeout_ms: int) -> None:
    page.wait_for_function(
        "() => !document.fonts || document.fonts.status === 'loaded'",
        timeout=timeout_ms,
    )


def _wait_for_render_settle(page: Any, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        () =>
            new Promise((resolve) => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => resolve(true));
                });
            })
        """,
        timeout=timeout_ms,
    )


def _wait_for_js_predicate(page: Any, predicate: str, timeout_ms: int) -> None:
    page.wait_for_function(
        """
        predicate => {
            const evaluator = new Function(`return Boolean(${predicate});`);
            return evaluator();
        }
        """,
        predicate,
        timeout=timeout_ms,
    )


def _run_readiness_check(page: Any, check: ReadinessCheck) -> None:
    if check.operation == "load-state":
        assert check.target is not None
        try:
            page.wait_for_load_state(check.target, timeout=check.timeout_ms)
        except Exception:
            if check.optional:
                return
            raise
        return

    if check.operation == "selector-visible":
        assert check.target is not None
        page.wait_for_selector(check.target, state="visible", timeout=check.timeout_ms)
        return

    if check.operation == "js-predicate":
        assert check.target is not None
        _wait_for_js_predicate(page, predicate=check.target, timeout_ms=check.timeout_ms)
        return

    if check.operation == "fonts-ready":
        _wait_for_fonts(page, timeout_ms=check.timeout_ms)
        return

    if check.operation == "render-settle":
        _wait_for_render_settle(page, timeout_ms=check.timeout_ms)
        return

    if check.operation == "wait-timeout":
        page.wait_for_timeout(check.duration_ms)
        return

    raise ValueError(f"Unsupported readiness operation: {check.operation}")


def _wait_for_capture_readiness(page: Any, plan: CapturePlan) -> None:
    for check in plan.readiness_checks:
        _run_readiness_check(page, check)


@dataclass(frozen=True)
class CaptureResult:
    preset: CapturePreset
    variant: CaptureVariant
    capture_type: CaptureArtifactType
    screenshot_path: Path
    context_options: dict[str, Any]
    success: bool
    error: str | None = None


@dataclass(frozen=True)
class CaptureLogEntry:
    level: str
    stage: str
    message: str
    preset_slug: str | None = None
    variant_slug: str | None = None
    timestamp: str | None = None


@dataclass(frozen=True)
class CaptureRunResult:
    run_dir: Path
    manifest_path: Path
    review_summary_path: Path
    gallery_index_path: Path
    captured_at: str
    results: tuple[CaptureResult, ...]
    logs: tuple[CaptureLogEntry, ...]
    run_error: str | None = None

    @property
    def successful_captures(self) -> tuple[CaptureResult, ...]:
        return tuple(result for result in self.results if result.success)

    @property
    def failed_captures(self) -> tuple[CaptureResult, ...]:
        return tuple(result for result in self.results if not result.success)

    @property
    def run_status(self) -> str:
        if not self.results:
            return "total-failure"
        if not self.failed_captures:
            return "complete-success"
        if self.successful_captures:
            return "partial-success"
        return "total-failure"


def _log_event(
    logs: list[CaptureLogEntry],
    *,
    level: str,
    stage: str,
    message: str,
    preset_slug: str | None = None,
    variant_slug: str | None = None,
) -> None:
    logs.append(
        CaptureLogEntry(
            level=level,
            stage=stage,
            message=message,
            preset_slug=preset_slug,
            variant_slug=variant_slug,
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
    )


def _build_failed_results_for_run_error(
    plan: CapturePlan,
    presets: tuple[CapturePreset, ...],
    variants: tuple[CaptureVariant, ...],
    run_error: str,
    existing_results: tuple[CaptureResult, ...] = (),
) -> list[CaptureResult]:
    existing_keys = {
        (result.preset.slug, result.variant.slug, result.capture_type)
        for result in existing_results
    }
    results: list[CaptureResult] = []
    for variant in variants:
        for preset in presets:
            for capture_type in preset.output_capture_types:
                if (preset.slug, variant.slug, capture_type) in existing_keys:
                    continue
                results.append(
                    CaptureResult(
                        preset=preset,
                        variant=variant,
                        capture_type=capture_type,
                        screenshot_path=_build_screenshot_path(
                            plan.run_dir,
                            preset,
                            variant,
                            capture_type,
                        ),
                        context_options={
                            "locale": plan.locale,
                            "timezone_id": plan.timezone_id,
                            "is_mobile": preset.is_mobile,
                            "has_touch": preset.has_touch,
                            "color_scheme": variant.color_scheme,
                            "java_script_enabled": variant.java_script_enabled,
                        },
                        success=False,
                        error=run_error,
                    )
                )
    return results


def _build_missing_result_placeholder(
    plan: CapturePlan,
    preset: CapturePreset,
    variant: CaptureVariant,
    capture_type: CaptureArtifactType,
    *,
    reason: str | None = None,
) -> CaptureResult:
    return CaptureResult(
        preset=preset,
        variant=variant,
        capture_type=capture_type,
        screenshot_path=_build_screenshot_path(
            plan.run_dir,
            preset,
            variant,
            capture_type,
        ),
        context_options={
            "locale": plan.locale,
            "timezone_id": plan.timezone_id,
            "is_mobile": preset.is_mobile,
            "has_touch": preset.has_touch,
            "color_scheme": variant.color_scheme,
            "java_script_enabled": variant.java_script_enabled,
        },
        success=False,
        error=reason or "Artifact missing from run results.",
    )


def _complete_results_for_serialization(
    plan: CapturePlan,
    run_result: CaptureRunResult,
) -> tuple[CaptureResult, ...]:
    results_by_key = {
        (result.preset.slug, result.variant.slug, result.capture_type): result
        for result in run_result.results
    }
    completed_results: list[CaptureResult] = []
    missing_reason = (
        "Artifact missing from run results after run abort."
        if run_result.run_error
        else "Artifact missing from run results."
    )
    for variant in _build_capture_variants(plan):
        for preset in plan.capture_presets:
            for capture_type in preset.output_capture_types:
                result = results_by_key.get((preset.slug, variant.slug, capture_type))
                if result is None:
                    result = _build_missing_result_placeholder(
                        plan,
                        preset,
                        variant,
                        capture_type,
                        reason=missing_reason,
                    )
                completed_results.append(result)
    return tuple(completed_results)


def _build_manifest_payload(
    plan: CapturePlan,
    run_result: CaptureRunResult,
) -> dict[str, Any]:
    selected_presets = plan.capture_presets
    serialized_results = _complete_results_for_serialization(plan, run_result)
    succeeded_results = tuple(result for result in serialized_results if result.success)
    failed_results = tuple(result for result in serialized_results if not result.success)
    readiness_checks = [
        {
            "operation": check.operation,
            "target": check.target,
            "timeout_ms": check.timeout_ms,
            "duration_ms": check.duration_ms,
            "optional": check.optional,
        }
        for check in plan.readiness_checks
    ]
    return {
        "url": plan.url,
        "captured_at": run_result.captured_at,
        "run_label": plan.run_label,
        "run_dir": str(run_result.run_dir),
        "manifest_path": str(run_result.manifest_path),
        "review_summary_path": str(run_result.review_summary_path),
        "gallery_index_path": str(run_result.gallery_index_path),
        "locale": plan.locale,
        "timezone_id": plan.timezone_id,
        "timeout_ms": plan.timeout_ms,
        "capture_mode": plan.capture_mode,
        "selected_preset_slugs": [preset.slug for preset in selected_presets],
        "excluded_preset_names": list(plan.preset_exclude),
        "navigation_wait_until": plan.navigation_wait_until,
        "post_navigation_wait_ms": plan.post_navigation_wait_ms,
        "ready_selectors": list(plan.ready_selectors),
        "ready_js_predicate": plan.ready_js_predicate,
        "ready_wait_ms": plan.ready_wait_ms,
        "run_status": run_result.run_status,
        "run_error": run_result.run_error,
        "capture_counts": {
            "total": len(serialized_results),
            "succeeded": len(succeeded_results),
            "failed": len(failed_results),
        },
        "logs": [
            {
                "timestamp": entry.timestamp,
                "level": entry.level,
                "stage": entry.stage,
                "message": entry.message,
                "preset_slug": entry.preset_slug,
                "variant_slug": entry.variant_slug,
            }
            for entry in run_result.logs
        ],
        "captures": [
            {
                "preset": {
                    "name": result.preset.name,
                    "slug": result.preset.slug,
                    "order": result.preset.order,
                    "family": result.preset.family,
                    "capture_mode": result.preset.capture_mode,
                    "review_preset_role": result.preset.review_preset_role,
                    "is_primary_review_preset": result.preset.is_primary_review_preset,
                    "primary_capture_type": result.preset.primary_capture_type,
                    "output_capture_types": list(result.preset.output_capture_types),
                    "include_above_the_fold_capture": (
                        result.preset.include_above_the_fold_capture
                    ),
                    "full_page": result.preset.full_page,
                    "viewport": {
                        "width": result.preset.viewport.width,
                        "height": result.preset.viewport.height,
                    },
                },
                "variant": {
                    "slug": result.variant.slug,
                    "color_scheme": result.variant.color_scheme,
                    "java_script_enabled": result.variant.java_script_enabled,
                },
                "emulation": {
                    "device_descriptor": result.preset.device_descriptor,
                    "viewport": {
                        "width": result.preset.viewport.width,
                        "height": result.preset.viewport.height,
                    },
                    "is_mobile": result.context_options["is_mobile"],
                    "has_touch": result.context_options["has_touch"],
                    "locale": result.context_options["locale"],
                    "timezone_id": result.context_options["timezone_id"],
                    "color_scheme": result.context_options["color_scheme"],
                    "java_script_enabled": result.context_options["java_script_enabled"],
                    "user_agent": result.context_options.get("user_agent"),
                    "device_scale_factor": result.context_options.get(
                        "device_scale_factor"
                    ),
                },
                "capture": {
                    "preset_capture_mode": result.preset.capture_mode,
                    "artifact_capture_type": result.capture_type,
                    "is_primary_capture_type": (
                        result.capture_type == result.preset.primary_capture_type
                    ),
                    "is_full_page": result.capture_type == "full_page",
                    "is_above_the_fold": (
                        result.capture_type == "viewport"
                        and result.preset.primary_capture_type == "full_page"
                    ),
                },
                "review": {
                    "preset_role": result.preset.review_preset_role,
                    "artifact_role": (
                        "primary"
                        if (
                            result.preset.is_primary_review_preset
                            and result.variant.slug == "default"
                            and result.capture_type == result.preset.primary_capture_type
                        )
                        else "supplemental"
                    ),
                    "is_primary_review_preset": result.preset.is_primary_review_preset,
                },
                "timing": {
                    "timeout_ms": plan.timeout_ms,
                    "navigation_wait_until": plan.navigation_wait_until,
                    "post_navigation_wait_ms": plan.post_navigation_wait_ms,
                    "ready_wait_ms": plan.ready_wait_ms,
                    "readiness_checks": readiness_checks,
                },
                "output": {
                    "capture_type": result.capture_type,
                    "path": str(result.screenshot_path),
                    "filename": result.screenshot_path.name,
                    "exists": result.screenshot_path.exists(),
                    "full_page": result.capture_type == "full_page",
                },
                "status": "succeeded" if result.success else "failed",
                "error": result.error,
            }
            for result in serialized_results
        ],
    }


def _relative_to_run_dir(path: Path, run_dir: Path) -> str:
    return str(path.relative_to(run_dir))


def _build_review_summary(plan: CapturePlan, run_result: CaptureRunResult) -> str:
    created_date = run_result.captured_at.split("T", 1)[0]
    selected_presets = plan.capture_presets
    serialized_results = _complete_results_for_serialization(plan, run_result)
    successful_results = tuple(result for result in serialized_results if result.success)
    failed_results = tuple(result for result in serialized_results if not result.success)
    status_labels = {
        "complete-success": "Complete success",
        "partial-success": "Partial success",
        "total-failure": "Total failure",
    }
    variant_labels = {
        "default": "Default",
        "dark": "Dark mode",
        "no-js": "JavaScript disabled",
    }
    enabled_variants: list[str] = []
    ordered_variant_slugs: list[str] = []
    seen_variants: set[str] = set()
    for result in serialized_results:
        if result.variant.slug in seen_variants:
            continue
        seen_variants.add(result.variant.slug)
        ordered_variant_slugs.append(result.variant.slug)
        enabled_variants.append(
            variant_labels.get(result.variant.slug, result.variant.slug)
        )

    grouped_results: dict[tuple[str, str], list[CaptureResult]] = {}
    for result in serialized_results:
        grouped_results.setdefault(
            (result.preset.slug, result.variant.slug),
            [],
        ).append(result)

    role_labels = {
        "primary": "Primary review presets",
        "supplemental": "Supplemental review presets",
    }

    def _format_artifact_line(result: CaptureResult) -> str:
        capture_label = result.capture_type.replace("_", " ")
        line = (
            f"- {capture_label.title()}: "
            f"`{_relative_to_run_dir(result.screenshot_path, run_result.run_dir)}`"
        )
        if result.error:
            line = f"{line} - failed: {result.error}"
        return line

    lines = [
        "---",
        "type: report",
        f"title: Review Bundle Summary {plan.run_label}",
        f"created: {created_date}",
        "tags:",
        "  - review-bundle",
        "  - screenshots",
        "related:",
        "  - '[[capture-plan]]'",
        "---",
        "",
        "# Screenshot Review Bundle",
        "",
        "## Run Metadata",
        f"- URL: `{plan.url}`",
        f"- Run label: `{plan.run_label}`",
        f"- Capture timestamp: `{run_result.captured_at}`",
        f"- Manifest: `{_relative_to_run_dir(run_result.manifest_path, run_result.run_dir)}`",
        f"- Run status: `{status_labels[run_result.run_status]}`",
        f"- Capture counts: `{len(successful_results)} succeeded / {len(failed_results)} failed / {len(serialized_results)} total`",
        (
            "- Selected presets: "
            + ", ".join(f"`{preset.name}`" for preset in selected_presets)
        ),
        f"- Capture mode override: `{plan.capture_mode.replace('_', '-')}`",
        f"- Enabled variants: {', '.join(enabled_variants)}",
        (
            "- Selected primary review presets: "
            + ", ".join(
                f"`{preset.name}`"
                for preset in selected_presets
                if preset.review_preset_role == "primary"
            )
        ),
        "",
    ]
    if run_result.run_error:
        lines.extend(
            [
                "## Run Error",
                f"- `{run_result.run_error}`",
                "",
            ]
        )

    lines.extend(
        [
        "## Reviewer Guidance",
        "Use this bundle for design critique. Comment on:",
        "- hierarchy and scan order",
        "- spacing and alignment consistency",
        "- overall visual balance",
        "- CTA prominence and clarity",
        "- text density and readability",
        "- awkward wrapping or truncation",
        "- overflow, clipping, or layout breakage",
        "- mobile and tablet adaptation compared with desktop",
        "",
        "## Preset Taxonomy",
        ]
    )

    for preset in selected_presets:
        if preset.review_preset_role != "primary":
            continue
        lines.append(
            f"- Primary: `{preset.name}` (`{preset.family}`, `{preset.viewport.width}x{preset.viewport.height}`, `{preset.capture_mode}`)"
        )

    for preset in selected_presets:
        if preset.review_preset_role != "supplemental":
            continue
        lines.append(
            f"- Supplemental: `{preset.name}` (`{preset.family}`, `{preset.viewport.width}x{preset.viewport.height}`, `{preset.capture_mode}`)"
        )

    lines.extend(
        [
            "",
            "## Review Artifacts",
        ]
    )

    for review_role in ("primary", "supplemental"):
        presets_for_role = [
            preset
            for preset in selected_presets
            if preset.review_preset_role == review_role
        ]
        if not presets_for_role:
            continue

        lines.extend(
            [
                "",
                f"### {role_labels[review_role]}",
            ]
        )
        for preset in presets_for_role:
            lines.extend(
                [
                    (
                        f"- `{preset.name}` "
                        f"(`{preset.family}`, `{preset.viewport.width}x{preset.viewport.height}`, "
                        f"`{preset.capture_mode}`)"
                    ),
                ]
            )
            for variant_slug in ordered_variant_slugs:
                results = grouped_results.get((preset.slug, variant_slug), [])
                if not results:
                    continue
                lines.append(f"  - Variant `{variant_slug}`")
                for result in results:
                    lines.append(f"    {_format_artifact_line(result)}")

    if failed_results:
        lines.extend(
            [
                "",
                "## Failure Reasons",
            ]
        )
        for result in failed_results:
            lines.append(
                f"- `{result.preset.name}` / `{result.variant.slug}` / `{result.capture_type}`: {result.error}"
            )

    if run_result.logs:
        lines.extend(
            [
                "",
                "## Run Log",
            ]
        )
        for entry in run_result.logs:
            scope = []
            if entry.preset_slug:
                scope.append(entry.preset_slug)
            if entry.variant_slug:
                scope.append(entry.variant_slug)
            scope_label = f" [{' / '.join(scope)}]" if scope else ""
            lines.append(
                f"- `{entry.timestamp}` `{entry.level}` `{entry.stage}`{scope_label}: {entry.message}"
            )

    return "\n".join(lines) + "\n"


def _write_manifest(plan: CapturePlan, run_result: CaptureRunResult) -> None:
    manifest_payload = _build_manifest_payload(plan, run_result)
    run_result.manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_review_summary(plan: CapturePlan, run_result: CaptureRunResult) -> None:
    run_result.review_summary_path.write_text(
        _build_review_summary(plan, run_result),
        encoding="utf-8",
    )


def _build_gallery_index(plan: CapturePlan, run_result: CaptureRunResult) -> str:
    serialized_results = _complete_results_for_serialization(plan, run_result)
    successful_results = tuple(result for result in serialized_results if result.success)
    failed_results = tuple(result for result in serialized_results if not result.success)
    status_labels = {
        "complete-success": "Complete success",
        "partial-success": "Partial success",
        "total-failure": "Total failure",
    }
    review_role_sections = {
        "primary": "Primary review presets",
        "supplemental": "Supplemental review presets",
    }
    artifact_role_labels = {
        "primary": "Primary artifact",
        "supplemental": "Supplemental artifact",
    }
    grouped_results: dict[
        str,
        dict[str, dict[str, list[CaptureResult]]],
    ] = {
        "primary": defaultdict(lambda: defaultdict(list)),
        "supplemental": defaultdict(lambda: defaultdict(list)),
    }

    for result in serialized_results:
        grouped_results[result.preset.review_preset_role][result.preset.slug][
            result.variant.slug
        ].append(result)

    preset_sections: list[str] = []
    for review_role in ("primary", "supplemental"):
        presets_markup: list[str] = []
        for preset in plan.capture_presets:
            if preset.review_preset_role != review_role:
                continue

            variant_groups = grouped_results[review_role].get(preset.slug, {})
            variant_markup: list[str] = []
            for variant_slug, variant_results in variant_groups.items():
                cards: list[str] = []
                for result in variant_results:
                    title = (
                        f"{result.preset.name} / {result.variant.slug} / "
                        f"{result.capture_type}"
                    )
                    viewport = (
                        f"{result.preset.viewport.width}x{result.preset.viewport.height}"
                    )
                    artifact_role = (
                        "primary"
                        if (
                            result.preset.is_primary_review_preset
                            and result.variant.slug == "default"
                            and result.capture_type == result.preset.primary_capture_type
                        )
                        else "supplemental"
                    )
                    card_classes = [
                        "capture-card",
                        (
                            "capture-card--success"
                            if result.success
                            else "capture-card--failed"
                        ),
                        f"capture-card--{artifact_role}",
                    ]
                    status_label = "Succeeded" if result.success else "Failed"
                    image_markup = (
                        f'<a class="capture-card__image-link" href="{escape(_relative_to_run_dir(result.screenshot_path, run_result.run_dir), quote=True)}">'
                        f'<img src="{escape(_relative_to_run_dir(result.screenshot_path, run_result.run_dir), quote=True)}" '
                        f'alt="{escape(title, quote=True)} screenshot preview" loading="lazy"></a>'
                        if result.success
                        else '<div class="capture-card__placeholder">Screenshot unavailable</div>'
                    )
                    error_markup = (
                        f'<p class="capture-card__error">{escape(result.error or "")}</p>'
                        if result.error
                        else ""
                    )
                    cards.append(
                        "\n".join(
                            [
                                f'<article class="{" ".join(card_classes)}">',
                                f'<p class="capture-card__artifact-role">{escape(artifact_role_labels[artifact_role])}</p>',
                                f'<h4>{escape(title)}</h4>',
                                '<dl class="capture-card__meta">',
                                f"<div><dt>Viewport</dt><dd>{escape(viewport)}</dd></div>",
                                f"<div><dt>Family</dt><dd>{escape(result.preset.family)}</dd></div>",
                                f"<div><dt>Review Role</dt><dd>{escape(result.preset.review_preset_role)}</dd></div>",
                                f"<div><dt>Capture Type</dt><dd>{escape(result.capture_type)}</dd></div>",
                                f"<div><dt>Status</dt><dd>{status_label}</dd></div>",
                                f"<div><dt>File</dt><dd>{escape(_relative_to_run_dir(result.screenshot_path, run_result.run_dir))}</dd></div>",
                                "</dl>",
                                image_markup,
                                error_markup,
                                "</article>",
                            ]
                        )
                    )

                variant_markup.append(
                    "\n".join(
                        [
                            '<section class="variant-group">',
                            f"<h3>Variant: {escape(variant_slug)}</h3>",
                            '<div class="capture-grid">',
                            *[f"  {card}" for card in cards],
                            "</div>",
                            "</section>",
                        ]
                    )
                )

            preset_classes = [
                "preset-panel",
                f"preset-panel--{review_role}",
            ]
            presets_markup.append(
                "\n".join(
                    [
                        f'<article class="{" ".join(preset_classes)}">',
                        '<div class="preset-panel__header">',
                        (
                            f"<div><h3>{escape(preset.name)}</h3>"
                            f'<p class="preset-panel__subtitle">{escape(preset.slug)} | '
                            f"{escape(preset.family)} | "
                            f"{preset.viewport.width}x{preset.viewport.height}</p></div>"
                        ),
                        (
                            '<span class="preset-panel__role-badge">'
                            f"{escape(artifact_role_labels[review_role].replace(' artifact', ' preset'))}"
                            "</span>"
                        ),
                        "</div>",
                        '<dl class="preset-panel__meta">',
                        f"<div><dt>Default Capture</dt><dd>{escape(preset.primary_capture_type)}</dd></div>",
                        f"<div><dt>Outputs</dt><dd>{escape(', '.join(preset.output_capture_types))}</dd></div>",
                        f"<div><dt>Capture Mode</dt><dd>{escape(preset.capture_mode)}</dd></div>",
                        (
                            "<div><dt>Companion Capture</dt><dd>"
                            + (
                                "above-the-fold viewport included"
                                if preset.include_above_the_fold_capture
                                else "none"
                            )
                            + "</dd></div>"
                        ),
                        "</dl>",
                        *variant_markup,
                        "</article>",
                    ]
                )
            )

        if presets_markup:
            preset_sections.append(
                "\n".join(
                    [
                        f'<section class="review-group review-group--{review_role}" aria-label="{escape(review_role_sections[review_role], quote=True)}">',
                        f"<h2>{escape(review_role_sections[review_role])}</h2>",
                        '<div class="preset-stack">',
                        *[f"  {preset_markup}" for preset_markup in presets_markup],
                        "</div>",
                        "</section>",
                    ]
                )
            )

    enabled_variants = ", ".join(
        dict.fromkeys(result.variant.slug for result in serialized_results)
    )
    return "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>Review Gallery {escape(plan.run_label)}</title>",
            "  <style>",
            "    :root { color-scheme: light; font-family: Georgia, 'Times New Roman', serif; background: linear-gradient(180deg, #f8f5ef 0%, #efe7dc 100%); color: #1f2933; }",
            "    * { box-sizing: border-box; }",
            "    body { margin: 0; padding: 24px; }",
            "    main { max-width: 1440px; margin: 0 auto; }",
            "    h1 { margin-bottom: 8px; font-size: 2rem; }",
            "    p { line-height: 1.5; }",
            "    .run-meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 24px 0 32px; }",
            "    .run-meta div, .preset-panel, .capture-card { background: rgba(255, 253, 250, 0.92); border: 1px solid #d8d2c4; border-radius: 16px; box-shadow: 0 10px 30px rgba(31, 41, 51, 0.08); }",
            "    .run-meta div { padding: 14px 16px; }",
            "    .run-meta dt, .preset-panel dt, .capture-card dt { font-size: 0.75rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; color: #52606d; }",
            "    .run-meta dd, .preset-panel dd, .capture-card dd { margin: 4px 0 0; }",
            "    .review-group { margin-top: 32px; }",
            "    .review-group h2 { margin-bottom: 16px; }",
            "    .preset-stack { display: grid; gap: 20px; }",
            "    .preset-panel { padding: 20px; }",
            "    .preset-panel--primary { border-color: #7f5f3a; }",
            "    .preset-panel--supplemental { border-style: dashed; }",
            "    .preset-panel__header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 16px; }",
            "    .preset-panel__header h3 { margin: 0 0 4px; font-size: 1.35rem; }",
            "    .preset-panel__subtitle { margin: 0; color: #52606d; }",
            "    .preset-panel__role-badge, .capture-card__artifact-role { display: inline-flex; align-items: center; border-radius: 999px; font-size: 0.78rem; font-weight: 700; letter-spacing: 0.04em; text-transform: uppercase; }",
            "    .preset-panel__role-badge { padding: 8px 12px; background: #eadbc8; color: #5d4120; }",
            "    .preset-panel--supplemental .preset-panel__role-badge { background: #ece6dc; color: #5f6c7b; }",
            "    .preset-panel__meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 0 0 18px; }",
            "    .variant-group + .variant-group { margin-top: 18px; }",
            "    .variant-group h3 { margin: 0 0 12px; font-size: 1rem; }",
            "    .capture-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 18px; }",
            "    .capture-card { padding: 18px; }",
            "    .capture-card--primary { border-color: #bf8b30; background: #fff8ee; }",
            "    .capture-card--supplemental { border-color: #cbd2d9; }",
            "    .capture-card h4 { margin-top: 0; margin-bottom: 12px; font-size: 1.05rem; }",
            "    .capture-card__artifact-role { margin: 0 0 10px; padding: 6px 10px; background: #f4d7a1; color: #6f4218; }",
            "    .capture-card--supplemental .capture-card__artifact-role { background: #e8edf2; color: #52606d; }",
            "    .capture-card__meta { display: grid; gap: 10px; margin: 0 0 16px; }",
            "    .capture-card__meta div { min-width: 0; }",
            "    .capture-card__meta dd { word-break: break-word; }",
            "    .capture-card__image-link, .capture-card__placeholder { display: block; border-radius: 12px; overflow: hidden; background: #ebe6dc; }",
            "    .capture-card img { display: block; width: 100%; height: auto; }",
            "    .capture-card__placeholder { padding: 48px 16px; text-align: center; color: #7b8794; font-weight: 700; }",
            "    .capture-card__error { margin-bottom: 0; color: #b42318; font-weight: 700; }",
            "    .capture-card--failed { border-color: #f0b3ad; }",
            "    @media (max-width: 640px) { body { padding: 16px; } }",
            "  </style>",
            "</head>",
            "<body>",
            "  <main>",
            f"    <h1>Review Gallery: {escape(plan.run_label)}</h1>",
            f"    <p>URL: <a href=\"{escape(plan.url, quote=True)}\">{escape(plan.url)}</a><br>Captured at: {escape(run_result.captured_at)}<br>Variants: {escape(enabled_variants)}</p>",
            '    <section class="run-meta" aria-label="Run metadata">',
            f"      <div><dt>Run Status</dt><dd>{escape(status_labels[run_result.run_status])}</dd></div>",
            f"      <div><dt>Manifest</dt><dd>{escape(_relative_to_run_dir(run_result.manifest_path, run_result.run_dir))}</dd></div>",
            f"      <div><dt>Review Summary</dt><dd>{escape(_relative_to_run_dir(run_result.review_summary_path, run_result.run_dir))}</dd></div>",
            f"      <div><dt>Successful Captures</dt><dd>{len(successful_results)}</dd></div>",
            f"      <div><dt>Failed Captures</dt><dd>{len(failed_results)}</dd></div>",
            "    </section>",
            (
                f'    <p class="capture-card__error"><strong>Run error:</strong> {escape(run_result.run_error)}</p>'
                if run_result.run_error
                else ""
            ),
            *[f"    {section}" for section in preset_sections],
            "  </main>",
            "</body>",
            "</html>",
            "",
        ]
    )


def _write_gallery_index(plan: CapturePlan, run_result: CaptureRunResult) -> None:
    run_result.gallery_index_path.write_text(
        _build_gallery_index(plan, run_result),
        encoding="utf-8",
    )


def run_capture_plan(plan: CapturePlan) -> CaptureRunResult:
    selected_presets = plan.capture_presets
    plan.run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = plan.run_dir / plan.metadata_filename
    review_summary_path = plan.run_dir / plan.review_summary_filename
    gallery_index_path = plan.run_dir / plan.gallery_index_filename
    captured_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    results: list[CaptureResult] = []
    logs: list[CaptureLogEntry] = []
    variants = _build_capture_variants(plan)
    run_error: str | None = None
    _log_event(
        logs,
        level="info",
        stage="run-started",
        message=f"Starting capture run for {plan.url}",
    )

    try:
        sync_playwright, PlaywrightError = _get_playwright_api()
        with sync_playwright() as playwright:
            _log_event(
                logs,
                level="info",
                stage="playwright-ready",
                message="Playwright context initialized",
            )
            browser = playwright.chromium.launch()
            _log_event(
                logs,
                level="info",
                stage="browser-launched",
                message="Chromium browser launched",
            )
            try:
                for variant in variants:
                    _log_event(
                        logs,
                        level="info",
                        stage="variant-started",
                        message=f"Starting variant {variant.slug}",
                        variant_slug=variant.slug,
                    )
                    for preset in selected_presets:
                        context_options = _build_context_options(
                            playwright, plan, preset, variant
                        )
                        _log_event(
                            logs,
                            level="info",
                            stage="capture-started",
                            message=f"Capturing preset {preset.slug}",
                            preset_slug=preset.slug,
                            variant_slug=variant.slug,
                        )
                        try:
                            context = browser.new_context(**context_options)
                            try:
                                page = context.new_page()
                                _apply_deterministic_page_state(page, variant)
                                page.goto(
                                    plan.url,
                                    wait_until=plan.navigation_wait_until,
                                    timeout=plan.timeout_ms,
                                )
                                _wait_for_capture_readiness(page, plan)
                                for capture_type in preset.output_capture_types:
                                    screenshot_path = _build_screenshot_path(
                                        plan.run_dir,
                                        preset,
                                        variant,
                                        capture_type,
                                    )
                                    try:
                                        page.screenshot(
                                            path=str(screenshot_path),
                                            full_page=capture_type == "full_page",
                                        )
                                    except PlaywrightError as error:
                                        results.append(
                                            CaptureResult(
                                                preset=preset,
                                                variant=variant,
                                                capture_type=capture_type,
                                                screenshot_path=screenshot_path,
                                                context_options=context_options,
                                                success=False,
                                                error=str(error),
                                            )
                                        )
                                        _log_event(
                                            logs,
                                            level="error",
                                            stage="capture-failed",
                                            message=(
                                                f"{capture_type} capture failed for "
                                                f"{preset.slug}: {error}"
                                            ),
                                            preset_slug=preset.slug,
                                            variant_slug=variant.slug,
                                        )
                                        continue

                                    results.append(
                                        CaptureResult(
                                            preset=preset,
                                            variant=variant,
                                            capture_type=capture_type,
                                            screenshot_path=screenshot_path,
                                            context_options=context_options,
                                            success=True,
                                        )
                                    )
                                    _log_event(
                                        logs,
                                        level="info",
                                        stage="capture-succeeded",
                                        message=(
                                            f"Saved {screenshot_path.name} "
                                            f"({capture_type})"
                                        ),
                                        preset_slug=preset.slug,
                                        variant_slug=variant.slug,
                                    )
                            finally:
                                context.close()
                        except PlaywrightError as error:
                            for capture_type in preset.output_capture_types:
                                screenshot_path = _build_screenshot_path(
                                    plan.run_dir,
                                    preset,
                                    variant,
                                    capture_type,
                                )
                                results.append(
                                    CaptureResult(
                                        preset=preset,
                                        variant=variant,
                                        capture_type=capture_type,
                                        screenshot_path=screenshot_path,
                                        context_options=context_options,
                                        success=False,
                                        error=str(error),
                                    )
                                )
                                _log_event(
                                    logs,
                                    level="error",
                                    stage="capture-failed",
                                    message=(
                                        f"{capture_type} capture failed for "
                                        f"{preset.slug}: {error}"
                                    ),
                                    preset_slug=preset.slug,
                                    variant_slug=variant.slug,
                                )
                            continue
            finally:
                browser.close()
                _log_event(
                    logs,
                    level="info",
                    stage="browser-closed",
                    message="Chromium browser closed",
                )
    except Exception as error:
        run_error = f"Run aborted before completion: {error}"
        _log_event(
            logs,
            level="error",
            stage="run-aborted",
            message=run_error,
        )
        results.extend(
            _build_failed_results_for_run_error(
                plan,
                selected_presets,
                variants,
                run_error,
                existing_results=tuple(results),
            )
        )

    run_result = CaptureRunResult(
        run_dir=plan.run_dir,
        manifest_path=manifest_path,
        review_summary_path=review_summary_path,
        gallery_index_path=gallery_index_path,
        captured_at=captured_at,
        results=tuple(results),
        logs=tuple(logs),
        run_error=run_error,
    )
    _log_event(
        logs,
        level="info",
        stage="run-finished",
        message=(
            f"Run finished with status {run_result.run_status}: "
            f"{len(run_result.successful_captures)} succeeded, "
            f"{len(run_result.failed_captures)} failed"
        ),
    )
    run_result = CaptureRunResult(
        run_dir=run_result.run_dir,
        manifest_path=run_result.manifest_path,
        review_summary_path=run_result.review_summary_path,
        gallery_index_path=run_result.gallery_index_path,
        captured_at=run_result.captured_at,
        results=run_result.results,
        logs=tuple(logs),
        run_error=run_result.run_error,
    )
    _write_manifest(plan, run_result)
    _write_review_summary(plan, run_result)
    _write_gallery_index(plan, run_result)
    return run_result


def format_capture_run_result(run_result: CaptureRunResult) -> str:
    status_headlines = {
        "complete-success": "Complete success: every planned artifact was captured.",
        "partial-success": (
            "Partial success: some artifacts were captured, and some failed. "
            "The review bundle was still written."
        ),
        "total-failure": (
            "Total failure: no artifacts were captured successfully. "
            "Failure details are recorded in the review bundle."
        ),
    }
    run_status = str(run_result.run_status)
    lines = [
        status_headlines.get(run_status, f"Run finished with status: {run_status}"),
        f"Saved captures to: {run_result.run_dir}",
        f"Run status: {run_status}",
        (
            "Capture counts: "
            f"{len(run_result.successful_captures)} succeeded / "
            f"{len(run_result.failed_captures)} failed / "
            f"{len(run_result.results)} total"
        ),
        f"Manifest: {run_result.manifest_path}",
        f"Review summary: {run_result.review_summary_path}",
        f"Gallery index: {run_result.gallery_index_path}",
    ]
    if run_result.run_error:
        lines.append(f"Run error: {run_result.run_error}")
    if run_result.failed_captures:
        lines.append("Failed artifacts:")
        for result in run_result.failed_captures:
            if not isinstance(result, CaptureResult):
                lines.append(f"- {result}")
                continue
            details = str(result.screenshot_path)
            if result.error:
                details = f"{details} ({result.error})"
            lines.append(
                f"- {result.screenshot_path.name} [{result.preset.slug} / {result.variant.slug} / {result.capture_type}] -> {details}"
            )
    else:
        lines.append("Failed artifacts: (none)")
    return "\n".join(lines)
