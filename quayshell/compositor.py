"""Compositor capabilities and backend selection."""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from quayshell.model import LayerGeometry, MonitorGeometry


class Capability(Enum):
    OUTPUTS = "outputs"
    GLOBAL_CURSOR = "global-cursor"
    LAYERS = "layers"
    RESERVED_EDGES = "reserved-edges"
    CROSS_OUTPUT_DRAG = "cross-output-drag"
    SUMMON_TO_POINTER = "summon-to-pointer"
    DOCK_TRACKING = "dock-tracking"


class CompositorError(RuntimeError):
    """A compositor backend cannot provide requested data."""


@dataclass(frozen=True)
class CompositorSnapshot:
    monitors: tuple[MonitorGeometry, ...]
    layers: tuple[LayerGeometry, ...] = ()

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


class CompositorBackend(Protocol):
    name: str
    capabilities: frozenset[Capability]

    def snapshot(self) -> CompositorSnapshot: ...

    def cursor_position(self) -> tuple[int, int]: ...


class GdkBackend:
    name = "generic-wayland"
    capabilities = frozenset({Capability.OUTPUTS})

    def __init__(self, snapshot_provider: Callable[[], CompositorSnapshot]):
        self._snapshot_provider = snapshot_provider

    def snapshot(self) -> CompositorSnapshot:
        return self._snapshot_provider()

    def cursor_position(self) -> tuple[int, int]:
        raise CompositorError("The generic Wayland backend has no global cursor data.")


def select_backend(
    gdk_snapshot_provider: Callable[[], CompositorSnapshot],
    preferred: str = "auto",
) -> CompositorBackend:
    if preferred == "generic":
        return GdkBackend(gdk_snapshot_provider)
    if preferred == "hyprland":
        if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") or not shutil.which(
            "hyprctl"
        ):
            raise CompositorError(
                "The configured Hyprland backend needs an active Hyprland session."
            )
        from quayshell.hyprland import HyprlandClient

        return HyprlandClient()
    if preferred == "sway":
        if not os.environ.get("SWAYSOCK") or not shutil.which("swaymsg"):
            raise CompositorError(
                "The configured Sway backend needs an active Sway session."
            )
        from quayshell.sway import SwayClient

        return SwayClient()
    if preferred != "auto":
        raise CompositorError(f"Unknown compositor backend: {preferred}.")
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        from quayshell.hyprland import HyprlandClient

        return HyprlandClient()
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        from quayshell.sway import SwayClient

        return SwayClient()
    return GdkBackend(gdk_snapshot_provider)
