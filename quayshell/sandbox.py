"""Flatpak host-shell support."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


def running_in_flatpak() -> bool:
    """Return whether Quayshell runs in a Flatpak sandbox."""
    return bool(os.environ.get("FLATPAK_ID")) or Path("/.flatpak-info").is_file()


def resolve_host_shell(configured_shell: str | None = None) -> str:
    """Resolve and verify the login shell on the Flatpak host."""
    shell = configured_shell
    if shell is None:
        result = subprocess.run(
            ["flatpak-spawn", "--host", "getent", "passwd", str(os.getuid())],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("Cannot resolve the host login shell through Flatpak")
        fields = result.stdout.strip().split(":")
        if len(fields) < 7:
            raise RuntimeError("The host returned an invalid passwd entry")
        shell = fields[-1]

    if not os.path.isabs(shell):
        raise RuntimeError(f"The host shell path is not absolute: {shell}")
    result = subprocess.run(
        ["flatpak-spawn", "--host", "test", "-x", shell],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"The host shell is not executable: {shell}")
    return shell


def stage_shell_integration(source: Path, cache_home: Path) -> Path:
    """Copy shell hooks to a path that the sandbox and host can read."""
    destination = cache_home / "quayshell" / "shell_integration"
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "bash", destination / "bash")
    zsh_destination = destination / "zsh"
    zsh_destination.mkdir(exist_ok=True)
    shutil.copy2(source / "zsh" / ".zshrc", zsh_destination / ".zshrc")
    return destination


def host_spawn_arguments(
    arguments: Sequence[str], environment: Mapping[str, str]
) -> list[str]:
    """Wrap a command for execution on the Flatpak host."""
    command = ["flatpak-spawn", "--host", "--watch-bus"]
    command.extend(f"--env={key}={value}" for key, value in environment.items())
    command.extend(arguments)
    return command
