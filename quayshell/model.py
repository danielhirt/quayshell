"""Geometry types and placement rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MonitorGeometry:
    name: str
    x: int
    y: int
    width: int
    height: int
    reserved_left: int = 0
    reserved_top: int = 0
    reserved_right: int = 0
    reserved_bottom: int = 0
    focused: bool = False

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    @classmethod
    def from_hyprland(cls, data: dict[str, Any]) -> MonitorGeometry:
        scale = float(data.get("scale", 1.0)) or 1.0
        transform = int(data.get("transform", 0))
        physical_width = int(data["width"])
        physical_height = int(data["height"])
        if transform in {1, 3, 5, 7}:
            physical_width, physical_height = physical_height, physical_width

        reserved = list(data.get("reserved", [0, 0, 0, 0]))
        reserved.extend([0] * (4 - len(reserved)))
        return cls(
            name=str(data["name"]),
            x=int(data.get("x", 0)),
            y=int(data.get("y", 0)),
            width=round(physical_width / scale),
            height=round(physical_height / scale),
            reserved_left=int(reserved[0]),
            reserved_top=int(reserved[1]),
            reserved_right=int(reserved[2]),
            reserved_bottom=int(reserved[3]),
            focused=bool(data.get("focused", False)),
        )


@dataclass(frozen=True)
class LayerGeometry:
    namespace: str
    monitor: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class PanelPlacement:
    width: int
    height: int
    right_margin: int
    bottom_margin: int


@dataclass(frozen=True)
class PanelPosition:
    x: int
    y: int


@dataclass(frozen=True)
class PanelSize:
    width: int
    height: int


@dataclass(frozen=True)
class PanelGeometry:
    position: PanelPosition
    size: PanelSize


@dataclass(frozen=True)
class WindowControlVisibility:
    resize_handle: bool
    drag_handle: bool
    close_button: bool


def window_controls_for_pointer(
    panel_width: int,
    pointer_x: float,
    pointer_y: float,
    *,
    top_zone_height: int = 40,
    drag_zone_half_width: int = 72,
    resize_zone_width: int = 64,
    close_zone_width: int = 64,
) -> WindowControlVisibility:
    if panel_width <= 0 or pointer_x < 0 or pointer_y < 0:
        return WindowControlVisibility(False, False, False)

    resize_handle = pointer_y <= top_zone_height and pointer_x <= resize_zone_width
    close_button = (
        pointer_y <= top_zone_height and pointer_x >= panel_width - close_zone_width
    )
    drag_handle = (
        not resize_handle
        and not close_button
        and pointer_y <= top_zone_height
        and abs(pointer_x - panel_width / 2) <= drag_zone_half_width
    )
    return WindowControlVisibility(resize_handle, drag_handle, close_button)


def position_from_placement(
    monitor: MonitorGeometry,
    placement: PanelPlacement,
) -> PanelPosition:
    return PanelPosition(
        x=monitor.width - placement.right_margin - placement.width,
        y=monitor.height - placement.bottom_margin - placement.height,
    )


def clamp_panel_position(
    monitor: MonitorGeometry,
    position: PanelPosition,
    *,
    panel_width: int,
    panel_height: int,
) -> PanelPosition:
    min_x = monitor.reserved_left
    min_y = monitor.reserved_top
    max_x = max(min_x, monitor.width - monitor.reserved_right - panel_width)
    max_y = max(min_y, monitor.height - monitor.reserved_bottom - panel_height)
    return PanelPosition(
        x=min(max(position.x, min_x), max_x),
        y=min(max(position.y, min_y), max_y),
    )


def snap_panel_position(
    monitor: MonitorGeometry,
    position: PanelPosition,
    *,
    panel_width: int,
    panel_height: int,
    distance: int,
) -> PanelPosition:
    """Snap a panel to nearby usable monitor edges."""
    bounded = clamp_panel_position(
        monitor,
        position,
        panel_width=panel_width,
        panel_height=panel_height,
    )
    left = monitor.reserved_left
    top = monitor.reserved_top
    right = max(left, monitor.width - monitor.reserved_right - panel_width)
    bottom = max(top, monitor.height - monitor.reserved_bottom - panel_height)
    x = bounded.x
    y = bounded.y
    if x - left <= distance:
        x = left
    elif right - x <= distance:
        x = right
    if y - top <= distance:
        y = top
    elif bottom - y <= distance:
        y = bottom
    return PanelPosition(x, y)


def resize_from_top_left(
    monitor: MonitorGeometry,
    desired_position: PanelPosition,
    *,
    fixed_right: int,
    fixed_bottom: int,
    min_width: int,
    min_height: int,
    max_width: int,
    max_height: int,
) -> PanelGeometry:
    available_width = max(1, fixed_right - monitor.reserved_left)
    available_height = max(1, fixed_bottom - monitor.reserved_top)
    bounded_max_width = min(max(min_width, max_width), available_width)
    bounded_max_height = min(max(min_height, max_height), available_height)
    bounded_min_width = min(min_width, bounded_max_width)
    bounded_min_height = min(min_height, bounded_max_height)

    width = min(
        max(fixed_right - desired_position.x, bounded_min_width),
        bounded_max_width,
    )
    height = min(
        max(fixed_bottom - desired_position.y, bounded_min_height),
        bounded_max_height,
    )
    return PanelGeometry(
        position=PanelPosition(fixed_right - width, fixed_bottom - height),
        size=PanelSize(width, height),
    )


def placement_beside_bottom_dock(
    monitor: MonitorGeometry,
    dock: LayerGeometry,
    *,
    min_width: int = 160,
    edge_tolerance: int = 16,
) -> PanelPlacement | None:
    """Return a panel placement to the right of a bottom dock."""
    if dock.monitor != monitor.name or dock.width <= 0 or dock.height <= 0:
        return None
    if dock.x < monitor.x or dock.right > monitor.right:
        return None

    bottom_gap = monitor.bottom - dock.bottom
    if bottom_gap < 0 or bottom_gap > edge_tolerance:
        return None

    width = monitor.right - dock.right
    if width < min_width:
        return None

    return PanelPlacement(
        width=width,
        height=min(dock.height, monitor.height),
        right_margin=0,
        bottom_margin=bottom_gap,
    )
