import pytest

from quayshell.compositor import Capability
from quayshell.sway import SwayClient, SwayError, parse_sway_outputs

OUTPUTS = [
    {
        "name": "HDMI-A-1",
        "active": True,
        "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
    },
    {
        "name": "DP-1",
        "active": True,
        "rect": {"x": 1920, "y": -200, "width": 2560, "height": 1440},
    },
]
WORKSPACES = [{"name": "2", "output": "DP-1", "focused": True}]


def test_parses_sway_outputs_and_focused_workspace():
    monitors = parse_sway_outputs(OUTPUTS, WORKSPACES)

    assert monitors[0].name == "HDMI-A-1"
    assert monitors[1].x == 1920
    assert monitors[1].y == -200
    assert monitors[1].focused is True


def test_sway_client_reads_snapshot():
    responses = {"get_outputs": OUTPUTS, "get_workspaces": WORKSPACES}
    client = SwayClient(lambda args: responses[args[1]])

    assert client.snapshot().monitor().name == "DP-1"
    assert client.capabilities == frozenset({Capability.OUTPUTS})


def test_sway_rejects_invalid_output_data():
    with pytest.raises(SwayError, match="invalid field"):
        parse_sway_outputs([{"name": "broken"}], [])
