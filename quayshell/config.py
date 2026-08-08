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
    name: str,
    default: int,
    *,
    minimum: int,
) -> int:
    value = values.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"window.{name} must be an integer.")
    if value < minimum:
        comparison = "greater than zero" if minimum == 1 else "zero or greater"
        raise ConfigError(f"window.{name} must be {comparison}.")
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


def _max_scale(window: dict[str, Any]) -> float:
    value = window.get("max_scale", DEFAULT_MAX_SCALE)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("window.max_scale must be a number.")
    value = float(value)
    if not math.isfinite(value) or value < 1.0:
        raise ConfigError("window.max_scale must be 1.0 or greater.")
    return value


def _cross_monitor(window: dict[str, Any]) -> bool:
    value = window.get("cross_monitor", DEFAULT_CROSS_MONITOR)
    if not isinstance(value, bool):
        raise ConfigError("window.cross_monitor must be true or false.")
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

    _reject_unknown_keys(data, {"window", "terminal"}, "top-level")
    window = _table(data, "window")
    terminal = _table(data, "terminal")
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

    return Config(
        width=_integer(window, "width", DEFAULT_WIDTH, minimum=1),
        height=_integer(window, "height", DEFAULT_HEIGHT, minimum=1),
        margin=_integer(window, "margin", DEFAULT_MARGIN, minimum=0),
        monitor=_optional_string(window, "window", "monitor", None),
        dock_namespace=_optional_string(window, "window", "dock_namespace", None),
        max_scale=_max_scale(window),
        cross_monitor=_cross_monitor(window),
        font=_optional_string(terminal, "terminal", "font", DEFAULT_FONT)
        or DEFAULT_FONT,
        shell=_optional_string(terminal, "terminal", "shell", None),
    )
