"""GTK4, VTE4, and layer-shell application."""

from __future__ import annotations

import logging
import os
import pwd
import shlex
import time
from ctypes import CDLL
from ctypes.util import find_library
from pathlib import Path

# gtk4-layer-shell must load before GTK links to the Wayland client library.
CDLL(find_library("gtk4-layer-shell") or "libgtk4-layer-shell.so")

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0")
gi.require_version("Vte", "3.91")

from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte
from gi.repository import Gtk4LayerShell as LayerShell

from quayshell.activity import ActivityPhase, ActivityTracker, foreground_command
from quayshell.cli import Options
from quayshell.compositor import (
    Capability,
    CompositorError,
    CompositorSnapshot,
    select_backend,
)
from quayshell.model import (
    MonitorGeometry,
    PanelPlacement,
    PanelPosition,
    clamp_panel_position,
    placement_beside_bottom_dock,
    position_from_placement,
    resize_from_top_left,
    snap_panel_position,
    window_controls_for_pointer,
)
from quayshell.sandbox import (
    host_spawn_arguments,
    resolve_host_shell,
    running_in_flatpak,
    stage_shell_integration,
)

APP_ID = "dev.danielh.quayshell"
LAYER_NAMESPACE = "quayshell"
POLL_INTERVAL_SECONDS = 1
DRAG_INTERVAL_MILLISECONDS = 33
ACTIVITY_INTERVAL_MILLISECONDS = 100
SHELL_PREEXEC_TERMPROP = "vte.ext.quayshell.shell.preexec"
SHELL_POSTEXEC_TERMPROP = "vte.ext.quayshell.shell.postexec"

Vte.install_termprop(
    SHELL_PREEXEC_TERMPROP,
    Vte.PropertyType.VALUELESS,
    Vte.PropertyFlags.EPHEMERAL,
)
Vte.install_termprop(
    SHELL_POSTEXEC_TERMPROP,
    Vte.PropertyType.UINT,
    Vte.PropertyFlags.EPHEMERAL,
)

logger = logging.getLogger(__name__)


def _rgba(value: str) -> Gdk.RGBA:
    color = Gdk.RGBA()
    if not color.parse(value):
        raise ValueError(f"Invalid color: {value}")
    return color


class QuayshellWindow(Gtk.ApplicationWindow):
    def __init__(self, options: Options, **kwargs):
        super().__init__(**kwargs)
        self.options = options
        self._flatpak = running_in_flatpak()
        self._integration_path = Path(__file__).with_name("shell_integration")
        if self._flatpak:
            cache_home = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
            self._integration_path = stage_shell_integration(
                self._integration_path, cache_home
            )
        self._shell_path = self._resolve_shell()
        self.expanded = False
        self.snapshot: CompositorSnapshot | None = None
        self.monitor_geometry: MonitorGeometry | None = None
        self.monitor_name: str | None = options.monitor
        self.compositor = select_backend(self._gdk_snapshot, options.backend)
        self._home_monitor_name: str | None = None

        self._panel_position = PanelPosition(0, 0)
        self._panel_width = options.width
        self._panel_height = options.height
        self._manual_position: PanelPosition | None = None
        self._manual_size: tuple[int, int] | None = None
        self._drag_active = False
        self._drag_source_id: int | None = None
        self._drag_pointer_offset = (0, 0)
        self._drag_start_position = PanelPosition(0, 0)
        self._drag_size = (options.width, options.height)
        self._drag_crossed_monitor = False
        self._resize_active = False
        self._resize_source_id: int | None = None
        self._resize_pointer_offset = (0, 0)
        self._resize_fixed_right = 0
        self._resize_fixed_bottom = 0
        self._resize_start_size = (options.width, options.height)
        self._resize_start_position = PanelPosition(0, 0)
        self._resize_base_size: tuple[int, int] | None = None
        self._activity = ActivityTracker()
        self._shell_pid: int | None = None
        self._smart_collapsed = False

        self.set_title("Quayshell")
        self.set_icon_name(APP_ID)
        self.set_decorated(False)

        self._read_compositor()
        self._home_monitor_name = self.monitor_name
        self._configure_layer_surface()
        self.terminal = self._build_terminal()
        self.set_child(self._build_content(self.terminal))
        self._add_key_controller()
        self._apply_geometry()
        self._resize_base_size = (self._panel_width, self._panel_height)
        self._spawn_shell()
        GLib.timeout_add(
            ACTIVITY_INTERVAL_MILLISECONDS,
            self._activity_tick,
        )

        if (
            self.options.dock_namespace
            and Capability.DOCK_TRACKING in self.compositor.capabilities
        ):
            GLib.timeout_add_seconds(POLL_INTERVAL_SECONDS, self._poll_geometry)

    def _configure_layer_surface(self) -> None:
        LayerShell.init_for_window(self)
        LayerShell.set_namespace(self, LAYER_NAMESPACE)
        LayerShell.set_layer(self, LayerShell.Layer.OVERLAY)
        LayerShell.set_keyboard_mode(self, LayerShell.KeyboardMode.ON_DEMAND)
        LayerShell.set_exclusive_zone(self, -1)

        if self.monitor_name:
            monitor = self._gdk_monitor(self.monitor_name)
            if monitor is None:
                logger.warning("Wayland output %s is unavailable.", self.monitor_name)
            else:
                LayerShell.set_monitor(self, monitor)

    def _gdk_monitor(self, connector: str) -> Gdk.Monitor | None:
        display = Gdk.Display.get_default()
        if display is None:
            return None
        monitors = display.get_monitors()
        for index in range(monitors.get_n_items()):
            monitor = monitors.get_item(index)
            if monitor is None:
                continue
            name = monitor.get_connector() or f"output-{index + 1}"
            if name == connector:
                return monitor
        return None

    def _gdk_snapshot(self) -> CompositorSnapshot:
        display = Gdk.Display.get_default()
        if display is None:
            raise CompositorError("GDK has no active display.")
        models = display.get_monitors()
        monitors: list[MonitorGeometry] = []
        for index in range(models.get_n_items()):
            monitor = models.get_item(index)
            if monitor is None:
                continue
            geometry = monitor.get_geometry()
            name = monitor.get_connector() or f"output-{index + 1}"
            monitors.append(
                MonitorGeometry(
                    name=name,
                    x=geometry.x,
                    y=geometry.y,
                    width=geometry.width,
                    height=geometry.height,
                    focused=name == self.monitor_name
                    or (self.monitor_name is None and not monitors),
                )
            )
        return CompositorSnapshot(tuple(monitors))

    def _build_content(self, terminal: Vte.Terminal) -> Gtk.Widget:
        frame = Gtk.Overlay()
        frame.add_css_class("quayshell-frame")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_child(terminal)

        self.activity_label = Gtk.Label()
        self.activity_label.add_css_class("activity-label")
        self.activity_label.set_halign(Gtk.Align.START)
        self.activity_label.set_valign(Gtk.Align.START)
        self.activity_label.set_margin_top(2)
        self.activity_label.set_margin_start(26)
        self.activity_label.set_width_chars(15)
        self.activity_label.set_max_width_chars(15)
        self.activity_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.activity_label.set_can_target(False)
        frame.add_overlay(self.activity_label)

        self.mascot_label = Gtk.Label(label=self._activity.mascot())
        self.mascot_label.add_css_class("status-mascot")
        self.mascot_label.set_halign(Gtk.Align.END)
        self.mascot_label.set_valign(Gtk.Align.START)
        self.mascot_label.set_margin_top(1)
        self.mascot_label.set_margin_end(31)
        self.mascot_label.set_can_target(False)
        self.mascot_label.set_visible(self.options.mascot)
        frame.add_overlay(self.mascot_label)

        self.resize_handle = Gtk.Box()
        self.resize_handle.add_css_class("resize-handle")
        self.resize_handle.set_size_request(16, 16)
        self.resize_handle.set_halign(Gtk.Align.START)
        self.resize_handle.set_valign(Gtk.Align.START)
        self.resize_handle.set_margin_top(4)
        self.resize_handle.set_margin_start(4)
        self.resize_handle.set_cursor_from_name("nw-resize")
        frame.add_overlay(self.resize_handle)

        self.drag_handle = Gtk.Box()
        self.drag_handle.add_css_class("drag-handle")
        self.drag_handle.set_size_request(44, 8)
        self.drag_handle.set_halign(Gtk.Align.CENTER)
        self.drag_handle.set_valign(Gtk.Align.START)
        self.drag_handle.set_margin_top(4)
        self.drag_handle.set_cursor_from_name("grab")
        frame.add_overlay(self.drag_handle)

        self.close_button = Gtk.Button(label="×")
        self.close_button.add_css_class("close-button")
        self.close_button.set_halign(Gtk.Align.END)
        self.close_button.set_valign(Gtk.Align.START)
        self.close_button.set_margin_top(4)
        self.close_button.set_margin_end(4)
        self.close_button.set_focus_on_click(False)
        self.close_button.set_tooltip_text("Quit Quayshell")
        self.close_button.connect("clicked", self._quit)
        frame.add_overlay(self.close_button)

        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self._update_window_controls)
        motion.connect("motion", self._update_window_controls)
        motion.connect("leave", self._hide_window_controls)
        self.add_controller(motion)

        resize = Gtk.GestureDrag()
        resize.set_button(1)
        resize.connect("drag-begin", self._on_resize_begin)
        resize.connect("drag-update", self._on_resize_update)
        resize.connect("drag-end", self._on_resize_end)
        self.resize_handle.add_controller(resize)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.drag_handle.add_controller(drag)

        self._set_window_controls_visible(
            resize_handle=False,
            drag_handle=False,
            close_button=False,
        )
        return frame

    @staticmethod
    def _set_control_visible(widget: Gtk.Widget, visible: bool) -> None:
        widget.set_opacity(1.0 if visible else 0.0)
        widget.set_can_target(visible)

    def _set_window_controls_visible(
        self,
        *,
        resize_handle: bool,
        drag_handle: bool,
        close_button: bool,
    ) -> None:
        self._set_control_visible(self.resize_handle, resize_handle)
        self._set_control_visible(self.drag_handle, drag_handle)
        self._set_control_visible(self.close_button, close_button)

    def _update_window_controls(
        self,
        _controller: Gtk.EventControllerMotion,
        pointer_x: float,
        pointer_y: float,
    ) -> None:
        if self._drag_active or self._resize_active:
            self._set_window_controls_visible(
                resize_handle=self._resize_active,
                drag_handle=self._drag_active,
                close_button=False,
            )
            return

        panel_width = max(self.get_width(), self._panel_width)
        visibility = window_controls_for_pointer(
            panel_width,
            pointer_x,
            pointer_y,
        )
        self._set_window_controls_visible(
            resize_handle=visibility.resize_handle,
            drag_handle=visibility.drag_handle,
            close_button=visibility.close_button,
        )

    def _hide_window_controls(
        self,
        _controller: Gtk.EventControllerMotion,
    ) -> None:
        if not self._drag_active and not self._resize_active:
            self._set_window_controls_visible(
                resize_handle=False,
                drag_handle=False,
                close_button=False,
            )

    def _quit(self, _button: Gtk.Button | None = None) -> None:
        application = self.get_application()
        if application:
            application.quit()

    def _build_terminal(self) -> Vte.Terminal:
        terminal = Vte.Terminal()
        terminal.set_hexpand(True)
        terminal.set_vexpand(True)
        terminal.set_font(Pango.FontDescription.from_string(self.options.font))
        terminal.set_scrollback_lines(10_000)
        terminal.set_scroll_on_output(False)
        terminal.set_scroll_on_keystroke(True)
        terminal.set_mouse_autohide(True)
        terminal.set_audible_bell(False)
        terminal.set_cursor_blink_mode(Vte.CursorBlinkMode.ON)

        foreground = _rgba("#dce4ee")
        background = _rgba("rgba(6, 10, 16, 0)")
        palette = [
            _rgba(value)
            for value in (
                "#121821",
                "#d6636f",
                "#78b892",
                "#d5ad68",
                "#6096c8",
                "#a985c0",
                "#60b7b2",
                "#c9d1db",
                "#536171",
                "#ed7c86",
                "#91c9a5",
                "#e3c27e",
                "#7aaddb",
                "#bd9bd1",
                "#7accc6",
                "#edf2f7",
            )
        ]
        terminal.set_colors(foreground, background, palette)
        shell_name = Path(self._shell_path).name
        if shell_name in {"bash", "zsh"}:
            preexec_prop = SHELL_PREEXEC_TERMPROP
            postexec_prop = SHELL_POSTEXEC_TERMPROP
        else:
            preexec_prop = Vte.TERMPROP_SHELL_PREEXEC
            postexec_prop = Vte.TERMPROP_SHELL_POSTEXEC
        terminal.connect(
            f"termprop-changed::{preexec_prop}",
            self._on_shell_preexec,
        )
        terminal.connect(
            f"termprop-changed::{postexec_prop}",
            self._on_shell_postexec,
        )
        return terminal

    def _on_shell_preexec(
        self,
        _terminal: Vte.Terminal,
        _name: str,
    ) -> None:
        GLib.idle_add(self._command_started)

    def _on_shell_postexec(
        self,
        terminal: Vte.Terminal,
        name: str,
    ) -> None:
        is_set, status = terminal.get_termprop_uint(name)
        if is_set:
            GLib.idle_add(self._command_finished, int(status))

    def _command_started(self) -> bool:
        if self._activity.phase is ActivityPhase.RUNNING:
            return GLib.SOURCE_REMOVE
        self._activity.start(time.monotonic())
        if self.options.smart_collapse and self.expanded:
            self.expanded = False
            self._smart_collapsed = True
            self._apply_geometry()
        self._update_activity_display()
        return GLib.SOURCE_REMOVE

    def _command_finished(self, status: int) -> bool:
        completion = self._activity.finish(status, time.monotonic())
        if completion is None:
            return GLib.SOURCE_REMOVE
        self._update_activity_display()

        if (
            self.options.notify_on_completion
            and completion.duration >= self.options.notification_after_seconds
        ):
            notification = Gio.Notification.new("Quayshell command finished")
            command_name = completion.command.split(maxsplit=1)[0]
            if completion.status == 0:
                notification.set_body(
                    f"{command_name} finished in {completion.duration:.1f}s."
                )
            else:
                notification.set_body(
                    f"{command_name} exited with status {completion.status}."
                )
            notification.set_default_action("app.summon")
            application = self.get_application()
            if application:
                application.send_notification("command-completion", notification)

        if self._smart_collapsed:
            if status != 0 and self.options.expand_on_failure:
                self.expanded = True
                self._apply_geometry()
            self._smart_collapsed = False
        return GLib.SOURCE_REMOVE

    def _activity_tick(self) -> bool:
        now = time.monotonic()
        if self._activity.phase is ActivityPhase.RUNNING:
            pty = self.terminal.get_pty()
            if pty is not None:
                self._activity.set_command(
                    foreground_command(pty.get_fd(), self._shell_pid)
                )
        else:
            self._activity.reset_if_expired(now, self.options.result_seconds)
        self._update_activity_display(now)
        return GLib.SOURCE_CONTINUE

    def _update_activity_display(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self.activity_label.set_label(self._activity.label(now))
        self.activity_label.set_visible(self._activity.phase is not ActivityPhase.IDLE)
        self.mascot_label.set_label(self._activity.mascot())
        for css_class in ("running", "success", "failure"):
            self.activity_label.remove_css_class(css_class)
            self.mascot_label.remove_css_class(css_class)
        if self._activity.phase is not ActivityPhase.IDLE:
            css_class = self._activity.phase.value
            self.activity_label.add_css_class(css_class)
            self.mascot_label.add_css_class(css_class)

    def _add_key_controller(self) -> None:
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(controller)

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        state: Gdk.ModifierType,
    ) -> bool:
        modifiers = state & (
            Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.ALT_MASK
            | Gdk.ModifierType.SUPER_MASK
        )
        control_shift = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK

        if keyval == Gdk.KEY_F11 or (
            keyval in {Gdk.KEY_e, Gdk.KEY_E} and modifiers == control_shift
        ):
            self.expanded = not self.expanded
            self._read_compositor()
            self._apply_geometry()
            return True
        if keyval in {Gdk.KEY_c, Gdk.KEY_C} and modifiers == control_shift:
            self.terminal.copy_clipboard_format(Vte.Format.TEXT)
            return True
        if keyval in {Gdk.KEY_v, Gdk.KEY_V} and modifiers == control_shift:
            self.terminal.paste_clipboard()
            return True
        if keyval in {Gdk.KEY_q, Gdk.KEY_Q} and modifiers == control_shift:
            self._quit()
            return True
        return False

    def _resolve_shell(self) -> str:
        if self._flatpak:
            return resolve_host_shell(self.options.shell)
        shell = (
            self.options.shell
            or os.environ.get("SHELL")
            or pwd.getpwuid(os.getuid()).pw_shell
        )
        if not os.path.isabs(shell) or not os.access(shell, os.X_OK):
            raise RuntimeError(f"The shell is not executable: {shell}")
        return shell

    def _shell_arguments(self) -> list[str]:
        shell = self._shell_path
        shell_name = Path(shell).name
        if shell_name == "bash":
            bash_init = self._integration_path / "bash"
            command = (
                f"exec {shlex.quote(shell)} --noprofile "
                f"--rcfile {shlex.quote(str(bash_init))} -i"
            )
            return [shell, "-l", "-c", command]
        if shell_name == "zsh":
            zsh_dir = self._integration_path / "zsh"
            command = (
                f"exec env ZDOTDIR={shlex.quote(str(zsh_dir))} {shlex.quote(shell)} -i"
            )
            return [shell, "-l", "-c", command]
        return [shell, "-l"]

    def _spawn_shell(self) -> None:
        shell = self._shell_path
        environment = os.environ.copy()
        environment.update(
            {
                "SHELL": shell,
                "TERM": "xterm-256color",
                "COLORTERM": "truecolor",
                "TERM_PROGRAM": "quayshell",
            }
        )
        environment_list = [f"{key}={value}" for key, value in environment.items()]
        arguments = self._shell_arguments()
        if self._flatpak:
            arguments = host_spawn_arguments(
                arguments,
                {
                    "SHELL": shell,
                    "TERM": "xterm-256color",
                    "COLORTERM": "truecolor",
                    "TERM_PROGRAM": "quayshell",
                },
            )

        self.terminal.connect("child-exited", self._on_child_exited)
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(Path.home()),
            arguments,
            environment_list,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            self._on_spawned,
            None,
        )

    def _on_spawned(
        self,
        _terminal: Vte.Terminal,
        pid: int,
        error: GLib.Error | None,
        _user_data: object = None,
    ) -> None:
        if error is not None:
            logger.error("Cannot start the shell: %s", error.message)
            self._quit()
            return
        self._shell_pid = pid

    def _on_child_exited(self, _terminal: Vte.Terminal, _status: int) -> None:
        self._quit()

    def _read_compositor(self) -> None:
        try:
            snapshot = self.compositor.snapshot()
        except CompositorError as error:
            logger.warning(
                "%s geometry is unavailable: %s",
                self.compositor.name,
                error,
            )
            try:
                snapshot = self._gdk_snapshot()
            except CompositorError:
                return

        self.snapshot = snapshot
        monitor = snapshot.monitor(self.monitor_name)
        if monitor is None:
            if self.monitor_name:
                logger.warning("Wayland output %s is unavailable.", self.monitor_name)
            self.monitor_geometry = None
            return

        self.monitor_geometry = monitor
        if self.monitor_name is None:
            self.monitor_name = monitor.name

    def _collapsed_placement(self) -> PanelPlacement:
        if (
            self.snapshot
            and self.monitor_geometry
            and self.options.dock_namespace
            and Capability.DOCK_TRACKING in self.compositor.capabilities
        ):
            dock = self.snapshot.layer(
                self.options.dock_namespace, self.monitor_geometry.name
            )
            if dock:
                placement = placement_beside_bottom_dock(self.monitor_geometry, dock)
                if placement:
                    return placement
        return PanelPlacement(
            width=self.options.width,
            height=self.options.height,
            right_margin=self.options.margin,
            bottom_margin=self.options.margin,
        )

    def _set_anchors(
        self,
        *,
        left: bool,
        top: bool,
        right: bool,
        bottom: bool,
    ) -> None:
        LayerShell.set_anchor(self, LayerShell.Edge.LEFT, left)
        LayerShell.set_anchor(self, LayerShell.Edge.TOP, top)
        LayerShell.set_anchor(self, LayerShell.Edge.RIGHT, right)
        LayerShell.set_anchor(self, LayerShell.Edge.BOTTOM, bottom)

    def _set_margins(
        self,
        *,
        left: int = 0,
        top: int = 0,
        right: int = 0,
        bottom: int = 0,
    ) -> None:
        LayerShell.set_margin(self, LayerShell.Edge.LEFT, left)
        LayerShell.set_margin(self, LayerShell.Edge.TOP, top)
        LayerShell.set_margin(self, LayerShell.Edge.RIGHT, right)
        LayerShell.set_margin(self, LayerShell.Edge.BOTTOM, bottom)

    def _apply_geometry(self) -> None:
        placement = self._collapsed_placement()
        if self._manual_size:
            width, height = self._manual_size
        else:
            width, height = placement.width, placement.height
        self._panel_width = width
        self._panel_height = height

        monitor = self.monitor_geometry
        if self._manual_position and monitor:
            self._manual_position = clamp_panel_position(
                monitor,
                self._manual_position,
                panel_width=width,
                panel_height=height,
            )

        if self.expanded:
            top_margin = monitor.reserved_top if monitor else 0
            bottom_margin = (
                monitor.reserved_bottom if monitor else placement.bottom_margin
            )
            if self._manual_position:
                self._set_anchors(left=True, top=True, right=False, bottom=True)
                self._set_margins(
                    left=self._manual_position.x,
                    top=top_margin,
                    bottom=bottom_margin,
                )
                self._panel_position = PanelPosition(
                    self._manual_position.x,
                    top_margin,
                )
            else:
                self._set_anchors(left=False, top=True, right=True, bottom=True)
                self._set_margins(
                    top=top_margin,
                    right=placement.right_margin,
                    bottom=placement.bottom_margin,
                )
                if monitor:
                    self._panel_position = PanelPosition(
                        monitor.width - placement.right_margin - width,
                        top_margin,
                    )
            self.set_default_size(width, 0)
            return

        if self._manual_position:
            self._set_anchors(left=True, top=True, right=False, bottom=False)
            self._set_margins(
                left=self._manual_position.x,
                top=self._manual_position.y,
            )
            self._panel_position = self._manual_position
        else:
            self._set_anchors(left=False, top=False, right=True, bottom=True)
            self._set_margins(
                right=placement.right_margin,
                bottom=placement.bottom_margin,
            )
            if monitor:
                self._panel_position = position_from_placement(monitor, placement)
        self.set_default_size(width, height)

    def _set_output(self, monitor: MonitorGeometry) -> bool:
        if monitor.name == self.monitor_name:
            self.monitor_geometry = monitor
            return True
        gdk_monitor = self._gdk_monitor(monitor.name)
        if gdk_monitor is None:
            logger.warning("Wayland output %s is unavailable.", monitor.name)
            return False
        LayerShell.set_monitor(self, gdk_monitor)
        self.monitor_name = monitor.name
        self.monitor_geometry = monitor
        return True

    def summon_to_pointer(self) -> None:
        if Capability.SUMMON_TO_POINTER not in self.compositor.capabilities:
            logger.warning(
                "%s does not support summon-to-pointer.", self.compositor.name
            )
            return
        self._read_compositor()
        if self.snapshot is None:
            logger.warning("Cannot summon Quayshell without compositor geometry.")
            return
        try:
            cursor_x, cursor_y = self.compositor.cursor_position()
        except CompositorError as error:
            logger.warning("Cannot summon Quayshell: %s", error)
            return
        monitor = self.snapshot.monitor_at(cursor_x, cursor_y)
        if monitor is None or not self._set_output(monitor):
            return

        width = min(
            self._panel_width,
            monitor.width - monitor.reserved_left - monitor.reserved_right,
        )
        height = min(
            self._panel_height,
            monitor.height - monitor.reserved_top - monitor.reserved_bottom,
        )
        position = PanelPosition(
            cursor_x - monitor.x - width // 2,
            cursor_y - monitor.y + 24,
        )
        self._manual_position = clamp_panel_position(
            monitor,
            position,
            panel_width=width,
            panel_height=height,
        )
        self._manual_size = (width, height)
        self._apply_geometry()
        self.present()

    def return_home(self) -> None:
        self._read_compositor()
        if self.snapshot is None:
            return
        monitor = self.snapshot.monitor(self._home_monitor_name)
        if monitor is None or not self._set_output(monitor):
            return
        self._manual_position = None
        self._manual_size = None
        self._apply_geometry()
        self.present()

    def _on_resize_begin(
        self,
        gesture: Gtk.GestureDrag,
        _start_x: float,
        _start_y: float,
    ) -> None:
        if self.expanded or self.monitor_geometry is None or self._drag_active:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        monitor = self.monitor_geometry
        self._resize_start_position = self._panel_position
        self._resize_fixed_right = self._panel_position.x + self._panel_width
        self._resize_fixed_bottom = self._panel_position.y + self._panel_height
        self._resize_start_size = (self._panel_width, self._panel_height)
        self._resize_active = True
        self.resize_handle.set_cursor_from_name("nw-resize")
        self._set_window_controls_visible(
            resize_handle=True,
            drag_handle=False,
            close_button=False,
        )

        if Capability.GLOBAL_CURSOR in self.compositor.capabilities:
            try:
                cursor_x, cursor_y = self.compositor.cursor_position()
            except CompositorError as error:
                logger.warning("Cannot start resize: %s", error)
                gesture.set_state(Gtk.EventSequenceState.DENIED)
                self._resize_active = False
                return
            self._resize_pointer_offset = (
                cursor_x - monitor.x - self._panel_position.x,
                cursor_y - monitor.y - self._panel_position.y,
            )
            self._resize_source_id = GLib.timeout_add(
                DRAG_INTERVAL_MILLISECONDS,
                self._resize_tick,
            )

    def _apply_resize_position(self, desired_position: PanelPosition) -> None:
        if self.monitor_geometry is None:
            return
        start_width, start_height = self._resize_start_size
        base_width, base_height = self._resize_base_size or self._resize_start_size
        geometry = resize_from_top_left(
            self.monitor_geometry,
            desired_position,
            fixed_right=self._resize_fixed_right,
            fixed_bottom=self._resize_fixed_bottom,
            min_width=min(base_width, start_width),
            min_height=min(base_height, start_height),
            max_width=max(start_width, round(base_width * self.options.max_scale)),
            max_height=max(start_height, round(base_height * self.options.max_scale)),
        )
        resized = (
            geometry.size.width != start_width or geometry.size.height != start_height
        )
        if resized or self._manual_size is not None:
            self._manual_position = geometry.position
            self._manual_size = (geometry.size.width, geometry.size.height)
            self._apply_geometry()

    def _on_resize_update(
        self,
        _gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if (
            not self._resize_active
            or Capability.GLOBAL_CURSOR in self.compositor.capabilities
        ):
            return
        self._apply_resize_position(
            PanelPosition(
                self._resize_start_position.x + round(offset_x),
                self._resize_start_position.y + round(offset_y),
            )
        )

    def _resize_tick(self) -> bool:
        if not self._resize_active or self.monitor_geometry is None:
            self._resize_source_id = None
            return GLib.SOURCE_REMOVE
        try:
            cursor_x, cursor_y = self.compositor.cursor_position()
        except CompositorError:
            return GLib.SOURCE_CONTINUE
        offset_x, offset_y = self._resize_pointer_offset
        self._apply_resize_position(
            PanelPosition(
                cursor_x - self.monitor_geometry.x - offset_x,
                cursor_y - self.monitor_geometry.y - offset_y,
            )
        )
        return GLib.SOURCE_CONTINUE

    def _on_resize_end(
        self,
        gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if self._resize_active:
            if Capability.GLOBAL_CURSOR in self.compositor.capabilities:
                self._resize_tick()
            else:
                self._on_resize_update(gesture, offset_x, offset_y)
        self._resize_active = False
        self.resize_handle.set_cursor_from_name("nw-resize")
        if self._resize_source_id is not None:
            GLib.source_remove(self._resize_source_id)
            self._resize_source_id = None

    def _switch_to_pointer_monitor(self, cursor_x: int, cursor_y: int) -> bool:
        if (
            not self.options.cross_monitor
            or self.snapshot is None
            or Capability.CROSS_OUTPUT_DRAG not in self.compositor.capabilities
        ):
            return False
        target = self.snapshot.monitor_at(cursor_x, cursor_y)
        if target is None or target.name == self.monitor_name:
            return False
        if not self._set_output(target):
            return False
        self._drag_crossed_monitor = True
        return True

    @staticmethod
    def _primary_button_pressed() -> bool:
        display = Gdk.Display.get_default()
        seat = display.get_default_seat() if display else None
        pointer = seat.get_pointer() if seat else None
        if pointer is None:
            return False
        return bool(pointer.get_modifier_state() & Gdk.ModifierType.BUTTON1_MASK)

    def _on_drag_begin(
        self,
        gesture: Gtk.GestureDrag,
        _start_x: float,
        _start_y: float,
    ) -> None:
        if self.expanded or self.monitor_geometry is None or self._resize_active:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        self._read_compositor()
        if self.monitor_geometry is None:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        self._drag_start_position = self._panel_position
        self._drag_size = (self._panel_width, self._panel_height)
        self._drag_crossed_monitor = False
        self._drag_active = True
        self.drag_handle.set_cursor_from_name("grabbing")

        if Capability.GLOBAL_CURSOR in self.compositor.capabilities:
            try:
                cursor_x, cursor_y = self.compositor.cursor_position()
            except CompositorError as error:
                logger.warning("Cannot start drag: %s", error)
                gesture.set_state(Gtk.EventSequenceState.DENIED)
                self._drag_active = False
                return
            monitor = self.monitor_geometry
            self._drag_pointer_offset = (
                cursor_x - monitor.x - self._panel_position.x,
                cursor_y - monitor.y - self._panel_position.y,
            )
            self._drag_source_id = GLib.timeout_add(
                DRAG_INTERVAL_MILLISECONDS,
                self._drag_tick,
            )

    def _apply_drag_position(
        self,
        position: PanelPosition,
        *,
        switched_monitor: bool = False,
    ) -> None:
        if self.monitor_geometry is None:
            return
        monitor = self.monitor_geometry
        original_width, original_height = self._drag_size
        width = min(
            original_width,
            monitor.width - monitor.reserved_left - monitor.reserved_right,
        )
        height = min(
            original_height,
            monitor.height - monitor.reserved_top - monitor.reserved_bottom,
        )
        position = clamp_panel_position(
            monitor,
            position,
            panel_width=width,
            panel_height=height,
        )
        if self.options.magnetic_docking:
            position = snap_panel_position(
                monitor,
                position,
                panel_width=width,
                panel_height=height,
                distance=self.options.snap_distance,
            )
        moved = (
            abs(position.x - self._drag_start_position.x) > 2
            or abs(position.y - self._drag_start_position.y) > 2
        )
        if switched_monitor or moved or self._manual_position is not None:
            self._manual_position = position
            self._manual_size = (width, height)
            self._apply_geometry()

    def _on_drag_update(
        self,
        _gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if (
            not self._drag_active
            or Capability.GLOBAL_CURSOR in self.compositor.capabilities
        ):
            return
        self._apply_drag_position(
            PanelPosition(
                self._drag_start_position.x + round(offset_x),
                self._drag_start_position.y + round(offset_y),
            )
        )

    def _drag_tick(self) -> bool:
        if not self._drag_active or self.monitor_geometry is None:
            self._drag_source_id = None
            return GLib.SOURCE_REMOVE
        try:
            cursor_x, cursor_y = self.compositor.cursor_position()
        except CompositorError:
            return GLib.SOURCE_CONTINUE

        switched_monitor = self._switch_to_pointer_monitor(cursor_x, cursor_y)
        offset_x, offset_y = self._drag_pointer_offset
        self._apply_drag_position(
            PanelPosition(
                cursor_x - self.monitor_geometry.x - offset_x,
                cursor_y - self.monitor_geometry.y - offset_y,
            ),
            switched_monitor=switched_monitor,
        )
        if self._drag_crossed_monitor and not self._primary_button_pressed():
            self._drag_active = False
            self._drag_source_id = None
            self.drag_handle.set_cursor_from_name("grab")
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_drag_end(
        self,
        gesture: Gtk.GestureDrag,
        offset_x: float,
        offset_y: float,
    ) -> None:
        if self._drag_crossed_monitor and self._primary_button_pressed():
            return
        if self._drag_active:
            if Capability.GLOBAL_CURSOR in self.compositor.capabilities:
                self._drag_tick()
            else:
                self._on_drag_update(gesture, offset_x, offset_y)
        self._drag_active = False
        self.drag_handle.set_cursor_from_name("grab")
        if self._drag_source_id is not None:
            GLib.source_remove(self._drag_source_id)
            self._drag_source_id = None

    def _poll_geometry(self) -> bool:
        self._read_compositor()
        self._apply_geometry()
        return GLib.SOURCE_CONTINUE


class QuayshellApplication(Gtk.Application):
    def __init__(self, options: Options):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )
        self.options = options
        self.window: QuayshellWindow | None = None
        self.startup_error = False

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        summon = Gio.SimpleAction.new("summon", None)
        summon.connect("activate", self._summon)
        self.add_action(summon)
        home = Gio.SimpleAction.new("home", None)
        home.connect("activate", self._home)
        self.add_action(home)

    def _summon(self, _action: Gio.SimpleAction, _parameter: object) -> None:
        if self.window:
            self.window.summon_to_pointer()

    def _home(self, _action: Gio.SimpleAction, _parameter: object) -> None:
        if self.window:
            self.window.return_home()

    def do_activate(self) -> None:
        if self.window is not None:
            return
        if not LayerShell.is_supported():
            logger.error("The active Wayland compositor does not support layer-shell.")
            self.startup_error = True
            self.quit()
            return
        self._load_css()
        self.window = QuayshellWindow(options=self.options, application=self)
        self.window.present()

    def _load_css(self) -> None:
        provider = Gtk.CssProvider()
        provider.load_from_path(str(Path(__file__).with_name("style.css")))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )


def run(options: Options) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(name)s: %(message)s")
    application = QuayshellApplication(options)
    status = application.run([])
    return 1 if application.startup_error else status
