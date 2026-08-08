from pathlib import Path

import pytest

from quayshell.config import Config, ConfigError, default_config_path, load_config


def test_missing_config_uses_default(tmp_path):
    assert load_config(tmp_path / "missing.toml") == Config(max_scale=2.5)


def test_reads_all_settings(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        """[window]
width = 600
height = 120
margin = 12
monitor = "DP-2"
dock_namespace = "dock"
max_scale = 4.0
cross_monitor = false

[terminal]
font = "Monospace 13"
shell = "/bin/bash"
"""
    )

    assert load_config(path) == Config(
        width=600,
        height=120,
        margin=12,
        monitor="DP-2",
        dock_namespace="dock",
        max_scale=4.0,
        cross_monitor=False,
        font="Monospace 13",
        shell="/bin/bash",
    )


@pytest.mark.parametrize("value", ["0.5", "nan", "inf"])
def test_rejects_invalid_max_scale(tmp_path, value):
    path = tmp_path / "config.toml"
    path.write_text(f"[window]\nmax_scale = {value}\n")

    with pytest.raises(ConfigError, match="1.0 or greater"):
        load_config(path)


def test_rejects_unknown_setting(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[window]\nwidht = 400\n")

    with pytest.raises(ConfigError, match="widht"):
        load_config(path)


def test_rejects_nonboolean_cross_monitor(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[window]\ncross_monitor = "yes"\n')

    with pytest.raises(ConfigError, match="true or false"):
        load_config(path)


def test_rejects_invalid_toml(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[window\n")

    with pytest.raises(ConfigError, match="Cannot read"):
        load_config(path)


def test_default_path_uses_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert default_config_path() == Path(tmp_path) / "quayshell" / "config.toml"
