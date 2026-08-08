from pathlib import Path
from types import SimpleNamespace

import pytest

from quayshell import sandbox


def test_host_spawn_arguments_sets_environment():
    assert sandbox.host_spawn_arguments(
        ["/bin/zsh", "-l"], {"TERM": "xterm-256color", "SHELL": "/bin/zsh"}
    ) == [
        "flatpak-spawn",
        "--host",
        "--watch-bus",
        "--env=TERM=xterm-256color",
        "--env=SHELL=/bin/zsh",
        "/bin/zsh",
        "-l",
    ]


def test_resolve_host_shell_uses_passwd_entry(monkeypatch):
    calls = []

    def run(arguments, **_kwargs):
        calls.append(arguments)
        if "getent" in arguments:
            return SimpleNamespace(
                returncode=0,
                stdout="daniel:x:1000:1000::/home/daniel:/usr/bin/zsh\n",
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sandbox.subprocess, "run", run)

    assert sandbox.resolve_host_shell() == "/usr/bin/zsh"
    assert calls[-1] == [
        "flatpak-spawn",
        "--host",
        "test",
        "-x",
        "/usr/bin/zsh",
    ]


def test_resolve_host_shell_rejects_relative_override():
    with pytest.raises(RuntimeError, match="not absolute"):
        sandbox.resolve_host_shell("zsh")


def test_stage_shell_integration(tmp_path: Path):
    source = tmp_path / "source"
    (source / "zsh").mkdir(parents=True)
    (source / "bash").write_text("bash hook\n")
    (source / "zsh" / ".zshrc").write_text("zsh hook\n")

    destination = sandbox.stage_shell_integration(source, tmp_path / "cache")

    assert (destination / "bash").read_text() == "bash hook\n"
    assert (destination / "zsh" / ".zshrc").read_text() == "zsh hook\n"
