"""Read Quayshell configuration from TOML."""

from __future__ import annotations

import math
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_WIDTH = 380
DEFAULT_HEIGHT = 72
DEFAULT_MARGIN = 8
DEFAULT_FONT = "Monospace 11"
DEFAULT_MAX_SCALE = 2.5
DEFAULT_CROSS_MONITOR = True
DEFAULT_SMART_COLLAPSE = True
DEFAULT_EXPAND_ON_FAILURE = True
DEFAULT_NOTIFY_ON_COMPLETION = True
DEFAULT_NOTIFICATION_AFTER_SECONDS = 5.0
DEFAULT_RESULT_SECONDS = 8.0
DEFAULT_MASCOT = True
DEFAULT_MAGNETIC_DOCKING = True
DEFAULT_SNAP_DISTANCE = 24
DEFAULT_BACKEND = "auto"


class ConfigError(ValueError):
    """The configuration file contains invalid data."""


@dataclass(frozen=True)
class Config:
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    margin: int = DEFAULT_MARGIN
    monitor: str | None = None
    dock_namespace: str | None = None
    max_scale: float = DEFAULT_MAX_SCALE
    cross_monitor: bool = DEFAULT_CROSS_MONITOR
    font: str = DEFAULT_FONT
    shell: str | None = None
    smart_collapse: bool = DEFAULT_SMART_COLLAPSE
    expand_on_failure: bool = DEFAULT_EXPAND_ON_FAILURE
    notify_on_completion: bool = DEFAULT_NOTIFY_ON_COMPLETION
    notification_after_seconds: float = DEFAULT_NOTIFICATION_AFTER_SECONDS
    result_seconds: float = DEFAULT_RESULT_SECONDS
    mascot: bool = DEFAULT_MASCOT
    magnetic_docking: bool = DEFAULT_MAGNETIC_DOCKING
    snap_distance: int = DEFAULT_SNAP_DISTANCE
    backend: str = DEFAULT_BACKEND


def default_config_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home).expanduser() if config_home else Path.home() / ".config"
    return base / "quayshell" / "config.toml"


def _table(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a TOML table.")
    return value


def _reject_unknown_keys(
    values: dict[str, Any],
    allowed: set[str],
    location: str,
) -> None:
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ConfigError(f"Unknown {location} setting: {unknown[0]}.")


def _integer(
    values: dict[str, Any],
    table: str,
    name: str,
    default: int,
    *,
    minimum: int,
) -> int:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{table}.{name} must be an integer.")
    if value < minimum:
        comparison = "greater than zero" if minimum == 1 else "zero or greater"
        raise ConfigError(f"{table}.{name} must be {comparison}.")
    return value


def _number(
    values: dict[str, Any],
    table: str,
    name: str,
    default: float,
    *,
    minimum: float,
) -> float:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{table}.{name} must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < minimum:
        raise ConfigError(f"{table}.{name} must be {minimum} or greater.")
    return value


def _boolean(
    values: dict[str, Any],
    table: str,
    name: str,
    default: bool,
) -> bool:
    value = values.get(name, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{table}.{name} must be true or false.")
    return value


def _optional_string(
    values: dict[str, Any],
    table: str,
    name: str,
    default: str | None,
) -> str | None:
    value = values.get(name, default)
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ConfigError(f"{table}.{name} must be a nonempty string.")
    return value


def _choice(
    values: dict[str, Any],
    table: str,
    name: str,
    default: str,
    allowed: set[str],
) -> str:
    value = values.get(name, default)
    if not isinstance(value, str) or value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise ConfigError(f"{table}.{name} must be one of: {choices}.")
    return value


def load_config(path: Path | None = None) -> Config:
    config_path = path or default_config_path()
    if not config_path.exists():
        return Config()

    try:
        with config_path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Cannot read {config_path}: {error}") from error

    _reject_unknown_keys(
        data, {"window", "terminal", "behavior", "compositor"}, "top-level"
    )
    window = _table(data, "window")
    terminal = _table(data, "terminal")
    behavior = _table(data, "behavior")
    compositor = _table(data, "compositor")
    _reject_unknown_keys(
        window,
        {
            "width",
            "height",
            "margin",
            "monitor",
            "dock_namespace",
            "max_scale",
            "cross_monitor",
        },
        "window",
    )
    _reject_unknown_keys(terminal, {"font", "shell"}, "terminal")
    _reject_unknown_keys(compositor, {"backend"}, "compositor")
    _reject_unknown_keys(
        behavior,
        {
            "smart_collapse",
            "expand_on_failure",
            "notify_on_completion",
            "notification_after_seconds",
            "result_seconds",
            "mascot",
            "magnetic_docking",
            "snap_distance",
        },
        "behavior",
    )

    return Config(
        width=_integer(window, "window", "width", DEFAULT_WIDTH, minimum=1),
        height=_integer(window, "window", "height", DEFAULT_HEIGHT, minimum=1),
        margin=_integer(window, "window", "margin", DEFAULT_MARGIN, minimum=0),
        monitor=_optional_string(window, "window", "monitor", None),
        dock_namespace=_optional_string(window, "window", "dock_namespace", None),
        max_scale=_number(
            window, "window", "max_scale", DEFAULT_MAX_SCALE, minimum=1.0
        ),
        cross_monitor=_boolean(
            window, "window", "cross_monitor", DEFAULT_CROSS_MONITOR
        ),
        font=_optional_string(terminal, "terminal", "font", DEFAULT_FONT)
        or DEFAULT_FONT,
        shell=_optional_string(terminal, "terminal", "shell", None),
        smart_collapse=_boolean(
            behavior, "behavior", "smart_collapse", DEFAULT_SMART_COLLAPSE
        ),
        expand_on_failure=_boolean(
            behavior, "behavior", "expand_on_failure", DEFAULT_EXPAND_ON_FAILURE
        ),
        notify_on_completion=_boolean(
            behavior,
            "behavior",
            "notify_on_completion",
            DEFAULT_NOTIFY_ON_COMPLETION,
        ),
        notification_after_seconds=_number(
            behavior,
            "behavior",
            "notification_after_seconds",
            DEFAULT_NOTIFICATION_AFTER_SECONDS,
            minimum=0.0,
        ),
        result_seconds=_number(
            behavior,
            "behavior",
            "result_seconds",
            DEFAULT_RESULT_SECONDS,
            minimum=0.0,
        ),
        mascot=_boolean(behavior, "behavior", "mascot", DEFAULT_MASCOT),
        magnetic_docking=_boolean(
            behavior,
            "behavior",
            "magnetic_docking",
            DEFAULT_MAGNETIC_DOCKING,
        ),
        snap_distance=_integer(
            behavior,
            "behavior",
            "snap_distance",
            DEFAULT_SNAP_DISTANCE,
            minimum=0,
        ),
        backend=_choice(
            compositor,
            "compositor",
            "backend",
            DEFAULT_BACKEND,
            {"auto", "generic", "hyprland", "sway"},
        ),
    )
