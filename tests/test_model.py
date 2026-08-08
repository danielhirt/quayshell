from quayshell.model import (
    LayerGeometry,
    MonitorGeometry,
    PanelGeometry,
    PanelPlacement,
    PanelPosition,
    PanelSize,
    WindowControlVisibility,
    clamp_panel_position,
    placement_beside_bottom_dock,
    position_from_placement,
    resize_from_top_left,
    snap_panel_position,
    window_controls_for_pointer,
)


def test_monitor_geometry_accounts_for_scale_and_rotation():
    monitor = MonitorGeometry.from_hyprland(
        {
            "name": "DP-3",
            "x": 5120,
            "y": 0,
            "width": 2560,
            "height": 1440,
            "scale": 1.0,
            "transform": 1,
            "reserved": [0, 32, 0, 0],
            "focused": True,
        }
    )

    assert monitor.width == 1440
    assert monitor.height == 2560
    assert monitor.reserved_top == 32
    assert monitor.focused is True


def test_position_from_bottom_right_placement():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440)
    placement = PanelPlacement(380, 72, 8, 8)

    assert position_from_placement(monitor, placement) == PanelPosition(2172, 1360)


def test_clamps_dragged_position_to_reserved_monitor_area():
    monitor = MonitorGeometry(
        "DP-1",
        0,
        0,
        2560,
        1440,
        reserved_left=4,
        reserved_top=32,
        reserved_right=6,
        reserved_bottom=10,
    )

    assert clamp_panel_position(
        monitor,
        PanelPosition(-100, 2000),
        panel_width=380,
        panel_height=72,
    ) == PanelPosition(4, 1358)


def test_terminal_body_does_not_show_window_controls():
    assert window_controls_for_pointer(380, 190, 55) == WindowControlVisibility(
        False,
        False,
        False,
    )


def test_top_center_proximity_shows_only_drag_handle():
    assert window_controls_for_pointer(380, 190, 24) == WindowControlVisibility(
        False,
        True,
        False,
    )


def test_top_right_proximity_shows_only_close_button():
    assert window_controls_for_pointer(380, 355, 24) == WindowControlVisibility(
        False,
        False,
        True,
    )


def test_top_left_proximity_shows_only_resize_handle():
    assert window_controls_for_pointer(380, 20, 24) == WindowControlVisibility(
        True,
        False,
        False,
    )


def test_magnetic_docking_snaps_to_nearby_edges():
    monitor = MonitorGeometry(
        "DP-1",
        0,
        0,
        1000,
        800,
        reserved_left=10,
        reserved_top=20,
        reserved_right=30,
        reserved_bottom=40,
    )

    assert snap_panel_position(
        monitor,
        PanelPosition(28, 648),
        panel_width=200,
        panel_height=100,
        distance=24,
    ) == PanelPosition(10, 660)
    assert snap_panel_position(
        monitor,
        PanelPosition(400, 300),
        panel_width=200,
        panel_height=100,
        distance=24,
    ) == PanelPosition(400, 300)


def test_resize_from_top_left_enforces_default_maximum():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440, reserved_top=32)

    geometry = resize_from_top_left(
        monitor,
        PanelPosition(1000, 900),
        fixed_right=2552,
        fixed_bottom=1432,
        min_width=380,
        min_height=72,
        max_width=950,
        max_height=180,
    )

    assert geometry == PanelGeometry(
        PanelPosition(1602, 1252),
        PanelSize(950, 180),
    )


def test_resize_from_top_left_enforces_minimum():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440, reserved_top=32)

    geometry = resize_from_top_left(
        monitor,
        PanelPosition(2400, 1400),
        fixed_right=2552,
        fixed_bottom=1432,
        min_width=380,
        min_height=72,
        max_width=950,
        max_height=180,
    )

    assert geometry == PanelGeometry(
        PanelPosition(2172, 1360),
        PanelSize(380, 72),
    )


def test_places_panel_to_right_of_bottom_dock():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440)
    dock = LayerGeometry("nwg-dock", "DP-1", 700, 1370, 1200, 64)

    placement = placement_beside_bottom_dock(monitor, dock)

    assert placement is not None
    assert placement.width == 660
    assert placement.height == 64
    assert placement.right_margin == 0
    assert placement.bottom_margin == 6


def test_rejects_layer_that_is_not_a_bottom_dock():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440)
    top_bar = LayerGeometry("waybar", "DP-1", 0, 0, 2560, 32)

    assert placement_beside_bottom_dock(monitor, top_bar) is None


def test_rejects_dock_with_too_little_space_for_terminal():
    monitor = MonitorGeometry("DP-1", 0, 0, 2560, 1440)
    dock = LayerGeometry("dock", "DP-1", 0, 1376, 2500, 64)

    assert placement_beside_bottom_dock(monitor, dock) is None
