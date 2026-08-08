import argparse

import pytest

from quayshell.cli import (
    nonnegative_integer,
    parse_args,
    positive_integer,
    scale_at_least_one,
)
from quayshell.config import Config


def test_default_options():
    options = parse_args([])

    assert options.width == 380
    assert options.height == 72
    assert options.margin == 8
    assert options.monitor is None
    assert options.dock_namespace is None
    assert options.font == "Monospace 11"
    assert options.max_scale == 2.5
    assert options.cross_monitor is True
    assert options.smart_collapse is True
    assert options.magnetic_docking is True
    assert options.backend == "auto"
    assert options.remote_action is None


def test_custom_options():
    options = parse_args(
        [
            "--width",
            "420",
            "--height",
            "80",
            "--margin",
            "0",
            "--monitor",
            "DP-1",
            "--dock-namespace",
            "nwg-dock",
            "--font",
            "MesloLGS Nerd Font 11",
            "--shell",
            "/bin/zsh",
            "--no-cross-monitor",
            "--backend",
            "generic",
        ]
    )

    assert options.width == 420
    assert options.height == 80
    assert options.margin == 0
    assert options.monitor == "DP-1"
    assert options.dock_namespace == "nwg-dock"
    assert options.shell == "/bin/zsh"
    assert options.max_scale == 2.5
    assert options.cross_monitor is False
    assert options.backend == "generic"


@pytest.mark.parametrize("value", ["0", "-1"])
def test_positive_integer_rejects_nonpositive_values(value):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_integer(value)


def test_config_values_reach_options_and_cli_overrides_them():
    config = Config(width=600, monitor="DP-2", max_scale=4.0, cross_monitor=False)

    options = parse_args(
        ["--width", "700", "--max-scale", "5", "--cross-monitor"],
        config=config,
    )

    assert options.width == 700
    assert options.monitor == "DP-2"
    assert options.max_scale == 5.0
    assert options.cross_monitor is True


@pytest.mark.parametrize("value", ["0.5", "nan", "inf"])
def test_scale_rejects_values_below_one_or_nonfinite(value):
    with pytest.raises(argparse.ArgumentTypeError):
        scale_at_least_one(value)


def test_remote_action_options():
    assert parse_args(["--summon"]).remote_action == "summon"
    assert parse_args(["--home"]).remote_action == "home"
    assert parse_args(["--diagnose"]).remote_action == "diagnose"


def test_nonnegative_integer_accepts_zero():
    assert nonnegative_integer("0") == 0
