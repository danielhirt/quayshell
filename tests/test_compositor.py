import pytest

from quayshell.compositor import (
    Capability,
    CompositorError,
    CompositorSnapshot,
    GdkBackend,
    select_backend,
)
from quayshell.model import MonitorGeometry


def test_generic_backend_reports_only_output_capability():
    snapshot = CompositorSnapshot((MonitorGeometry("HDMI-A-1", 0, 0, 1920, 1080),))
    backend = GdkBackend(lambda: snapshot)

    assert backend.snapshot() == snapshot
    assert backend.capabilities == frozenset({Capability.OUTPUTS})


def test_selects_hyprland_backend(monkeypatch):
    monkeypatch.setenv("HYPRLAND_INSTANCE_SIGNATURE", "test")
    monkeypatch.setattr(
        "quayshell.compositor.shutil.which",
        lambda command: f"/usr/bin/{command}",
    )

    assert select_backend(lambda: CompositorSnapshot(())).name == "hyprland"


def test_forced_hyprland_backend_requires_active_session(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)

    with pytest.raises(CompositorError, match="active Hyprland"):
        select_backend(lambda: CompositorSnapshot(()), "hyprland")


def test_falls_back_to_generic_backend(monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("SWAYSOCK", raising=False)

    assert select_backend(lambda: CompositorSnapshot(())).name == "generic-wayland"
