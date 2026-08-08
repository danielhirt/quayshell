"""Read monitor and layer geometry from Hyprland."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from quayshell.compositor import Capability, CompositorError, CompositorSnapshot
from quayshell.model import LayerGeometry, MonitorGeometry


class HyprlandError(CompositorError):
    """Hyprland IPC returned invalid data or no data."""


HyprlandSnapshot = CompositorSnapshot


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
    name = "hyprland"
    capabilities = frozenset(
        {
            Capability.OUTPUTS,
            Capability.GLOBAL_CURSOR,
            Capability.LAYERS,
            Capability.RESERVED_EDGES,
            Capability.CROSS_OUTPUT_DRAG,
            Capability.SUMMON_TO_POINTER,
            Capability.DOCK_TRACKING,
        }
    )

    def __init__(self, runner: Callable[[list[str]], Any] = _run_hyprctl):
        self._runner = runner

    def snapshot(self) -> CompositorSnapshot:
        return CompositorSnapshot(
            monitors=parse_monitors(self._runner(["monitors"])),
            layers=parse_layers(self._runner(["layers"])),
        )

    def cursor_position(self) -> tuple[int, int]:
        return parse_cursor_position(self._runner(["cursorpos"]))
