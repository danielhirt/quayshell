"""Read monitor and layer geometry from Hyprland."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from quayshell.model import LayerGeometry, MonitorGeometry


class HyprlandError(RuntimeError):
    """Hyprland IPC returned invalid data or no data."""


@dataclass(frozen=True)
class HyprlandSnapshot:
    monitors: tuple[MonitorGeometry, ...]
    layers: tuple[LayerGeometry, ...]

    def monitor(self, requested_name: str | None = None) -> MonitorGeometry | None:
        if requested_name:
            return next(
                (item for item in self.monitors if item.name == requested_name), None
            )
        return next(
            (item for item in self.monitors if item.focused),
            self.monitors[0] if self.monitors else None,
        )

    def monitor_at(self, x: int, y: int) -> MonitorGeometry | None:
        return next(
            (
                item
                for item in self.monitors
                if item.x <= x < item.right and item.y <= y < item.bottom
            ),
            None,
        )

    def layer(self, namespace: str, monitor_name: str) -> LayerGeometry | None:
        return next(
            (
                item
                for item in self.layers
                if item.namespace == namespace and item.monitor == monitor_name
            ),
            None,
        )


def parse_monitors(data: Any) -> tuple[MonitorGeometry, ...]:
    if not isinstance(data, list):
        raise HyprlandError("Hyprland monitor data is not a list.")
    try:
        return tuple(MonitorGeometry.from_hyprland(item) for item in data)
    except (KeyError, TypeError, ValueError) as error:
        raise HyprlandError("Hyprland monitor data has an invalid field.") from error


def parse_layers(data: Any) -> tuple[LayerGeometry, ...]:
    if not isinstance(data, dict):
        raise HyprlandError("Hyprland layer data is not an object.")

    layers: list[LayerGeometry] = []
    try:
        for monitor_name, monitor_data in data.items():
            levels = monitor_data.get("levels", {})
            for surfaces in levels.values():
                for surface in surfaces:
                    layers.append(
                        LayerGeometry(
                            namespace=str(surface.get("namespace", "")),
                            monitor=str(monitor_name),
                            x=int(surface["x"]),
                            y=int(surface["y"]),
                            width=int(surface["w"]),
                            height=int(surface["h"]),
                        )
                    )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise HyprlandError("Hyprland layer data has an invalid field.") from error
    return tuple(layers)


def parse_cursor_position(data: Any) -> tuple[int, int]:
    if not isinstance(data, dict):
        raise HyprlandError("Hyprland cursor data is not an object.")
    try:
        return int(data["x"]), int(data["y"])
    except (KeyError, TypeError, ValueError) as error:
        raise HyprlandError("Hyprland cursor data has an invalid field.") from error


def _run_hyprctl(arguments: list[str]) -> Any:
    try:
        result = subprocess.run(
            ["hyprctl", "-j", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=0.75,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise HyprlandError("Cannot read Hyprland IPC data.") from error

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise HyprlandError("Hyprland returned invalid JSON.") from error


class HyprlandClient:
    def __init__(self, runner: Callable[[list[str]], Any] = _run_hyprctl):
        self._runner = runner

    def snapshot(self) -> HyprlandSnapshot:
        return HyprlandSnapshot(
            monitors=parse_monitors(self._runner(["monitors"])),
            layers=parse_layers(self._runner(["layers"])),
        )

    def cursor_position(self) -> tuple[int, int]:
        return parse_cursor_position(self._runner(["cursorpos"]))
