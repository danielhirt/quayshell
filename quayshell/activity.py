"""Track shell command activity for the compact status display."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ActivityPhase(Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True)
class CommandCompletion:
    command: str
    status: int
    duration: float


class ActivityTracker:
    def __init__(self) -> None:
        self.phase = ActivityPhase.IDLE
        self.command = "command"
        self.started_at: float | None = None
        self.completed_at: float | None = None
        self.status: int | None = None

    def start(self, now: float) -> None:
        self.phase = ActivityPhase.RUNNING
        self.command = "command"
        self.started_at = now
        self.completed_at = None
        self.status = None

    def set_command(self, command: str | None) -> None:
        if self.phase is ActivityPhase.RUNNING and command:
            self.command = command

    def finish(self, status: int, now: float) -> CommandCompletion | None:
        if self.phase is not ActivityPhase.RUNNING or self.started_at is None:
            return None
        duration = max(0.0, now - self.started_at)
        self.status = status
        self.completed_at = now
        self.phase = ActivityPhase.SUCCESS if status == 0 else ActivityPhase.FAILURE
        return CommandCompletion(self.command, status, duration)

    def reset_if_expired(self, now: float, result_seconds: float) -> None:
        if self.completed_at is None:
            return
        if now - self.completed_at >= result_seconds:
            self.phase = ActivityPhase.IDLE
            self.completed_at = None

    def elapsed(self, now: float) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at if self.completed_at is not None else now
        return max(0.0, end - self.started_at)

    def label(self, now: float) -> str:
        seconds = round(self.elapsed(now))
        if self.phase is ActivityPhase.RUNNING:
            return f"{self.command} · {seconds}s"
        if self.phase is ActivityPhase.SUCCESS:
            return f"✓ {self.command} · {seconds}s"
        if self.phase is ActivityPhase.FAILURE:
            return f"× {self.command} · exit {self.status}"
        return ""

    def mascot(self) -> str:
        return {
            ActivityPhase.IDLE: "·ᴗ·",
            ActivityPhase.RUNNING: "·⌄·",
            ActivityPhase.SUCCESS: "·‿·",
            ActivityPhase.FAILURE: "·︵·",
        }[self.phase]


def format_command_line(data: bytes, *, max_chars: int = 48) -> str | None:
    parts = [part.decode(errors="replace") for part in data.split(b"\0") if part]
    if not parts:
        return None
    parts[0] = Path(parts[0]).name
    command = " ".join(part.replace("\n", " ").replace("\r", " ") for part in parts)
    if len(command) > max_chars:
        return command[: max(1, max_chars - 1)] + "…"
    return command


def foreground_command(pty_fd: int, shell_pid: int | None) -> str | None:
    try:
        process_group = os.tcgetpgrp(pty_fd)
    except OSError:
        return None
    if process_group <= 0 or process_group == shell_pid:
        return None
    try:
        data = Path(f"/proc/{process_group}/cmdline").read_bytes()
    except OSError:
        return None
    return format_command_line(data)
