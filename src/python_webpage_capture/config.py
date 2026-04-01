"""Deterministic defaults for screenshot capture planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final, Literal


CaptureMode = Literal["viewport", "full_page"]
VALID_CAPTURE_MODES: Final[frozenset[str]] = frozenset({"viewport", "full_page"})
CaptureModeSelection = Literal["default", "viewport", "full_page", "both"]
VALID_CAPTURE_MODE_SELECTIONS: Final[frozenset[str]] = frozenset(
    {"default", "viewport", "full_page", "both"}
)
NavigationWaitUntil = Literal["commit", "domcontentloaded", "load", "networkidle"]
VALID_NAVIGATION_WAIT_UNTIL: Final[frozenset[str]] = frozenset(
    {"commit", "domcontentloaded", "load", "networkidle"}
)
PresetFamily = Literal["desktop", "laptop", "tablet", "mobile"]
VALID_PRESET_FAMILIES: Final[frozenset[str]] = frozenset(
    {"desktop", "laptop", "tablet", "mobile"}
)
ReviewPresetRole = Literal["primary", "supplemental"]
VALID_REVIEW_PRESET_ROLES: Final[frozenset[str]] = frozenset(
    {"primary", "supplemental"}
)


@dataclass(frozen=True)
class Viewport:
    width: int
    height: int


@dataclass(frozen=True)
class CapturePreset:
    order: int
    slug: str
    name: str
    family: PresetFamily
    viewport: Viewport
    capture_mode: CaptureMode
    review_preset_role: ReviewPresetRole
    device_descriptor: str | None = None
    is_mobile: bool = False
    has_touch: bool = False
    include_above_the_fold_capture: bool = False
    default_browser_color_scheme: str = "light"

    def __post_init__(self) -> None:
        if self.capture_mode not in VALID_CAPTURE_MODES:
            raise ValueError(
                f"Unsupported capture mode {self.capture_mode!r}; "
                f"expected one of {sorted(VALID_CAPTURE_MODES)}"
            )
        if self.family not in VALID_PRESET_FAMILIES:
            raise ValueError(
                f"Unsupported preset family {self.family!r}; "
                f"expected one of {sorted(VALID_PRESET_FAMILIES)}"
            )
        if self.review_preset_role not in VALID_REVIEW_PRESET_ROLES:
            raise ValueError(
                f"Unsupported review preset role {self.review_preset_role!r}; "
                f"expected one of {sorted(VALID_REVIEW_PRESET_ROLES)}"
            )

    @property
    def filename(self) -> str:
        return f"{self.order:02d}-{self.slug}-{self.viewport.width}x{self.viewport.height}.png"

    @property
    def artifact_stem(self) -> str:
        return f"{self.order:02d}-{self.slug}-{self.viewport.width}x{self.viewport.height}"

    @property
    def primary_capture_type(self) -> CaptureMode:
        return self.capture_mode

    @property
    def output_capture_types(self) -> tuple[CaptureMode, ...]:
        if self.include_above_the_fold_capture and self.capture_mode != "viewport":
            return (self.capture_mode, "viewport")
        return (self.capture_mode,)

    @property
    def full_page(self) -> bool:
        return self.capture_mode == "full_page"

    @property
    def is_primary_review_preset(self) -> bool:
        return self.review_preset_role == "primary"


@dataclass(frozen=True)
class WaitDefaults:
    navigation_wait_until: NavigationWaitUntil
    post_navigation_wait_ms: int


@dataclass(frozen=True)
class OutputNamingDefaults:
    run_directory_template: str
    screenshot_filename: str
    metadata_filename: str
    review_summary_filename: str
    gallery_index_filename: str


@dataclass(frozen=True)
class CaptureDefaults:
    timeout_ms: int
    primary_preset: str
    waits: WaitDefaults
    locale: str
    timezone_id: str
    output_naming: OutputNamingDefaults


CAPTURE_MATRIX: Final[tuple[CapturePreset, ...]] = (
    CapturePreset(
        order=1,
        slug="large-desktop",
        name="Large Desktop",
        family="desktop",
        viewport=Viewport(width=1728, height=1117),
        device_descriptor="Desktop Chrome",
        capture_mode="full_page",
        review_preset_role="supplemental",
    ),
    CapturePreset(
        order=2,
        slug="standard-desktop",
        name="Standard Desktop",
        family="desktop",
        viewport=Viewport(width=1440, height=900),
        device_descriptor="Desktop Chrome",
        capture_mode="full_page",
        review_preset_role="primary",
    ),
    CapturePreset(
        order=3,
        slug="laptop",
        name="Laptop",
        family="laptop",
        viewport=Viewport(width=1280, height=800),
        device_descriptor="Desktop Chrome",
        capture_mode="full_page",
        review_preset_role="supplemental",
    ),
    CapturePreset(
        order=4,
        slug="tablet-portrait",
        name="Tablet Portrait",
        family="tablet",
        viewport=Viewport(width=820, height=1180),
        device_descriptor="iPad Pro 11",
        has_touch=True,
        capture_mode="full_page",
        review_preset_role="primary",
    ),
    CapturePreset(
        order=5,
        slug="tablet-landscape",
        name="Tablet Landscape",
        family="tablet",
        viewport=Viewport(width=1180, height=820),
        device_descriptor="iPad Pro 11 landscape",
        has_touch=True,
        capture_mode="full_page",
        review_preset_role="supplemental",
    ),
    CapturePreset(
        order=6,
        slug="mobile-portrait",
        name="Mobile Portrait",
        family="mobile",
        viewport=Viewport(width=390, height=844),
        device_descriptor="iPhone 13",
        is_mobile=True,
        has_touch=True,
        capture_mode="viewport",
        review_preset_role="primary",
    ),
    CapturePreset(
        order=7,
        slug="mobile-landscape",
        name="Mobile Landscape",
        family="mobile",
        viewport=Viewport(width=844, height=390),
        device_descriptor="iPhone 13 landscape",
        is_mobile=True,
        has_touch=True,
        capture_mode="viewport",
        review_preset_role="supplemental",
    ),
)


def get_capture_preset(name: str) -> CapturePreset:
    for preset in CAPTURE_MATRIX:
        if preset.name == name or preset.slug == name:
            return preset
    raise KeyError(f"Unknown capture preset: {name}")


def apply_capture_mode_selection(
    preset: CapturePreset,
    selection: CaptureModeSelection,
) -> CapturePreset:
    if selection not in VALID_CAPTURE_MODE_SELECTIONS:
        raise ValueError(
            f"Unsupported capture mode selection {selection!r}; "
            f"expected one of {sorted(VALID_CAPTURE_MODE_SELECTIONS)}"
        )
    if selection == "default":
        return preset
    if selection == "viewport":
        return replace(
            preset,
            capture_mode="viewport",
            include_above_the_fold_capture=False,
        )
    if selection == "full_page":
        return replace(
            preset,
            capture_mode="full_page",
            include_above_the_fold_capture=False,
        )
    return replace(
        preset,
        capture_mode="full_page",
        include_above_the_fold_capture=True,
    )


def resolve_capture_presets(
    *,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
    capture_mode_selection: CaptureModeSelection = "default",
) -> tuple[CapturePreset, ...]:
    include_set = {name.casefold() for name in include}
    exclude_set = {name.casefold() for name in exclude}

    resolved: list[CapturePreset] = []
    for preset in CAPTURE_MATRIX:
        preset_keys = {preset.slug.casefold(), preset.name.casefold()}
        if include_set and not (preset_keys & include_set):
            continue
        if preset_keys & exclude_set:
            continue
        resolved.append(apply_capture_mode_selection(preset, capture_mode_selection))

    if include and not resolved:
        unknown_names = [
            name
            for name in include
            if not any(
                name.casefold() in {preset.slug.casefold(), preset.name.casefold()}
                for preset in CAPTURE_MATRIX
            )
        ]
        if unknown_names:
            raise KeyError(f"Unknown capture preset: {unknown_names[0]}")

    if not resolved:
        raise ValueError("Preset filters removed every capture preset.")

    return tuple(resolved)


def get_review_presets(*, role: ReviewPresetRole) -> tuple[CapturePreset, ...]:
    return tuple(preset for preset in CAPTURE_MATRIX if preset.review_preset_role == role)


DEFAULTS = CaptureDefaults(
    timeout_ms=30_000,
    primary_preset="Standard Desktop",
    waits=WaitDefaults(
        navigation_wait_until="load",
        post_navigation_wait_ms=0,
    ),
    locale="en-US",
    timezone_id="UTC",
    output_naming=OutputNamingDefaults(
        run_directory_template="{run_label}",
        screenshot_filename="page.png",
        metadata_filename="capture-plan.json",
        review_summary_filename="review-summary.md",
        gallery_index_filename="review-gallery.html",
    ),
)
