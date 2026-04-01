from dataclasses import replace
import functools
import json
import runpy
import shutil
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import tomllib

import python_webpage_capture
from python_webpage_capture.capture import (
    CaptureLogEntry,
    CaptureResult,
    CaptureRunResult,
    CaptureVariant,
    _build_capture_variants,
    _write_gallery_index,
    _write_manifest,
    _write_review_summary,
    format_capture_run_result,
    run_capture_plan,
)
from python_webpage_capture.cli import (
    REPOSITORY_ROOT,
    build_capture_plan,
    format_plan_summary,
    main,
    resolve_output_dir,
)
from python_webpage_capture.config import (
    CAPTURE_MATRIX,
    DEFAULTS,
    CapturePreset,
    Viewport,
    apply_capture_mode_selection,
    get_capture_preset,
    get_review_presets,
    resolve_capture_presets,
)


class PackageSmokeTest(unittest.TestCase):
    def test_version_is_defined(self) -> None:
        self.assertEqual(python_webpage_capture.__version__, "0.1.0")

    def test_pyproject_declares_playwright_dependency(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertIn("playwright>=1.53,<2", pyproject["project"]["dependencies"])

    def test_readme_documents_browser_bootstrap(self) -> None:
        readme_path = Path(__file__).resolve().parents[1] / "README.md"
        readme = readme_path.read_text(encoding="utf-8")

        self.assertIn("python -m pip install -e .", readme)
        self.assertIn("python -m playwright install chromium", readme)
        self.assertIn("python-webpage-capture `", readme)

    def test_readme_includes_validation_checklist_with_real_artifact_names(self) -> None:
        readme_path = Path(__file__).resolve().parents[1] / "README.md"
        readme = readme_path.read_text(encoding="utf-8")

        self.assertIn("## Validation Checklist", readme)
        self.assertIn("capture-plan.json", readme)
        self.assertIn("review-summary.md", readme)
        self.assertIn("review-gallery.html", readme)
        self.assertIn(
            "02-standard-desktop-1440x900-default-full-page.png",
            readme,
        )
        self.assertIn("Capture mode override", readme)
        self.assertIn("Variant passes", readme)

    def test_pyproject_declares_console_entrypoint(self) -> None:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

        self.assertEqual(
            pyproject["project"]["scripts"]["python-webpage-capture"],
            "python_webpage_capture.cli:main",
        )

    def test_module_entrypoint_invokes_cli_main(self) -> None:
        with patch("python_webpage_capture.cli.main", return_value=0) as cli_main:
            with self.assertRaises(SystemExit) as exit_info:
                runpy.run_module("python_webpage_capture", run_name="__main__")

        self.assertEqual(exit_info.exception.code, 0)
        cli_main.assert_called_once_with()


class CliPlanTest(unittest.TestCase):
    def test_resolve_output_dir_accepts_absolute_path_under_repo(self) -> None:
        absolute_runs = (REPOSITORY_ROOT / "runs").resolve()

        self.assertEqual(resolve_output_dir(str(absolute_runs)), absolute_runs)

    def test_build_capture_plan_accepts_relative_output_dir_under_repo(self) -> None:
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                "runs",
                "--run-label",
                "smoke",
                "--timeout-ms",
                "15000",
            ]
        )

        self.assertEqual(plan.url, "http://localhost:8080/")
        self.assertEqual(plan.output_dir, REPOSITORY_ROOT / "runs")
        self.assertEqual(plan.run_dir, REPOSITORY_ROOT / "runs" / "smoke")
        self.assertEqual(plan.timeout_ms, 15000)
        self.assertEqual(plan.device_preset, DEFAULTS.primary_preset)
        self.assertEqual(plan.preset_include, ())
        self.assertEqual(plan.preset_exclude, ())
        self.assertEqual(plan.capture_mode, "default")
        self.assertEqual(plan.navigation_wait_until, DEFAULTS.waits.navigation_wait_until)
        self.assertEqual(
            plan.post_navigation_wait_ms, DEFAULTS.waits.post_navigation_wait_ms
        )
        self.assertEqual(plan.locale, DEFAULTS.locale)
        self.assertEqual(plan.timezone_id, DEFAULTS.timezone_id)
        self.assertFalse(plan.capture_dark_mode)
        self.assertFalse(plan.capture_no_javascript)
        self.assertEqual(plan.ready_selectors, ())
        self.assertIsNone(plan.ready_js_predicate)
        self.assertEqual(plan.ready_wait_ms, 0)
        self.assertEqual(
            [
                (check.operation, check.target, check.timeout_ms, check.duration_ms, check.optional)
                for check in plan.readiness_checks
            ],
            [
                ("load-state", "networkidle", 5000, 0, True),
                ("fonts-ready", None, 5000, 0, False),
                ("render-settle", None, 5000, 0, False),
            ],
        )
        self.assertEqual(
            plan.screenshot_filename, DEFAULTS.output_naming.screenshot_filename
        )
        self.assertEqual(plan.metadata_filename, DEFAULTS.output_naming.metadata_filename)
        self.assertEqual(
            plan.review_summary_filename,
            DEFAULTS.output_naming.review_summary_filename,
        )
        self.assertEqual(
            plan.gallery_index_filename,
            DEFAULTS.output_naming.gallery_index_filename,
        )

    def test_build_capture_plan_uses_config_defaults_and_accepts_browser_overrides(self) -> None:
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                "runs",
                "--run-label",
                "smoke",
                "--locale",
                "fr-FR",
                "--timezone-id",
                "Europe/Paris",
                "--preset",
                "standard-desktop",
                "--preset",
                "mobile-portrait",
                "--exclude-preset",
                "standard-desktop",
                "--capture-mode",
                "both",
                "--navigation-wait-until",
                "domcontentloaded",
                "--post-navigation-wait-ms",
                "1250",
                "--dark-mode",
                "--disable-javascript-pass",
                "--ready-selector",
                "#app-shell",
                "--ready-selector",
                "main hero",
                "--ready-js-predicate",
                "window.__APP_READY__ === true",
                "--ready-wait-ms",
                "750",
            ]
        )

        self.assertEqual(plan.timeout_ms, DEFAULTS.timeout_ms)
        self.assertEqual(plan.preset_include, ("standard-desktop", "mobile-portrait"))
        self.assertEqual(plan.preset_exclude, ("standard-desktop",))
        self.assertEqual(plan.capture_mode, "both")
        self.assertEqual(plan.navigation_wait_until, "domcontentloaded")
        self.assertEqual(plan.post_navigation_wait_ms, 1250)
        self.assertEqual(plan.locale, "fr-FR")
        self.assertEqual(plan.timezone_id, "Europe/Paris")
        self.assertTrue(plan.capture_dark_mode)
        self.assertTrue(plan.capture_no_javascript)
        self.assertEqual(plan.ready_selectors, ("#app-shell", "main hero"))
        self.assertEqual(plan.ready_js_predicate, "window.__APP_READY__ === true")
        self.assertEqual(plan.ready_wait_ms, 750)
        self.assertEqual(
            [
                (check.operation, check.target, check.timeout_ms, check.duration_ms, check.optional)
                for check in plan.readiness_checks
            ],
            [
                ("load-state", "networkidle", 5000, 0, True),
                ("selector-visible", "#app-shell", DEFAULTS.timeout_ms, 0, False),
                ("selector-visible", "main hero", DEFAULTS.timeout_ms, 0, False),
                (
                    "js-predicate",
                    "window.__APP_READY__ === true",
                    DEFAULTS.timeout_ms,
                    0,
                    False,
                ),
                ("fonts-ready", None, 5000, 0, False),
                ("render-settle", None, 5000, 0, False),
                ("wait-timeout", None, 0, 1250, False),
                ("wait-timeout", None, 0, 750, False),
            ],
        )
        self.assertEqual([preset.slug for preset in plan.capture_presets], ["mobile-portrait"])

    def test_build_capture_plan_rejects_negative_post_navigation_wait(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    "runs",
                    "--run-label",
                    "smoke",
                    "--post-navigation-wait-ms",
                    "-1",
                ]
            )

    def test_build_capture_plan_rejects_unknown_selected_preset(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    "runs",
                    "--run-label",
                    "smoke",
                    "--preset",
                    "watch",
                ]
            )

    def test_build_capture_plan_rejects_output_dir_outside_repo(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    "..\\outside",
                    "--run-label",
                    "smoke",
                    "--timeout-ms",
                    "15000",
                ]
            )

    def test_build_capture_plan_rejects_invalid_url(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "localhost:8080",
                    "--output-dir",
                    "runs",
                    "--run-label",
                    "smoke",
                    "--timeout-ms",
                    "15000",
                ]
            )

    def test_build_capture_plan_rejects_non_positive_timeout(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    "runs",
                    "--run-label",
                    "smoke",
                    "--timeout-ms",
                    "0",
                ]
            )

    def test_build_capture_plan_rejects_negative_ready_wait(self) -> None:
        with self.assertRaises(SystemExit):
            build_capture_plan(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    "runs",
                    "--run-label",
                    "smoke",
                    "--ready-wait-ms",
                    "-1",
                ]
            )

    def test_format_plan_summary_includes_concise_run_details(self) -> None:
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                "runs",
                "--run-label",
                "smoke",
                "--timeout-ms",
                "15000",
            ]
        )

        summary = format_plan_summary(plan)

        self.assertIn("Screenshot run configuration:", summary)
        self.assertIn("URL: http://localhost:8080/", summary)
        self.assertIn("Run directory:", summary)
        self.assertIn(f"Primary preset: {DEFAULTS.primary_preset}", summary)
        self.assertIn("Primary viewport: 1440x900", summary)
        self.assertIn(
            "Selected presets: Large Desktop, Standard Desktop, Laptop, Tablet Portrait, Tablet Landscape, Mobile Portrait, Mobile Landscape",
            summary,
        )
        self.assertIn(
            "Resolved preset outputs: Large Desktop (full-page), Standard Desktop (full-page), Laptop (full-page), Tablet Portrait (full-page), Tablet Landscape (full-page), Mobile Portrait (viewport), Mobile Landscape (viewport)",
            summary,
        )
        self.assertIn(
            "Selected primary review presets: Standard Desktop, Tablet Portrait, Mobile Portrait",
            summary,
        )
        self.assertIn("Excluded presets: (none)", summary)
        self.assertIn("Capture mode override: default", summary)
        self.assertIn("Variant passes: default", summary)
        self.assertIn("Planned artifact count: 7", summary)
        self.assertIn("Supplemental artifacts: (none)", summary)
        self.assertIn("Dark mode variant: disabled", summary)
        self.assertIn("JavaScript-disabled pass: disabled", summary)
        self.assertIn("Ready selectors: (none)", summary)
        self.assertIn("Ready JS predicate: (none)", summary)
        self.assertIn("Ready wait (ms): 0", summary)
        self.assertIn("Post-navigation wait (ms): 0", summary)
        self.assertIn(
            f"Screenshot filename: {DEFAULTS.output_naming.screenshot_filename}",
            summary,
        )
        self.assertIn(
            f"Review summary filename: {DEFAULTS.output_naming.review_summary_filename}",
            summary,
        )
        self.assertIn(
            f"Gallery index filename: {DEFAULTS.output_naming.gallery_index_filename}",
            summary,
        )

    def test_format_plan_summary_reports_dual_output_counts_for_primary_preset(self) -> None:
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                "runs",
                "--run-label",
                "smoke",
                "--preset",
                "standard-desktop",
                "--capture-mode",
                "both",
                "--dark-mode",
            ]
        )

        summary = format_plan_summary(plan)

        self.assertIn("Selected presets: Standard Desktop", summary)
        self.assertIn(
            "Resolved preset outputs: Standard Desktop (full-page, viewport)",
            summary,
        )
        self.assertIn("Capture mode override: both", summary)
        self.assertIn("Variant passes: default, dark", summary)
        self.assertIn("Planned artifact count: 4", summary)
        self.assertIn(
            "Supplemental artifacts: 2 companion viewport captures, 1 dark-mode artifacts",
            summary,
        )


class ConfigDefaultsTest(unittest.TestCase):
    def test_defaults_are_deterministic_and_centralized(self) -> None:
        self.assertEqual(DEFAULTS.timeout_ms, 30000)
        self.assertEqual(DEFAULTS.primary_preset, "Standard Desktop")
        self.assertEqual(DEFAULTS.waits.navigation_wait_until, "load")
        self.assertEqual(DEFAULTS.waits.post_navigation_wait_ms, 0)
        self.assertEqual(DEFAULTS.locale, "en-US")
        self.assertEqual(DEFAULTS.timezone_id, "UTC")
        self.assertEqual(DEFAULTS.output_naming.run_directory_template, "{run_label}")
        self.assertEqual(DEFAULTS.output_naming.screenshot_filename, "page.png")
        self.assertEqual(DEFAULTS.output_naming.metadata_filename, "capture-plan.json")
        self.assertEqual(
            DEFAULTS.output_naming.review_summary_filename, "review-summary.md"
        )
        self.assertEqual(
            DEFAULTS.output_naming.gallery_index_filename, "review-gallery.html"
        )

    def test_capture_matrix_covers_expected_viewport_families(self) -> None:
        self.assertEqual(
            [preset.name for preset in CAPTURE_MATRIX],
            [
                "Large Desktop",
                "Standard Desktop",
                "Laptop",
                "Tablet Portrait",
                "Tablet Landscape",
                "Mobile Portrait",
                "Mobile Landscape",
            ],
        )
        self.assertEqual(
            [preset.family for preset in CAPTURE_MATRIX],
            [
                "desktop",
                "desktop",
                "laptop",
                "tablet",
                "tablet",
                "mobile",
                "mobile",
            ],
        )

    def test_capture_matrix_marks_primary_and_supplemental_review_presets(self) -> None:
        self.assertEqual(
            [preset.name for preset in get_review_presets(role="primary")],
            ["Standard Desktop", "Tablet Portrait", "Mobile Portrait"],
        )
        self.assertEqual(
            [preset.name for preset in get_review_presets(role="supplemental")],
            ["Large Desktop", "Laptop", "Tablet Landscape", "Mobile Landscape"],
        )

    def test_capture_matrix_uses_explicit_sortable_filenames(self) -> None:
        self.assertEqual(
            [preset.filename for preset in CAPTURE_MATRIX],
            [
                "01-large-desktop-1728x1117.png",
                "02-standard-desktop-1440x900.png",
                "03-laptop-1280x800.png",
                "04-tablet-portrait-820x1180.png",
                "05-tablet-landscape-1180x820.png",
                "06-mobile-portrait-390x844.png",
                "07-mobile-landscape-844x390.png",
            ],
        )

    def test_capture_matrix_keeps_explicit_viewports_even_for_device_mappings(self) -> None:
        mobile_portrait = get_capture_preset("mobile-portrait")
        tablet_landscape = get_capture_preset("Tablet Landscape")

        self.assertEqual(mobile_portrait.device_descriptor, "iPhone 13")
        self.assertEqual(mobile_portrait.viewport.width, 390)
        self.assertEqual(mobile_portrait.viewport.height, 844)
        self.assertTrue(mobile_portrait.is_mobile)
        self.assertTrue(mobile_portrait.has_touch)
        self.assertEqual(mobile_portrait.capture_mode, "viewport")
        self.assertEqual(mobile_portrait.family, "mobile")
        self.assertEqual(mobile_portrait.review_preset_role, "primary")
        self.assertTrue(mobile_portrait.is_primary_review_preset)
        self.assertEqual(mobile_portrait.primary_capture_type, "viewport")
        self.assertEqual(mobile_portrait.output_capture_types, ("viewport",))
        self.assertFalse(mobile_portrait.include_above_the_fold_capture)
        self.assertFalse(mobile_portrait.full_page)

        self.assertEqual(tablet_landscape.device_descriptor, "iPad Pro 11 landscape")
        self.assertEqual(tablet_landscape.viewport.width, 1180)
        self.assertEqual(tablet_landscape.viewport.height, 820)
        self.assertFalse(tablet_landscape.is_mobile)
        self.assertTrue(tablet_landscape.has_touch)
        self.assertEqual(tablet_landscape.capture_mode, "full_page")
        self.assertEqual(tablet_landscape.family, "tablet")
        self.assertEqual(tablet_landscape.review_preset_role, "supplemental")
        self.assertFalse(tablet_landscape.is_primary_review_preset)
        self.assertEqual(tablet_landscape.primary_capture_type, "full_page")
        self.assertEqual(tablet_landscape.output_capture_types, ("full_page",))
        self.assertFalse(tablet_landscape.include_above_the_fold_capture)
        self.assertTrue(tablet_landscape.full_page)

    def test_capture_preset_rejects_unknown_capture_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported capture mode"):
            CapturePreset(
                order=99,
                slug="invalid",
                name="Invalid",
                family="desktop",
                viewport=Viewport(width=100, height=100),
                capture_mode="stitched",  # type: ignore[arg-type]
                review_preset_role="primary",
            )

    def test_capture_preset_rejects_unknown_review_preset_role(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported review preset role"):
            CapturePreset(
                order=99,
                slug="invalid-role",
                name="Invalid Role",
                family="desktop",
                viewport=Viewport(width=100, height=100),
                capture_mode="viewport",
                review_preset_role="secondary",  # type: ignore[arg-type]
            )

    def test_apply_capture_mode_selection_can_override_and_expand_artifacts(self) -> None:
        mobile_preset = get_capture_preset("mobile-portrait")

        viewport_only = apply_capture_mode_selection(mobile_preset, "viewport")
        full_page_only = apply_capture_mode_selection(mobile_preset, "full_page")
        both = apply_capture_mode_selection(mobile_preset, "both")

        self.assertEqual(viewport_only.output_capture_types, ("viewport",))
        self.assertEqual(full_page_only.output_capture_types, ("full_page",))
        self.assertEqual(both.output_capture_types, ("full_page", "viewport"))

    def test_resolve_capture_presets_filters_and_preserves_matrix_order(self) -> None:
        selected = resolve_capture_presets(
            include=("mobile-portrait", "large-desktop", "tablet-portrait"),
            exclude=("large-desktop",),
            capture_mode_selection="full_page",
        )

        self.assertEqual(
            [preset.slug for preset in selected],
            ["tablet-portrait", "mobile-portrait"],
        )
        self.assertTrue(all(preset.capture_mode == "full_page" for preset in selected))

    def test_resolve_capture_presets_can_subtract_excluded_presets_from_include_list(self) -> None:
        selected = resolve_capture_presets(
            include=("mobile-portrait", "tablet-portrait"),
            exclude=("mobile-portrait",),
        )

        self.assertEqual([preset.slug for preset in selected], ["tablet-portrait"])


class QuietFixtureHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        return


class LocalFixtureServer:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> str:
        handler = functools.partial(QuietFixtureHandler, directory=str(self.directory))
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="local-fixture-server",
            daemon=True,
        )
        self._thread.start()
        host, port = self._server.server_address
        return f"http://{host}:{port}/index.html"

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)
        return False


class FakePlaywrightError(Exception):
    pass


class FakePage:
    def __init__(self, preset_slug: str, failing_slug: str | None) -> None:
        self.preset_slug = preset_slug
        self.failing_slug = failing_slug
        self.emulate_media_calls: list[dict[str, object]] = []
        self.add_init_script_calls: list[str] = []
        self.goto_calls: list[dict[str, object]] = []
        self.load_state_calls: list[dict[str, object]] = []
        self.wait_for_function_calls: list[dict[str, object]] = []
        self.wait_for_selector_calls: list[dict[str, object]] = []
        self.wait_for_timeout_calls: list[int] = []
        self.screenshot_calls: list[dict[str, object]] = []

    def emulate_media(self, color_scheme: str, reduced_motion: str) -> None:
        self.emulate_media_calls.append(
            {
                "color_scheme": color_scheme,
                "reduced_motion": reduced_motion,
            }
        )

    def add_init_script(self, script: str) -> None:
        self.add_init_script_calls.append(script)

    def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_calls.append(
            {"url": url, "wait_until": wait_until, "timeout": timeout}
        )

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_state_calls.append({"state": state, "timeout": timeout})

    def wait_for_function(
        self, expression: str, arg: object | None = None, timeout: int = 0
    ) -> None:
        self.wait_for_function_calls.append(
            {"expression": expression.strip(), "arg": arg, "timeout": timeout}
        )

    def wait_for_selector(self, selector: str, state: str, timeout: int) -> None:
        self.wait_for_selector_calls.append(
            {"selector": selector, "state": state, "timeout": timeout}
        )

    def wait_for_timeout(self, timeout: int) -> None:
        self.wait_for_timeout_calls.append(timeout)

    def screenshot(self, path: str, full_page: bool) -> None:
        self.screenshot_calls.append({"path": path, "full_page": full_page})
        if self.preset_slug == self.failing_slug:
            raise FakePlaywrightError(f"{self.preset_slug} screenshot failed")
        Path(path).write_bytes(b"fake-png")


class FakeContext:
    def __init__(
        self,
        browser: "FakeBrowser",
        preset_slug: str,
        options: dict[str, object],
    ) -> None:
        self.browser = browser
        self.preset_slug = preset_slug
        self.options = options
        self.closed = False
        self.page = FakePage(preset_slug, browser.failing_slug)

    def new_page(self) -> FakePage:
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(
        self,
        failing_slug: str | None = None,
        *,
        launch_error: str | None = None,
    ) -> None:
        self.failing_slug = failing_slug
        self.launch_error = launch_error
        self.closed = False
        self.contexts: list[FakeContext] = []
        self.launch_count = 0

    def new_context(self, **options: object) -> FakeContext:
        preset = CAPTURE_MATRIX[len(self.contexts) % len(CAPTURE_MATRIX)]
        context = FakeContext(self, preset.slug, options)
        self.contexts.append(context)
        return context

    def close(self) -> None:
        self.closed = True


class FakeChromium:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser

    def launch(self) -> FakeBrowser:
        self.browser.launch_count += 1
        if self.browser.launch_error:
            raise FakePlaywrightError(self.browser.launch_error)
        return self.browser


class FakePlaywrightContextManager:
    def __init__(self, browser: FakeBrowser) -> None:
        self.browser = browser
        self.chromium = FakeChromium(browser)
        self.devices = {
            "Desktop Chrome": {
                "user_agent": "desktop-test-agent",
                "device_scale_factor": 1,
            },
            "iPad Pro 11": {
                "user_agent": "ipad-portrait-test-agent",
                "device_scale_factor": 2,
            },
            "iPad Pro 11 landscape": {
                "user_agent": "ipad-landscape-test-agent",
                "device_scale_factor": 2,
            },
            "iPhone 13": {
                "user_agent": "iphone-portrait-test-agent",
                "device_scale_factor": 3,
            },
            "iPhone 13 landscape": {
                "user_agent": "iphone-landscape-test-agent",
                "device_scale_factor": 3,
            },
        }

    def __enter__(self) -> "FakePlaywrightContextManager":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class CaptureEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(dir=REPOSITORY_ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def build_plan(
        self,
        *,
        preset_include: tuple[str, ...] = (),
        preset_exclude: tuple[str, ...] = (),
        capture_mode: str = "default",
        navigation_wait_until: str | None = None,
        post_navigation_wait_ms: int = 0,
        capture_dark_mode: bool = False,
        capture_no_javascript: bool = False,
        ready_selectors: tuple[str, ...] = (),
        ready_js_predicate: str | None = None,
        ready_wait_ms: int = 0,
    ):
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                str(self.temp_dir.relative_to(REPOSITORY_ROOT)),
                "--run-label",
                "capture-smoke",
                "--timeout-ms",
                "45000",
            ]
        )
        return plan.__class__(
            url=plan.url,
            output_dir=plan.output_dir,
            run_label=plan.run_label,
            timeout_ms=plan.timeout_ms,
            device_preset=plan.device_preset,
            preset_include=preset_include,
            preset_exclude=preset_exclude,
            capture_mode=capture_mode,
            navigation_wait_until=(
                navigation_wait_until
                if navigation_wait_until is not None
                else plan.navigation_wait_until
            ),
            post_navigation_wait_ms=post_navigation_wait_ms,
            locale=plan.locale,
            timezone_id=plan.timezone_id,
            capture_dark_mode=capture_dark_mode,
            capture_no_javascript=capture_no_javascript,
            ready_selectors=ready_selectors,
            ready_js_predicate=ready_js_predicate,
            ready_wait_ms=ready_wait_ms,
            screenshot_filename=plan.screenshot_filename,
            metadata_filename=plan.metadata_filename,
            review_summary_filename=plan.review_summary_filename,
            gallery_index_filename=plan.gallery_index_filename,
        )

    def test_run_capture_plan_captures_each_preset_with_expected_capture_mode(self) -> None:
        fake_browser = FakeBrowser()

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(self.build_plan(post_navigation_wait_ms=120))

        self.assertEqual(fake_browser.launch_count, 1)
        self.assertTrue(fake_browser.closed)
        self.assertEqual(len(run_result.results), len(CAPTURE_MATRIX))
        self.assertFalse(run_result.failed_captures)
        self.assertEqual(run_result.run_status, "complete-success")
        self.assertIsNone(run_result.run_error)
        self.assertEqual(run_result.manifest_path, run_result.run_dir / "capture-plan.json")
        self.assertEqual(
            run_result.review_summary_path, run_result.run_dir / "review-summary.md"
        )
        self.assertEqual(
            run_result.gallery_index_path, run_result.run_dir / "review-gallery.html"
        )
        self.assertTrue(run_result.manifest_path.exists())
        self.assertTrue(run_result.review_summary_path.exists())
        self.assertTrue(run_result.gallery_index_path.exists())
        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["url"], "http://localhost:8080/")
        self.assertEqual(manifest["run_label"], "capture-smoke")
        self.assertEqual(manifest["manifest_path"], str(run_result.manifest_path))
        self.assertEqual(
            manifest["review_summary_path"], str(run_result.review_summary_path)
        )
        self.assertEqual(
            manifest["gallery_index_path"], str(run_result.gallery_index_path)
        )
        self.assertEqual(len(manifest["captures"]), len(CAPTURE_MATRIX))
        self.assertTrue(manifest["captured_at"].endswith("Z"))
        self.assertEqual(manifest["run_status"], "complete-success")
        self.assertIsNone(manifest["run_error"])
        self.assertEqual(manifest["captures"][0]["preset"]["family"], "desktop")
        self.assertEqual(
            manifest["captures"][0]["preset"]["review_preset_role"], "supplemental"
        )
        self.assertFalse(manifest["captures"][0]["preset"]["is_primary_review_preset"])
        self.assertEqual(manifest["captures"][1]["preset"]["family"], "desktop")
        self.assertEqual(
            manifest["captures"][1]["preset"]["review_preset_role"], "primary"
        )
        self.assertTrue(manifest["captures"][1]["preset"]["is_primary_review_preset"])
        self.assertEqual(
            manifest["capture_counts"],
            {"total": len(CAPTURE_MATRIX), "succeeded": len(CAPTURE_MATRIX), "failed": 0},
        )
        self.assertTrue(manifest["logs"])
        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("type: report", review_summary)
        self.assertIn("# Screenshot Review Bundle", review_summary)
        self.assertIn("- URL: `http://localhost:8080/`", review_summary)
        self.assertIn("- Run label: `capture-smoke`", review_summary)
        self.assertIn("- Manifest: `capture-plan.json`", review_summary)
        self.assertIn("- Run status: `Complete success`", review_summary)
        self.assertIn("- Enabled variants: Default", review_summary)
        self.assertIn(
            "- Selected primary review presets: `Standard Desktop`, `Tablet Portrait`, `Mobile Portrait`",
            review_summary,
        )
        self.assertIn("## Preset Taxonomy", review_summary)
        self.assertIn(
            "- Primary: `Standard Desktop` (`desktop`, `1440x900`, `full_page`)",
            review_summary,
        )
        self.assertIn(
            "- Supplemental: `Large Desktop` (`desktop`, `1728x1117`, `full_page`)",
            review_summary,
        )
        self.assertIn("## Review Artifacts", review_summary)
        self.assertIn("### Primary review presets", review_summary)
        self.assertIn("### Supplemental review presets", review_summary)
        self.assertIn("- `Standard Desktop` (`desktop`, `1440x900`, `full_page`)", review_summary)
        self.assertIn("  - Variant `default`", review_summary)
        self.assertIn(
            "    - Full Page: `01-large-desktop-1728x1117-default-full-page.png`",
            review_summary,
        )
        self.assertIn("## Run Log", review_summary)
        self.assertIn("## Reviewer Guidance", review_summary)
        self.assertIn("Use this bundle for design critique. Comment on:", review_summary)
        self.assertIn("- hierarchy and scan order", review_summary)
        self.assertIn("- spacing and alignment consistency", review_summary)
        self.assertIn("- overall visual balance", review_summary)
        self.assertIn("- CTA prominence and clarity", review_summary)
        self.assertIn("- text density and readability", review_summary)
        self.assertIn("- awkward wrapping or truncation", review_summary)
        self.assertIn("- overflow, clipping, or layout breakage", review_summary)
        self.assertIn("- mobile and tablet adaptation compared with desktop", review_summary)
        self.assertIn("<!DOCTYPE html>", gallery_index)
        self.assertIn("Review Gallery: capture-smoke", gallery_index)
        self.assertIn("01-large-desktop-1728x1117-default-full-page.png", gallery_index)
        self.assertIn("Run Status</dt><dd>Complete success</dd>", gallery_index)
        self.assertIn("Successful Captures</dt><dd>7</dd>", gallery_index)
        self.assertIn("Failed Captures</dt><dd>0</dd>", gallery_index)
        self.assertIn("Primary review presets", gallery_index)
        self.assertIn("Supplemental review presets", gallery_index)
        self.assertIn("Primary preset", gallery_index)
        self.assertIn("Supplemental artifact", gallery_index)
        self.assertIn("Family</dt><dd>desktop</dd>", gallery_index)
        self.assertIn("Review Role</dt><dd>primary</dd>", gallery_index)
        first_capture = manifest["captures"][0]
        self.assertEqual(first_capture["preset"]["slug"], "large-desktop")
        self.assertEqual(first_capture["preset"]["viewport"], {"width": 1728, "height": 1117})
        self.assertEqual(first_capture["preset"]["capture_mode"], "full_page")
        self.assertTrue(first_capture["preset"]["full_page"])
        self.assertEqual(first_capture["variant"]["slug"], "default")
        self.assertEqual(first_capture["emulation"]["device_descriptor"], "Desktop Chrome")
        self.assertEqual(first_capture["emulation"]["viewport"], {"width": 1728, "height": 1117})
        self.assertEqual(first_capture["emulation"]["user_agent"], "desktop-test-agent")
        self.assertEqual(first_capture["capture"]["preset_capture_mode"], "full_page")
        self.assertEqual(first_capture["capture"]["artifact_capture_type"], "full_page")
        self.assertTrue(first_capture["capture"]["is_primary_capture_type"])
        self.assertTrue(first_capture["capture"]["is_full_page"])
        self.assertFalse(first_capture["capture"]["is_above_the_fold"])
        self.assertEqual(first_capture["review"]["preset_role"], "supplemental")
        self.assertEqual(first_capture["review"]["artifact_role"], "supplemental")
        self.assertFalse(first_capture["review"]["is_primary_review_preset"])
        self.assertEqual(first_capture["timing"]["navigation_wait_until"], manifest["navigation_wait_until"])
        self.assertEqual(first_capture["timing"]["timeout_ms"], manifest["timeout_ms"])
        self.assertEqual(
            first_capture["timing"]["post_navigation_wait_ms"],
            manifest["post_navigation_wait_ms"],
        )
        self.assertEqual(first_capture["timing"]["ready_wait_ms"], manifest["ready_wait_ms"])
        self.assertTrue(first_capture["timing"]["readiness_checks"])
        self.assertTrue(first_capture["output"]["exists"])
        self.assertEqual(first_capture["status"], "succeeded")
        self.assertIsNone(first_capture["error"])
        preset_capture_modes = {
            capture["preset"]["slug"]: capture["preset"]["capture_mode"]
            for capture in manifest["captures"]
        }
        self.assertEqual(
            preset_capture_modes,
            {
                "large-desktop": "full_page",
                "standard-desktop": "full_page",
                "laptop": "full_page",
                "tablet-portrait": "full_page",
                "tablet-landscape": "full_page",
                "mobile-portrait": "viewport",
                "mobile-landscape": "viewport",
            },
        )
        mobile_captures = {
            capture["preset"]["slug"]: capture["preset"]["capture_mode"]
            for capture in manifest["captures"]
            if capture["preset"]["slug"].startswith("mobile-")
        }
        self.assertEqual(
            mobile_captures,
            {
                "mobile-portrait": "viewport",
                "mobile-landscape": "viewport",
            },
        )

        for preset, context, result in zip(
            CAPTURE_MATRIX, fake_browser.contexts, run_result.results
        ):
            self.assertEqual(
                context.options["viewport"],
                {"width": preset.viewport.width, "height": preset.viewport.height},
            )
            self.assertEqual(context.options["is_mobile"], preset.is_mobile)
            self.assertEqual(context.options["has_touch"], preset.has_touch)
            self.assertEqual(context.options["locale"], DEFAULTS.locale)
            self.assertEqual(context.options["timezone_id"], DEFAULTS.timezone_id)
            self.assertEqual(context.options["color_scheme"], "light")
            self.assertTrue(context.options["java_script_enabled"])
            self.assertIn("user_agent", context.options)
            self.assertTrue(context.closed)
            self.assertTrue(result.success)
            self.assertEqual(
                result.screenshot_path.name,
                f"{preset.artifact_stem}-default-{preset.primary_capture_type.replace('_', '-')}.png",
            )
            self.assertEqual(result.variant.slug, "default")
            self.assertTrue(result.screenshot_path.exists())
            self.assertEqual(
                context.page.emulate_media_calls,
                [
                    {
                        "color_scheme": "light",
                        "reduced_motion": "reduce",
                    }
                ],
            )
            self.assertEqual(len(context.page.add_init_script_calls), 1)
            self.assertIn(
                "animation-duration: 0s",
                context.page.add_init_script_calls[0],
            )
            self.assertEqual(
                context.page.goto_calls,
                [
                    {
                        "url": "http://localhost:8080/",
                        "wait_until": DEFAULTS.waits.navigation_wait_until,
                        "timeout": 45000,
                    }
                ],
            )
            self.assertEqual(
                context.page.load_state_calls,
                [
                    {"state": "networkidle", "timeout": 5000},
                ],
            )
            self.assertEqual(
                context.page.wait_for_function_calls,
                [
                    {
                        "expression": "() => !document.fonts || document.fonts.status === 'loaded'",
                        "arg": None,
                        "timeout": 5000,
                    },
                    {
                        "expression": """() =>
            new Promise((resolve) => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => resolve(true));
                });
            })""",
                        "arg": None,
                        "timeout": 5000,
                    },
                ],
            )
            self.assertFalse(context.page.wait_for_selector_calls)
            self.assertEqual(context.page.wait_for_timeout_calls, [120])
            self.assertEqual(
                context.page.screenshot_calls,
                [{"path": str(result.screenshot_path), "full_page": preset.full_page}],
            )

    def test_run_capture_plan_adds_above_the_fold_artifact_when_enabled(self) -> None:
        fake_browser = FakeBrowser()
        patched_matrix = (
            replace(CAPTURE_MATRIX[0], include_above_the_fold_capture=True),
            *CAPTURE_MATRIX[1:],
        )

        with patch("python_webpage_capture.config.CAPTURE_MATRIX", patched_matrix):
            with patch(
                "python_webpage_capture.capture._get_playwright_api",
                return_value=(
                    lambda: FakePlaywrightContextManager(fake_browser),
                    FakePlaywrightError,
                ),
            ):
                run_result = run_capture_plan(self.build_plan())

        dual_results = [
            result
            for result in run_result.results
            if result.preset.slug == "large-desktop" and result.variant.slug == "default"
        ]
        self.assertEqual(len(run_result.results), len(CAPTURE_MATRIX) + 1)
        self.assertEqual(
            [(result.capture_type, result.screenshot_path.name) for result in dual_results],
            [
                ("full_page", "01-large-desktop-1728x1117-default-full-page.png"),
                ("viewport", "01-large-desktop-1728x1117-default-viewport.png"),
            ],
        )
        self.assertTrue(all(result.success for result in dual_results))
        self.assertEqual(
            fake_browser.contexts[0].page.screenshot_calls,
            [
                {
                    "path": str(
                        run_result.run_dir
                        / "01-large-desktop-1728x1117-default-full-page.png"
                    ),
                    "full_page": True,
                },
                {
                    "path": str(
                        run_result.run_dir
                        / "01-large-desktop-1728x1117-default-viewport.png"
                    ),
                    "full_page": False,
                },
            ],
        )

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        manifest_dual_results = [
            capture
            for capture in manifest["captures"]
            if capture["preset"]["slug"] == "large-desktop"
        ]
        self.assertEqual(
            [capture["output"]["capture_type"] for capture in manifest_dual_results],
            ["full_page", "viewport"],
        )
        self.assertEqual(
            manifest_dual_results[0]["preset"]["output_capture_types"],
            ["full_page", "viewport"],
        )
        self.assertTrue(
            manifest_dual_results[0]["preset"]["include_above_the_fold_capture"]
        )
        self.assertEqual(manifest_dual_results[0]["preset"]["family"], "desktop")
        self.assertEqual(
            manifest_dual_results[0]["preset"]["review_preset_role"], "supplemental"
        )
        self.assertTrue(manifest_dual_results[0]["capture"]["is_full_page"])
        self.assertFalse(manifest_dual_results[0]["capture"]["is_above_the_fold"])
        self.assertEqual(
            manifest_dual_results[1]["output"]["filename"],
            "01-large-desktop-1728x1117-default-viewport.png",
        )
        self.assertFalse(manifest_dual_results[1]["output"]["full_page"])
        self.assertTrue(manifest_dual_results[1]["capture"]["is_above_the_fold"])
        self.assertFalse(manifest_dual_results[1]["capture"]["is_primary_capture_type"])
        self.assertEqual(manifest_dual_results[1]["review"]["artifact_role"], "supplemental")

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn("## Preset Taxonomy", review_summary)
        self.assertIn(
            "    - Viewport: `01-large-desktop-1728x1117-default-viewport.png`",
            review_summary,
        )

        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("Large Desktop / default / viewport", gallery_index)
        self.assertIn("Large Desktop</h3>", gallery_index)
        self.assertIn("Companion Capture</dt><dd>above-the-fold viewport included</dd>", gallery_index)
        self.assertIn("Review Role</dt><dd>supplemental</dd>", gallery_index)
        self.assertIn(
            "Capture Type</dt><dd>viewport</dd>",
            gallery_index,
        )
        self.assertIn("Supplemental artifact", gallery_index)

    def test_run_capture_plan_keeps_primary_artifact_role_only_for_default_primary_capture(self) -> None:
        fake_browser = FakeBrowser()

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(
                self.build_plan(
                    preset_include=("standard-desktop",),
                    capture_mode="both",
                    capture_dark_mode=True,
                )
            )

        self.assertEqual(
            [
                (result.variant.slug, result.capture_type, result.success)
                for result in run_result.results
            ],
            [
                ("default", "full_page", True),
                ("default", "viewport", True),
                ("dark", "full_page", True),
                ("dark", "viewport", True),
            ],
        )

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        standard_desktop_captures = [
            capture
            for capture in manifest["captures"]
            if capture["preset"]["slug"] == "standard-desktop"
        ]
        self.assertEqual(len(standard_desktop_captures), 4)
        self.assertEqual(
            [
                (
                    capture["variant"]["slug"],
                    capture["output"]["capture_type"],
                    capture["review"]["artifact_role"],
                    capture["capture"]["is_above_the_fold"],
                )
                for capture in standard_desktop_captures
            ],
            [
                ("default", "full_page", "primary", False),
                ("default", "viewport", "supplemental", True),
                ("dark", "full_page", "supplemental", False),
                ("dark", "viewport", "supplemental", True),
            ],
        )
        self.assertEqual(
            standard_desktop_captures[0]["preset"]["output_capture_types"],
            ["full_page", "viewport"],
        )
        self.assertTrue(
            standard_desktop_captures[0]["preset"]["include_above_the_fold_capture"]
        )

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn(
            "- Selected presets: `Standard Desktop`",
            review_summary,
        )
        self.assertIn("- Capture mode override: `both`", review_summary)
        self.assertIn("### Primary review presets", review_summary)
        self.assertIn("  - Variant `default`", review_summary)
        self.assertIn("  - Variant `dark`", review_summary)
        self.assertIn(
            "    - Full Page: `02-standard-desktop-1440x900-default-full-page.png`",
            review_summary,
        )
        self.assertIn(
            "    - Viewport: `02-standard-desktop-1440x900-dark-viewport.png`",
            review_summary,
        )

        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("Companion Capture</dt><dd>above-the-fold viewport included</dd>", gallery_index)
        self.assertEqual(gallery_index.count("Primary artifact"), 1)
        self.assertEqual(gallery_index.count("Supplemental artifact"), 3)
        self.assertIn("Variant: default", gallery_index)
        self.assertIn("Variant: dark", gallery_index)
        self.assertIn("Standard Desktop / dark / full_page", gallery_index)

    def test_run_capture_plan_honors_preset_filters_and_capture_mode_override(self) -> None:
        fake_browser = FakeBrowser()

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(
                self.build_plan(
                    preset_include=("standard-desktop", "mobile-portrait"),
                    capture_mode="full_page",
                    navigation_wait_until="domcontentloaded",
                    post_navigation_wait_ms=75,
                )
            )

        self.assertEqual(
            [result.preset.slug for result in run_result.results],
            ["standard-desktop", "mobile-portrait"],
        )
        self.assertTrue(all(result.capture_type == "full_page" for result in run_result.results))
        self.assertEqual(len(fake_browser.contexts), 2)
        self.assertEqual(
            fake_browser.contexts[0].page.goto_calls,
            [
                {
                    "url": "http://localhost:8080/",
                    "wait_until": "domcontentloaded",
                    "timeout": 45000,
                }
            ],
        )
        self.assertEqual(fake_browser.contexts[1].page.wait_for_timeout_calls, [75])

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["capture_mode"], "full_page")
        self.assertEqual(
            manifest["selected_preset_slugs"],
            ["standard-desktop", "mobile-portrait"],
        )
        self.assertEqual(
            [capture["preset"]["slug"] for capture in manifest["captures"]],
            ["standard-desktop", "mobile-portrait"],
        )
        self.assertTrue(
            all(capture["output"]["capture_type"] == "full_page" for capture in manifest["captures"])
        )

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn(
            "- Selected presets: `Standard Desktop`, `Mobile Portrait`",
            review_summary,
        )
        self.assertIn("- Capture mode override: `full-page`", review_summary)
        self.assertIn(
            "- Primary: `Mobile Portrait` (`mobile`, `390x844`, `full_page`)",
            review_summary,
        )
        self.assertIn("### Primary review presets", review_summary)
        self.assertIn(
            "    - Full Page: `06-mobile-portrait-390x844-default-full-page.png`",
            review_summary,
        )

    def test_run_capture_plan_isolates_failures_per_preset(self) -> None:
        fake_browser = FakeBrowser(failing_slug="tablet-landscape")

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(self.build_plan())

        self.assertEqual(len(run_result.successful_captures), len(CAPTURE_MATRIX) - 1)
        self.assertEqual(len(run_result.failed_captures), 1)
        self.assertEqual(run_result.run_status, "partial-success")
        self.assertIsNone(run_result.run_error)
        self.assertEqual(run_result.failed_captures[0].preset.slug, "tablet-landscape")
        self.assertIn(
            "tablet-landscape screenshot failed", run_result.failed_captures[0].error
        )
        self.assertFalse(run_result.failed_captures[0].screenshot_path.exists())
        self.assertTrue(run_result.successful_captures[0].screenshot_path.exists())
        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        failed_capture = next(
            capture
            for capture in manifest["captures"]
            if capture["preset"]["slug"] == "tablet-landscape"
        )
        self.assertEqual(failed_capture["status"], "failed")
        self.assertIn("tablet-landscape screenshot failed", failed_capture["error"])
        self.assertEqual(manifest["run_status"], "partial-success")
        self.assertEqual(manifest["capture_counts"]["failed"], 1)
        self.assertEqual(
            failed_capture["output"]["path"],
            str(run_result.failed_captures[0].screenshot_path),
        )
        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn("- Run status: `Partial success`", review_summary)
        self.assertIn("## Failure Reasons", review_summary)
        self.assertIn(
            "- `Tablet Landscape` / `default` / `full_page`: tablet-landscape screenshot failed",
            review_summary,
        )
        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("Run Status</dt><dd>Partial success</dd>", gallery_index)
        self.assertIn("Tablet Landscape</h3>", gallery_index)
        self.assertIn("Screenshot unavailable", gallery_index)
        self.assertIn("tablet-landscape screenshot failed", gallery_index)
        self.assertIn("Failed Captures</dt><dd>1</dd>", gallery_index)

    def test_run_capture_plan_adds_dark_and_no_js_variants_with_ready_checks(self) -> None:
        fake_browser = FakeBrowser()

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(
                self.build_plan(
                    capture_dark_mode=True,
                    capture_no_javascript=True,
                    ready_selectors=("#hero",),
                    ready_js_predicate="window.__CAPTURE_READY__ === true",
                    ready_wait_ms=300,
                )
            )

        self.assertEqual(len(run_result.results), len(CAPTURE_MATRIX) * 3)
        self.assertEqual(
            [result.variant.slug for result in run_result.results],
            (["default"] * len(CAPTURE_MATRIX))
            + (["dark"] * len(CAPTURE_MATRIX))
            + (["no-js"] * len(CAPTURE_MATRIX)),
        )
        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn("- Enabled variants: Default, Dark mode, JavaScript disabled", review_summary)
        self.assertIn(
            f"    - Full Page: `{run_result.results[len(CAPTURE_MATRIX)].screenshot_path.name}`",
            review_summary,
        )
        self.assertIn(
            f"    - Full Page: `{run_result.results[len(CAPTURE_MATRIX) * 2].screenshot_path.name}`",
            review_summary,
        )

        dark_result = run_result.results[len(CAPTURE_MATRIX)]
        no_js_result = run_result.results[len(CAPTURE_MATRIX) * 2]
        self.assertTrue(dark_result.screenshot_path.name.endswith("-dark-full-page.png"))
        self.assertTrue(no_js_result.screenshot_path.name.endswith("-no-js-full-page.png"))

        dark_context = fake_browser.contexts[len(CAPTURE_MATRIX)]
        no_js_context = fake_browser.contexts[len(CAPTURE_MATRIX) * 2]
        self.assertEqual(dark_context.options["color_scheme"], "dark")
        self.assertTrue(dark_context.options["java_script_enabled"])
        self.assertEqual(no_js_context.options["color_scheme"], "light")
        self.assertFalse(no_js_context.options["java_script_enabled"])
        self.assertEqual(
            dark_context.page.emulate_media_calls,
            [{"color_scheme": "dark", "reduced_motion": "reduce"}],
        )
        self.assertEqual(
            no_js_context.page.wait_for_selector_calls,
            [{"selector": "#hero", "state": "visible", "timeout": 45000}],
        )
        self.assertEqual(no_js_context.page.wait_for_timeout_calls, [300])
        self.assertEqual(
            [call["expression"] for call in no_js_context.page.wait_for_function_calls],
            [
                """predicate => {
            const evaluator = new Function(`return Boolean(${predicate});`);
            return evaluator();
        }""",
                "() => !document.fonts || document.fonts.status === 'loaded'",
                """() =>
            new Promise((resolve) => {
                requestAnimationFrame(() => {
                    requestAnimationFrame(() => resolve(true));
                });
            })""",
            ],
        )
        self.assertEqual(
            no_js_context.page.wait_for_function_calls[0]["arg"],
            "window.__CAPTURE_READY__ === true",
        )

    def test_format_capture_run_result_reports_status_lines(self) -> None:
        fake_browser = FakeBrowser(failing_slug="mobile-landscape")

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(self.build_plan())

        summary = format_capture_run_result(run_result)

        self.assertIn(
            "Partial success: some artifacts were captured, and some failed. The review bundle was still written.",
            summary,
        )
        self.assertIn("Saved captures to:", summary)
        self.assertIn("Run status: partial-success", summary)
        self.assertIn("Capture counts: 6 succeeded / 1 failed / 7 total", summary)
        self.assertIn("Manifest:", summary)
        self.assertIn("Review summary:", summary)
        self.assertIn("Gallery index:", summary)
        self.assertIn(
            "Failed artifacts:",
            summary,
        )
        self.assertIn(
            "- 07-mobile-landscape-844x390-default-viewport.png [mobile-landscape / default / viewport]",
            summary,
        )

    def test_run_capture_plan_reports_total_failure_when_browser_launch_fails(self) -> None:
        fake_browser = FakeBrowser(launch_error="chromium launch failed")

        with patch(
            "python_webpage_capture.capture._get_playwright_api",
            return_value=(
                lambda: FakePlaywrightContextManager(fake_browser),
                FakePlaywrightError,
            ),
        ):
            run_result = run_capture_plan(self.build_plan(capture_dark_mode=True))

        self.assertEqual(run_result.run_status, "total-failure")
        self.assertIn("chromium launch failed", run_result.run_error)
        self.assertEqual(len(run_result.results), len(CAPTURE_MATRIX) * 2)
        self.assertFalse(run_result.successful_captures)
        self.assertEqual(len(run_result.failed_captures), len(CAPTURE_MATRIX) * 2)
        self.assertTrue(run_result.manifest_path.exists())
        self.assertTrue(run_result.review_summary_path.exists())
        self.assertTrue(run_result.gallery_index_path.exists())

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["run_status"], "total-failure")
        self.assertIn("chromium launch failed", manifest["run_error"])
        self.assertEqual(
            manifest["capture_counts"],
            {
                "total": len(CAPTURE_MATRIX) * 2,
                "succeeded": 0,
                "failed": len(CAPTURE_MATRIX) * 2,
            },
        )
        self.assertTrue(
            all(
                capture["error"] == run_result.run_error
                for capture in manifest["captures"]
            )
        )

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn("- Run status: `Total failure`", review_summary)
        self.assertIn("## Run Error", review_summary)
        self.assertIn("chromium launch failed", review_summary)
        self.assertIn("## Review Artifacts", review_summary)
        self.assertIn("## Failure Reasons", review_summary)
        self.assertIn("- `Large Desktop` / `default` / `full_page`:", review_summary)
        self.assertIn("- `Large Desktop` / `dark` / `full_page`:", review_summary)

        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("Run Status</dt><dd>Total failure</dd>", gallery_index)
        self.assertIn("Run error:</strong> Run aborted before completion: chromium launch failed", gallery_index)
        self.assertIn("Failed Captures</dt><dd>14</dd>", gallery_index)
        self.assertIn("Variant: dark", gallery_index)

    def test_main_returns_non_zero_when_any_capture_fails(self) -> None:
        with patch("python_webpage_capture.cli.run_capture_plan") as run_capture:
            run_capture.return_value.failed_captures = ("failure",)
            run_capture.return_value.results = ()
            run_capture.return_value.run_dir = self.temp_dir
            run_capture.return_value.manifest_path = self.temp_dir / "capture-plan.json"
            run_capture.return_value.review_summary_path = self.temp_dir / "review-summary.md"
            run_capture.return_value.gallery_index_path = self.temp_dir / "review-gallery.html"
            exit_code = main(
                [
                    "--url",
                    "http://localhost:8080/",
                    "--output-dir",
                    str(self.temp_dir.relative_to(REPOSITORY_ROOT)),
                    "--run-label",
                    "capture-smoke",
                ]
            )

        self.assertEqual(exit_code, 1)


class BrowserWorkflowSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as error:
            raise unittest.SkipTest(
                "Playwright is not installed; run `python -m pip install -e .` first."
            ) from error

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                browser.close()
        except Exception as error:
            raise unittest.SkipTest(
                "Playwright Chromium runtime is unavailable; run "
                "`python -m playwright install chromium` first."
            ) from error

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(dir=REPOSITORY_ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))

    def test_cli_smoke_run_captures_local_fixture(self) -> None:
        fixture_dir = self.temp_dir / "fixture-site"
        fixture_dir.mkdir()
        fixture_html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local Smoke Fixture</title>
  <style>
    body {
      margin: 0;
      font-family: Georgia, serif;
      background: linear-gradient(180deg, #f7efe4 0%, #d7e4f3 100%);
      color: #17212b;
    }
    #app {
      min-height: 1600px;
      padding: 48px 24px 120px;
    }
    .hero {
      max-width: 960px;
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.84);
      border: 1px solid rgba(23, 33, 43, 0.12);
      border-radius: 24px;
      padding: 32px;
      box-shadow: 0 24px 48px rgba(23, 33, 43, 0.12);
    }
    .band {
      margin-top: 32px;
      height: 640px;
      border-radius: 20px;
      background:
        linear-gradient(135deg, rgba(162, 59, 59, 0.18), rgba(21, 98, 136, 0.18)),
        repeating-linear-gradient(
          90deg,
          rgba(23, 33, 43, 0.04) 0,
          rgba(23, 33, 43, 0.04) 32px,
          transparent 32px,
          transparent 64px
        );
    }
  </style>
</head>
<body>
  <main id="app">
    <section class="hero">
      <p>Local smoke fixture for the Playwright screenshot pipeline.</p>
      <h1>Stable markup for end-to-end screenshot verification</h1>
      <p>This page stays fully local so the browser workflow can be tested without external dependencies.</p>
      <div class="band" aria-hidden="true"></div>
    </section>
  </main>
</body>
</html>
"""
        (fixture_dir / "index.html").write_text(fixture_html, encoding="utf-8")

        with LocalFixtureServer(fixture_dir) as fixture_url:
            exit_code = main(
                [
                    "--url",
                    fixture_url,
                    "--output-dir",
                    str(self.temp_dir.relative_to(REPOSITORY_ROOT)),
                    "--run-label",
                    "browser-workflow-smoke",
                    "--timeout-ms",
                    "5000",
                    "--ready-selector",
                    "#app",
                    "--ready-wait-ms",
                    "50",
                ]
            )

        run_dir = self.temp_dir / "browser-workflow-smoke"
        manifest_path = run_dir / "capture-plan.json"
        self.assertEqual(exit_code, 0)
        self.assertTrue(run_dir.exists())
        self.assertTrue(manifest_path.exists())

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["url"], fixture_url)
        self.assertEqual(manifest["run_status"], "complete-success")
        self.assertEqual(manifest["capture_counts"]["succeeded"], len(CAPTURE_MATRIX))
        self.assertTrue(
            any(run_dir.glob("*.png")),
            "Expected at least one screenshot artifact in the run directory.",
        )


class NonBrowserSerializationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(dir=REPOSITORY_ROOT))
        self.addCleanup(lambda: shutil.rmtree(self.temp_dir, ignore_errors=True))
        self.plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                str(self.temp_dir.relative_to(REPOSITORY_ROOT)),
                "--run-label",
                "serialization-check",
                "--dark-mode",
                "--disable-javascript-pass",
                "--ready-selector",
                "#app",
                "--ready-wait-ms",
                "250",
            ]
        )
        self.plan.run_dir.mkdir(parents=True, exist_ok=True)

    def test_build_capture_variants_is_stable_and_ordered(self) -> None:
        variants = _build_capture_variants(self.plan)

        self.assertEqual(
            [(variant.slug, variant.color_scheme, variant.java_script_enabled) for variant in variants],
            [
                ("default", "light", True),
                ("dark", "dark", True),
                ("no-js", "light", False),
            ],
        )

    def test_write_outputs_serializes_manifest_review_and_gallery_without_browser(self) -> None:
        success_preset = CAPTURE_MATRIX[0]
        failed_preset = CAPTURE_MATRIX[-1]
        default_variant = CaptureVariant(
            slug="default",
            color_scheme="light",
            java_script_enabled=True,
        )
        dark_variant = CaptureVariant(
            slug="dark",
            color_scheme="dark",
            java_script_enabled=True,
        )
        success_path = self.plan.run_dir / "01-large-desktop-1728x1117-default-full-page.png"
        success_path.write_bytes(b"fake-png")
        failed_path = self.plan.run_dir / "07-mobile-landscape-844x390-dark-viewport.png"

        run_result = CaptureRunResult(
            run_dir=self.plan.run_dir,
            manifest_path=self.plan.run_dir / self.plan.metadata_filename,
            review_summary_path=self.plan.run_dir / self.plan.review_summary_filename,
            gallery_index_path=self.plan.run_dir / self.plan.gallery_index_filename,
            captured_at="2026-04-01T10:00:00Z",
            results=(
                CaptureResult(
                    preset=success_preset,
                    variant=default_variant,
                    capture_type="full_page",
                    screenshot_path=success_path,
                    context_options={
                        "locale": self.plan.locale,
                        "timezone_id": self.plan.timezone_id,
                        "is_mobile": success_preset.is_mobile,
                        "has_touch": success_preset.has_touch,
                        "color_scheme": default_variant.color_scheme,
                        "java_script_enabled": default_variant.java_script_enabled,
                        "user_agent": "desktop-test-agent",
                        "device_scale_factor": 1,
                    },
                    success=True,
                ),
                CaptureResult(
                    preset=failed_preset,
                    variant=dark_variant,
                    capture_type="viewport",
                    screenshot_path=failed_path,
                    context_options={
                        "locale": self.plan.locale,
                        "timezone_id": self.plan.timezone_id,
                        "is_mobile": failed_preset.is_mobile,
                        "has_touch": failed_preset.has_touch,
                        "color_scheme": dark_variant.color_scheme,
                        "java_script_enabled": dark_variant.java_script_enabled,
                        "user_agent": "mobile-test-agent",
                        "device_scale_factor": 3,
                    },
                    success=False,
                    error="mock serialization failure",
                ),
            ),
            logs=(
                CaptureLogEntry(
                    level="info",
                    stage="run-started",
                    message="Synthetic serialization run",
                    timestamp="2026-04-01T10:00:00Z",
                ),
                CaptureLogEntry(
                    level="error",
                    stage="capture-failed",
                    message="mock serialization failure",
                    preset_slug=failed_preset.slug,
                    variant_slug=dark_variant.slug,
                    timestamp="2026-04-01T10:00:02Z",
                ),
            ),
            run_error="Synthetic run error",
        )

        _write_manifest(self.plan, run_result)
        _write_review_summary(self.plan, run_result)
        _write_gallery_index(self.plan, run_result)

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["run_status"], "partial-success")
        self.assertEqual(
            manifest["capture_counts"],
            {"total": 21, "succeeded": 1, "failed": 20},
        )
        self.assertEqual(manifest["ready_selectors"], ["#app"])
        self.assertEqual(manifest["ready_js_predicate"], None)
        self.assertEqual(manifest["ready_wait_ms"], 250)
        self.assertEqual(
            manifest["captures"][0]["output"]["filename"],
            "01-large-desktop-1728x1117-default-full-page.png",
        )
        self.assertEqual(manifest["captures"][0]["output"]["capture_type"], "full_page")
        self.assertTrue(manifest["captures"][0]["output"]["exists"])
        self.assertEqual(manifest["captures"][0]["preset"]["family"], "desktop")
        self.assertEqual(manifest["captures"][0]["preset"]["capture_mode"], "full_page")
        self.assertEqual(
            manifest["captures"][0]["preset"]["review_preset_role"], "supplemental"
        )
        self.assertEqual(manifest["captures"][0]["capture"]["artifact_capture_type"], "full_page")
        self.assertTrue(manifest["captures"][0]["capture"]["is_primary_capture_type"])
        self.assertFalse(manifest["captures"][0]["capture"]["is_above_the_fold"])
        self.assertEqual(manifest["captures"][0]["review"]["artifact_role"], "supplemental")
        self.assertEqual(manifest["captures"][0]["emulation"]["viewport"], {"width": 1728, "height": 1117})
        self.assertEqual(
            manifest["captures"][0]["timing"]["readiness_checks"][0]["operation"],
            "load-state",
        )
        failed_capture = next(
            capture
            for capture in manifest["captures"]
            if capture["preset"]["slug"] == failed_preset.slug
            and capture["variant"]["slug"] == "dark"
            and capture["output"]["capture_type"] == "viewport"
        )
        self.assertEqual(failed_capture["variant"]["slug"], "dark")
        self.assertEqual(failed_capture["preset"]["family"], "mobile")
        self.assertEqual(failed_capture["preset"]["capture_mode"], "viewport")
        self.assertEqual(
            failed_capture["preset"]["review_preset_role"], "supplemental"
        )
        self.assertEqual(failed_capture["output"]["capture_type"], "viewport")
        self.assertFalse(failed_capture["output"]["exists"])
        self.assertEqual(failed_capture["capture"]["preset_capture_mode"], "viewport")
        self.assertTrue(failed_capture["capture"]["is_primary_capture_type"])
        self.assertFalse(failed_capture["capture"]["is_above_the_fold"])
        self.assertEqual(failed_capture["review"]["artifact_role"], "supplemental")
        self.assertEqual(
            failed_capture["emulation"]["viewport"],
            {"width": 844, "height": 390},
        )
        self.assertEqual(failed_capture["timing"]["ready_wait_ms"], 250)
        self.assertEqual(failed_capture["status"], "failed")
        self.assertEqual(failed_capture["error"], "mock serialization failure")
        self.assertEqual(manifest["logs"][1]["preset_slug"], failed_preset.slug)

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn("type: report", review_summary)
        self.assertIn("created: 2026-04-01", review_summary)
        self.assertIn(
            "- Capture counts: `1 succeeded / 20 failed / 21 total`",
            review_summary,
        )
        self.assertIn(
            "- Enabled variants: Default, Dark mode, JavaScript disabled",
            review_summary,
        )
        self.assertIn(
            "- Selected primary review presets: `Standard Desktop`, `Tablet Portrait`, `Mobile Portrait`",
            review_summary,
        )
        self.assertIn("- Run status: `Partial success`", review_summary)
        self.assertIn("## Preset Taxonomy", review_summary)
        self.assertIn("## Review Artifacts", review_summary)
        self.assertIn("### Primary review presets", review_summary)
        self.assertIn("### Supplemental review presets", review_summary)
        self.assertIn(
            "    - Full Page: `01-large-desktop-1728x1117-default-full-page.png`",
            review_summary,
        )
        self.assertIn(
            "    - Viewport: `07-mobile-landscape-844x390-dark-viewport.png` - failed: mock serialization failure",
            review_summary,
        )
        self.assertIn(
            "    - Full Page: `02-standard-desktop-1440x900-no-js-full-page.png` - failed: Artifact missing from run results after run abort.",
            review_summary,
        )
        self.assertIn("## Run Error", review_summary)
        self.assertIn("## Failure Reasons", review_summary)
        self.assertIn("## Run Log", review_summary)

        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", gallery_index)
        self.assertIn("Review Gallery: serialization-check", gallery_index)
        self.assertIn("Variants: default, dark, no-js", gallery_index)
        self.assertIn("Run Status</dt><dd>Partial success</dd>", gallery_index)
        self.assertIn("Successful Captures</dt><dd>1</dd>", gallery_index)
        self.assertIn("Failed Captures</dt><dd>20</dd>", gallery_index)
        self.assertIn("Family</dt><dd>mobile</dd>", gallery_index)
        self.assertIn("Review Role</dt><dd>supplemental</dd>", gallery_index)
        self.assertIn("Capture Type</dt><dd>viewport</dd>", gallery_index)
        self.assertIn("Screenshot unavailable", gallery_index)
        self.assertIn("mock serialization failure", gallery_index)
        self.assertIn("Artifact missing from run results after run abort.", gallery_index)

    def test_write_outputs_backfills_missing_planned_artifacts_as_failures(self) -> None:
        success_preset = self.plan.capture_presets[0]
        default_variant = CaptureVariant(
            slug="default",
            color_scheme="light",
            java_script_enabled=True,
        )
        success_path = self.plan.run_dir / "01-large-desktop-1728x1117-default-full-page.png"
        success_path.write_bytes(b"fake-png")

        run_result = CaptureRunResult(
            run_dir=self.plan.run_dir,
            manifest_path=self.plan.run_dir / self.plan.metadata_filename,
            review_summary_path=self.plan.run_dir / self.plan.review_summary_filename,
            gallery_index_path=self.plan.run_dir / self.plan.gallery_index_filename,
            captured_at="2026-04-01T10:00:00Z",
            results=(
                CaptureResult(
                    preset=success_preset,
                    variant=default_variant,
                    capture_type="full_page",
                    screenshot_path=success_path,
                    context_options={
                        "locale": self.plan.locale,
                        "timezone_id": self.plan.timezone_id,
                        "is_mobile": success_preset.is_mobile,
                        "has_touch": success_preset.has_touch,
                        "color_scheme": default_variant.color_scheme,
                        "java_script_enabled": default_variant.java_script_enabled,
                    },
                    success=True,
                ),
            ),
            logs=(),
            run_error=None,
        )

        _write_manifest(self.plan, run_result)
        _write_review_summary(self.plan, run_result)
        _write_gallery_index(self.plan, run_result)

        manifest = json.loads(run_result.manifest_path.read_text(encoding="utf-8"))
        planned_artifact_count = len(self.plan.capture_presets) * len(
            _build_capture_variants(self.plan)
        )
        self.assertEqual(
            manifest["capture_counts"],
            {"total": planned_artifact_count, "succeeded": 1, "failed": planned_artifact_count - 1},
        )
        self.assertEqual(len(manifest["captures"]), planned_artifact_count)

        missing_capture = next(
            capture
            for capture in manifest["captures"]
            if capture["preset"]["slug"] == "standard-desktop"
            and capture["variant"]["slug"] == "default"
            and capture["output"]["capture_type"] == "full_page"
        )
        self.assertEqual(missing_capture["status"], "failed")
        self.assertEqual(missing_capture["error"], "Artifact missing from run results.")
        self.assertFalse(missing_capture["output"]["exists"])

        review_summary = run_result.review_summary_path.read_text(encoding="utf-8")
        self.assertIn(
            "- Capture counts: `1 succeeded / 20 failed / 21 total`",
            review_summary,
        )
        self.assertIn("  - Variant `default`", review_summary)
        self.assertIn(
            "    - Full Page: `02-standard-desktop-1440x900-default-full-page.png` - failed: Artifact missing from run results.",
            review_summary,
        )

        gallery_index = run_result.gallery_index_path.read_text(encoding="utf-8")
        self.assertIn("Variants: default, dark, no-js", gallery_index)
        self.assertIn("Successful Captures</dt><dd>1</dd>", gallery_index)
        self.assertIn("Failed Captures</dt><dd>20</dd>", gallery_index)
        self.assertIn("02-standard-desktop-1440x900-default-full-page.png", gallery_index)
        self.assertIn("Artifact missing from run results.", gallery_index)
        self.assertIn("Screenshot unavailable", gallery_index)

    def test_format_plan_summary_surfaces_supplemental_artifacts_before_run(self) -> None:
        plan = build_capture_plan(
            [
                "--url",
                "http://localhost:8080/",
                "--output-dir",
                str(self.temp_dir.relative_to(REPOSITORY_ROOT)),
                "--run-label",
                "serialization-check",
                "--capture-mode",
                "both",
                "--dark-mode",
                "--disable-javascript-pass",
            ]
        )

        summary = format_plan_summary(plan)

        self.assertIn("Variant passes: default, dark, no-js", summary)
        self.assertIn("Planned artifact count: 42", summary)
        self.assertIn(
            "Supplemental artifacts: 21 companion viewport captures, 7 dark-mode artifacts, 7 no-JavaScript artifacts",
            summary,
        )
