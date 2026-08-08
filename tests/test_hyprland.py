import pytest

from quayshell.hyprland import (
    HyprlandClient,
    HyprlandError,
    parse_cursor_position,
    parse_layers,
    parse_monitors,
)

MONITORS = [
    {
        "name": "DP-1",
        "x": 0,
        "y": 0,
        "width": 2560,
        "height": 1440,
        "scale": 1.0,
        "transform": 0,
        "reserved": [0, 32, 0, 0],
        "focused": False,
    },
    {
        "name": "DP-2",
        "x": 2560,
        "y": 0,
        "width": 2560,
        "height": 1440,
        "scale": 1.0,
        "transform": 0,
        "reserved": [0, 32, 0, 0],
        "focused": True,
    },
]

LAYERS = {
    "DP-1": {
        "levels": {
            "2": [
                {
                    "namespace": "nwg-dock",
                    "x": 600,
                    "y": 1372,
                    "w": 1300,
                    "h": 64,
                }
            ]
        }
    },
    "DP-2": {"levels": {"2": []}},
}


def test_snapshot_selects_focused_monitor_and_layer():
    responses = {"monitors": MONITORS, "layers": LAYERS}
    client = HyprlandClient(lambda args: responses[args[0]])

    snapshot = client.snapshot()

    assert snapshot.monitor().name == "DP-2"
    assert snapshot.monitor("DP-1").reserved_top == 32
    assert snapshot.monitor_at(2559, 1439).name == "DP-1"
    assert snapshot.monitor_at(2560, 0).name == "DP-2"
    assert snapshot.monitor_at(-1, 0) is None
    assert snapshot.layer("nwg-dock", "DP-1").width == 1300
    assert snapshot.layer("nwg-dock", "DP-2") is None


def test_client_reads_cursor_position():
    client = HyprlandClient(lambda args: {"x": 4244, "y": 947})

    assert client.cursor_position() == (4244, 947)


def test_parse_cursor_position_rejects_invalid_data():
    with pytest.raises(HyprlandError, match="invalid field"):
        parse_cursor_position({"x": 10})


def test_parse_layers_rejects_invalid_geometry():
    with pytest.raises(HyprlandError, match="invalid field"):
        parse_layers({"DP-1": {"levels": {"2": [{"namespace": "dock"}]}}})


def test_parse_monitors_requires_a_list():
    with pytest.raises(HyprlandError, match="not a list"):
        parse_monitors({})
