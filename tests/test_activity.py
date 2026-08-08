import pytest

from quayshell.activity import ActivityPhase, ActivityTracker, format_command_line


def test_activity_tracks_successful_command():
    tracker = ActivityTracker()

    tracker.start(10.0)
    tracker.set_command("pytest")
    completion = tracker.finish(0, 13.6)

    assert completion is not None
    assert completion.command == "pytest"
    assert completion.duration == pytest.approx(3.6)
    assert tracker.phase is ActivityPhase.SUCCESS
    assert tracker.label(14.0) == "✓ pytest · 4s"
    assert tracker.mascot() == "·‿·"


def test_activity_tracks_failure_and_expires():
    tracker = ActivityTracker()

    tracker.start(20.0)
    tracker.set_command("cargo test")
    tracker.finish(2, 21.0)
    tracker.reset_if_expired(30.0, 8.0)

    assert tracker.phase is ActivityPhase.IDLE
    assert tracker.label(30.0) == ""


def test_finish_ignores_shell_startup_postexec():
    assert ActivityTracker().finish(0, 1.0) is None


def test_formats_foreground_command():
    assert format_command_line(b"/usr/bin/sleep\x001\x00") == "sleep 1"


def test_truncates_foreground_command():
    assert format_command_line(
        b"/usr/bin/python\x00long-script-name.py\x00", max_chars=16
    ) == ("python long-scr…")


def test_empty_command_line_returns_none():
    assert format_command_line(b"") is None
