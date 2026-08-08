"""Report runtime support and optional compositor capabilities."""

from __future__ import annotations

import os
import platform
import shutil
from ctypes import CDLL
from ctypes.util import find_library
from dataclasses import dataclass
from pathlib import Path

from quayshell.sandbox import resolve_host_shell, running_in_flatpak


@dataclass(frozen=True)
class DiagnosticItem:
    name: str
    state: str
    detail: str
    required: bool = False


@dataclass(frozen=True)
class DiagnosticReport:
    items: tuple[DiagnosticItem, ...]

    @property
    def supported(self) -> bool:
        return all(item.state == "ok" for item in self.items if item.required)

    def render(self) -> str:
        return "\n".join(
            f"[{item.state}] {item.name}: {item.detail}" for item in self.items
        )


def collect_diagnostics(backend: str = "auto") -> DiagnosticReport:
    items: list[DiagnosticItem] = []
    linux = platform.system() == "Linux"
    items.append(
        DiagnosticItem(
            "platform",
            "ok" if linux else "error",
            platform.platform(),
            required=True,
        )
    )
    wayland = os.environ.get("WAYLAND_DISPLAY")
    items.append(
        DiagnosticItem(
            "Wayland",
            "ok" if wayland else "error",
            wayland or "WAYLAND_DISPLAY is not set",
            required=True,
        )
    )
    layer_shell = find_library("gtk4-layer-shell")
    if layer_shell:
        CDLL(layer_shell)
    items.append(
        DiagnosticItem(
            "gtk4-layer-shell",
            "ok" if layer_shell else "error",
            layer_shell or "library not found",
            required=True,
        )
    )

    try:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Gtk4LayerShell", "1.0")
        gi.require_version("Vte", "3.91")
        from gi.repository import Gtk, Gtk4LayerShell, Vte

        Gtk.init()
        layer_protocol_supported = Gtk4LayerShell.is_supported()
        toolkit_detail = (
            f"GTK {Gtk.get_major_version()}.{Gtk.get_minor_version()}, "
            f"VTE {Vte.get_major_version()}.{Vte.get_minor_version()}"
        )
        toolkit_state = "ok"
    except (ImportError, ValueError) as error:
        toolkit_detail = str(error)
        toolkit_state = "error"
        layer_protocol_supported = False
    items.append(
        DiagnosticItem(
            "GTK and VTE",
            toolkit_state,
            toolkit_detail,
            required=True,
        )
    )
    items.append(
        DiagnosticItem(
            "layer-shell protocol",
            "ok" if layer_protocol_supported else "error",
            "available"
            if layer_protocol_supported
            else "not exposed by the active compositor session",
            required=True,
        )
    )

    hyprland_available = bool(
        os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl")
    )
    sway_available = bool(os.environ.get("SWAYSOCK") and shutil.which("swaymsg"))
    if backend == "hyprland" and not hyprland_available:
        compositor = "configured Hyprland backend; active session not found"
        compositor_state = "error"
        compositor_required = True
    elif backend == "sway" and not sway_available:
        compositor = "configured Sway backend; active session not found"
        compositor_state = "error"
        compositor_required = True
    elif backend == "generic":
        compositor = "configured generic Wayland feature set"
        compositor_state = "ok"
        compositor_required = False
    elif backend == "hyprland" or (
        backend == "auto"
        and os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
        and hyprland_available
    ):
        compositor = "Hyprland; full feature set"
        compositor_state = "ok"
        compositor_required = False
    elif backend == "sway" or (
        backend == "auto" and os.environ.get("SWAYSOCK") and sway_available
    ):
        compositor = "Sway; generic movement, no global-pointer features"
        compositor_state = "ok"
        compositor_required = False
    else:
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "unknown")
        compositor = f"{desktop}; generic Wayland feature set"
        compositor_state = "warning"
        compositor_required = False
    items.append(
        DiagnosticItem(
            "compositor",
            compositor_state,
            compositor,
            required=compositor_required,
        )
    )

    shell = os.environ.get("SHELL", "")
    if running_in_flatpak():
        try:
            shell = resolve_host_shell()
            flatpak_shell_state = "ok"
            flatpak_shell_detail = f"host commands use {shell}"
        except RuntimeError as error:
            flatpak_shell_state = "error"
            flatpak_shell_detail = str(error)
        items.append(
            DiagnosticItem(
                "Flatpak host shell",
                flatpak_shell_state,
                flatpak_shell_detail,
                required=True,
            )
        )
    shell_name = Path(shell).name
    shell_supported = shell_name in {"bash", "zsh"}
    items.append(
        DiagnosticItem(
            "shell integration",
            "ok" if shell_supported else "warning",
            f"{shell or 'unknown'}; "
            + ("full command tracking" if shell_supported else "VTE fallback tracking"),
        )
    )
    gapplication = shutil.which("gapplication")
    items.append(
        DiagnosticItem(
            "remote actions",
            "ok" if gapplication else "warning",
            gapplication or "gapplication not found",
        )
    )
    return DiagnosticReport(tuple(items))
