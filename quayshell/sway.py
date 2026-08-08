"""Read output geometry from Sway IPC."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from quayshell.compositor import Capability, CompositorError, CompositorSnapshot
from quayshell.model import MonitorGeometry


class SwayError(CompositorError):
    """Sway IPC returned invalid data or no data."""


def parse_sway_outputs(
    outputs: Any,
    workspaces: Any,
) -> tuple[MonitorGeometry, ...]:
    if not isinstance(outputs, list) or not isinstance(workspaces, list):
        raise SwayError("Sway output or workspace data has an invalid type.")
    focused_outputs = {
        str(workspace.get("output"))
        for workspace in workspaces
        if isinstance(workspace, dict) and workspace.get("focused") is True
    }
    monitors: list[MonitorGeometry] = []
    try:
        for output in outputs:
            if not output.get("active", True):
                continue
            rect = output["rect"]
            monitors.append(
                MonitorGeometry(
                    name=str(output["name"]),
                    x=int(rect["x"]),
                    y=int(rect["y"]),
                    width=int(rect["width"]),
                    height=int(rect["height"]),
                    focused=str(output["name"]) in focused_outputs,
                )
            )
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise SwayError("Sway output data has an invalid field.") from error
    return tuple(monitors)


def _run_swaymsg(arguments: list[str]) -> Any:
    try:
        result = subprocess.run(
            ["swaymsg", *arguments],
            check=True,
            capture_output=True,
            text=True,
            timeout=0.75,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise SwayError("Cannot read Sway IPC data.") from error
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SwayError("Sway returned invalid JSON.") from error


class SwayClient:
    name = "sway"
    capabilities = frozenset({Capability.OUTPUTS})

    def __init__(self, runner: Callable[[list[str]], Any] = _run_swaymsg):
        self._runner = runner

    def snapshot(self) -> CompositorSnapshot:
        outputs = self._runner(["-t", "get_outputs", "-r"])
        workspaces = self._runner(["-t", "get_workspaces", "-r"])
        return CompositorSnapshot(parse_sway_outputs(outputs, workspaces))

    def cursor_position(self) -> tuple[int, int]:
        raise SwayError("Sway IPC does not provide global cursor coordinates.")
