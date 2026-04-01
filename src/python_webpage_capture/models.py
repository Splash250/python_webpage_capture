"""Shared data models for screenshot planning and execution."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from python_webpage_capture.config import (
    DEFAULTS,
    CaptureModeSelection,
    CapturePreset,
    NavigationWaitUntil,
    resolve_capture_presets,
)


ReadinessOperation = Literal[
    "load-state",
    "selector-visible",
    "js-predicate",
    "fonts-ready",
    "render-settle",
    "wait-timeout",
]


@dataclass(frozen=True)
class ReadinessCheck:
    operation: ReadinessOperation
    timeout_ms: int
    target: str | None = None
    duration_ms: int = 0
    optional: bool = False


@dataclass(frozen=True)
class CapturePlan:
    url: str
    output_dir: Path
    run_label: str
    timeout_ms: int
    device_preset: str
    preset_include: tuple[str, ...]
    preset_exclude: tuple[str, ...]
    capture_mode: CaptureModeSelection
    navigation_wait_until: NavigationWaitUntil
    post_navigation_wait_ms: int
    locale: str
    timezone_id: str
    capture_dark_mode: bool
    capture_no_javascript: bool
    ready_selectors: tuple[str, ...]
    ready_js_predicate: str | None
    ready_wait_ms: int
    screenshot_filename: str
    metadata_filename: str
    review_summary_filename: str
    gallery_index_filename: str

    @property
    def run_dir(self) -> Path:
        run_directory_name = DEFAULTS.output_naming.run_directory_template.format(
            run_label=self.run_label
        )
        return self.output_dir / run_directory_name

    @property
    def capture_presets(self) -> tuple[CapturePreset, ...]:
        return resolve_capture_presets(
            include=self.preset_include,
            exclude=self.preset_exclude,
            capture_mode_selection=self.capture_mode,
        )

    @property
    def readiness_checks(self) -> tuple[ReadinessCheck, ...]:
        wait_budget_ms = max(250, min(self.timeout_ms, 5_000))
        checks: list[ReadinessCheck] = []

        if self.navigation_wait_until == "commit":
            checks.append(
                ReadinessCheck(
                    operation="load-state",
                    target="domcontentloaded",
                    timeout_ms=wait_budget_ms,
                )
            )
        if self.navigation_wait_until != "networkidle":
            checks.append(
                ReadinessCheck(
                    operation="load-state",
                    target="networkidle",
                    timeout_ms=wait_budget_ms,
                    optional=True,
                )
            )

        for selector in self.ready_selectors:
            checks.append(
                ReadinessCheck(
                    operation="selector-visible",
                    target=selector,
                    timeout_ms=self.timeout_ms,
                )
            )
        if self.ready_js_predicate:
            checks.append(
                ReadinessCheck(
                    operation="js-predicate",
                    target=self.ready_js_predicate,
                    timeout_ms=self.timeout_ms,
                )
            )

        checks.append(
            ReadinessCheck(
                operation="fonts-ready",
                timeout_ms=wait_budget_ms,
            )
        )
        checks.append(
            ReadinessCheck(
                operation="render-settle",
                timeout_ms=wait_budget_ms,
            )
        )

        if self.post_navigation_wait_ms > 0:
            checks.append(
                ReadinessCheck(
                    operation="wait-timeout",
                    timeout_ms=0,
                    duration_ms=self.post_navigation_wait_ms,
                )
            )
        if self.ready_wait_ms > 0:
            checks.append(
                ReadinessCheck(
                    operation="wait-timeout",
                    timeout_ms=0,
                    duration_ms=self.ready_wait_ms,
                )
            )

        return tuple(checks)
