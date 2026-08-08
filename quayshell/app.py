"""GTK4, VTE4, and layer-shell application."""

from __future__ import annotations

import logging
import os
import pwd
from ctypes import CDLL
from pathlib import Path

# gtk4-layer-shell must load before GTK links to the Wayland client library.
CDLL("libgtk4-layer-shell.so")

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
gi.require_version("Pango", "1.0")
gi.require_version("Vte", "3.91")

from gi.repository import Gdk, Gio, GLib, Gtk, Pango, Vte
from gi.repository import Gtk4LayerShell as LayerShell

from quayshell.cli import Options
from quayshell.hyprland import HyprlandClient, HyprlandError, HyprlandSnapshot
from quayshell.model import (
    MonitorGeometry,
    PanelPlacement,
    PanelPosition,
    clamp_panel_position,
    placement_beside_bottom_dock,
    position_from_placement,
    resize_from_top_left,
    window_controls_for_pointer,
)

APP_ID = "dev.danielh.quayshell"
LAYER_NAMESPACE = "quayshell"
POLL_INTERVAL_SECONDS = 1
DRAG_INTERVAL_MILLISECONDS = 33

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
        self.expanded = False
        self.hyprland = HyprlandClient()
        self.snapshot: HyprlandSnapshot | None = None
        self.monitor_geometry: MonitorGeometry | None = None
        self.monitor_name: str | None = options.monitor

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
        self._resize_base_size: tuple[int, int] | None = None

        self.set_title("Quayshell")
        self.set_decorated(False)

        self._read_hyprland()
        self._configure_layer_surface()
        self.terminal = self._build_terminal()
        self.set_child(self._build_content(self.terminal))
        self._add_key_controller()
        self._apply_geometry()
        self._resize_base_size = (self._panel_width, self._panel_height)
        self._spawn_shell()

        if self.options.dock_namespace:
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
            if monitor and monitor.get_connector() == connector:
                return monitor
        return None

    def _build_content(self, terminal: Vte.Terminal) -> Gtk.Widget:
        frame = Gtk.Overlay()
        frame.add_css_class("quayshell-frame")
        frame.set_overflow(Gtk.Overflow.HIDDEN)
        frame.set_child(terminal)

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
        resize.connect("drag-end", self._on_resize_end)
        self.resize_handle.add_controller(resize)

        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
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
        return terminal

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
            self._read_hyprland()
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
        shell = (
            self.options.shell
            or os.environ.get("SHELL")
            or pwd.getpwuid(os.getuid()).pw_shell
        )
        if not os.path.isabs(shell) or not os.access(shell, os.X_OK):
            raise RuntimeError(f"The shell is not executable: {shell}")
        return shell

    def _spawn_shell(self) -> None:
        shell = self._resolve_shell()
        environment = os.environ.copy()
        environment.update(
            {"SHELL": shell, "TERM": "xterm-256color", "COLORTERM": "truecolor"}
        )
        environment_list = [f"{key}={value}" for key, value in environment.items()]

        self.terminal.connect("child-exited", self._on_child_exited)
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            str(Path.home()),
            [shell, "-l"],
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
        _pid: int,
        error: GLib.Error | None,
        _user_data: object = None,
    ) -> None:
        if error is not None:
            logger.error("Cannot start the shell: %s", error.message)
            self._quit()

    def _on_child_exited(self, _terminal: Vte.Terminal, _status: int) -> None:
        self._quit()

    def _read_hyprland(self) -> None:
        try:
            snapshot = self.hyprland.snapshot()
        except HyprlandError as error:
            logger.debug("Hyprland geometry is unavailable: %s", error)
            return

        self.snapshot = snapshot
        monitor = snapshot.monitor(self.monitor_name)
        if monitor is None:
            if self.monitor_name:
                logger.warning("Hyprland output %s is unavailable.", self.monitor_name)
            self.monitor_geometry = None
            return

        self.monitor_geometry = monitor
        if self.monitor_name is None:
            self.monitor_name = monitor.name

    def _collapsed_placement(self) -> PanelPlacement:
        if self.snapshot and self.monitor_geometry and self.options.dock_namespace:
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

    def _on_resize_begin(
        self,
        gesture: Gtk.GestureDrag,
        _start_x: float,
        _start_y: float,
    ) -> None:
        if self.expanded or self.monitor_geometry is None or self._drag_active:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        try:
            cursor_x, cursor_y = self.hyprland.cursor_position()
        except HyprlandError as error:
            logger.warning("Cannot start resize: %s", error)
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        monitor = self.monitor_geometry
        self._resize_pointer_offset = (
            cursor_x - monitor.x - self._panel_position.x,
            cursor_y - monitor.y - self._panel_position.y,
        )
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
        if self._resize_source_id is None:
            self._resize_source_id = GLib.timeout_add(
                DRAG_INTERVAL_MILLISECONDS,
                self._resize_tick,
            )

    def _resize_tick(self) -> bool:
        if not self._resize_active or self.monitor_geometry is None:
            self._resize_source_id = None
            return GLib.SOURCE_REMOVE
        try:
            cursor_x, cursor_y = self.hyprland.cursor_position()
        except HyprlandError:
            return GLib.SOURCE_CONTINUE

        monitor = self.monitor_geometry
        offset_x, offset_y = self._resize_pointer_offset
        desired_position = PanelPosition(
            cursor_x - monitor.x - offset_x,
            cursor_y - monitor.y - offset_y,
        )
        start_width, start_height = self._resize_start_size
        base_width, base_height = self._resize_base_size or self._resize_start_size
        geometry = resize_from_top_left(
            monitor,
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
        return GLib.SOURCE_CONTINUE

    def _on_resize_end(
        self,
        _gesture: Gtk.GestureDrag,
        _offset_x: float,
        _offset_y: float,
    ) -> None:
        if self._resize_active:
            self._resize_tick()
        self._resize_active = False
        self.resize_handle.set_cursor_from_name("nw-resize")
        if self._resize_source_id is not None:
            GLib.source_remove(self._resize_source_id)
            self._resize_source_id = None

    def _switch_to_pointer_monitor(self, cursor_x: int, cursor_y: int) -> bool:
        if not self.options.cross_monitor or self.snapshot is None:
            return False
        target = self.snapshot.monitor_at(cursor_x, cursor_y)
        if target is None or target.name == self.monitor_name:
            return False
        gdk_monitor = self._gdk_monitor(target.name)
        if gdk_monitor is None:
            logger.warning("Wayland output %s is unavailable.", target.name)
            return False

        self._drag_crossed_monitor = True
        LayerShell.set_monitor(self, gdk_monitor)
        self.monitor_name = target.name
        self.monitor_geometry = target
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
        self._read_hyprland()
        if self.monitor_geometry is None:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        try:
            cursor_x, cursor_y = self.hyprland.cursor_position()
        except HyprlandError as error:
            logger.warning("Cannot start drag: %s", error)
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return

        monitor = self.monitor_geometry
        self._drag_pointer_offset = (
            cursor_x - monitor.x - self._panel_position.x,
            cursor_y - monitor.y - self._panel_position.y,
        )
        self._drag_start_position = self._panel_position
        self._drag_size = (self._panel_width, self._panel_height)
        self._drag_crossed_monitor = False
        self._drag_active = True
        self.drag_handle.set_cursor_from_name("grabbing")
        if self._drag_source_id is None:
            self._drag_source_id = GLib.timeout_add(
                DRAG_INTERVAL_MILLISECONDS,
                self._drag_tick,
            )

    def _drag_tick(self) -> bool:
        if not self._drag_active or self.monitor_geometry is None:
            self._drag_source_id = None
            return GLib.SOURCE_REMOVE
        try:
            cursor_x, cursor_y = self.hyprland.cursor_position()
        except HyprlandError:
            return GLib.SOURCE_CONTINUE

        switched_monitor = self._switch_to_pointer_monitor(cursor_x, cursor_y)
        monitor = self.monitor_geometry
        offset_x, offset_y = self._drag_pointer_offset
        position = PanelPosition(
            cursor_x - monitor.x - offset_x,
            cursor_y - monitor.y - offset_y,
        )
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

        moved = (
            abs(position.x - self._drag_start_position.x) > 2
            or abs(position.y - self._drag_start_position.y) > 2
        )
        if switched_monitor or moved or self._manual_position is not None:
            self._manual_position = position
            self._manual_size = (width, height)
            self._apply_geometry()
        if self._drag_crossed_monitor and not self._primary_button_pressed():
            self._drag_active = False
            self._drag_source_id = None
            self.drag_handle.set_cursor_from_name("grab")
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def _on_drag_end(
        self,
        _gesture: Gtk.GestureDrag,
        _offset_x: float,
        _offset_y: float,
    ) -> None:
        if self._drag_crossed_monitor and self._primary_button_pressed():
            return
        if self._drag_active:
            self._drag_tick()
        self._drag_active = False
        self.drag_handle.set_cursor_from_name("grab")
        if self._drag_source_id is not None:
            GLib.source_remove(self._drag_source_id)
            self._drag_source_id = None

    def _poll_geometry(self) -> bool:
        self._read_hyprland()
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

    def do_activate(self) -> None:
        if self.window is not None:
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
    return application.run([])
