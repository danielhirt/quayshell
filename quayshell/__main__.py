"""Run Quayshell."""

from __future__ import annotations

import subprocess
import sys

from quayshell.cli import parse_args
from quayshell.config import ConfigError, load_config


def main(arguments: list[str] | None = None) -> int:
    try:
        config = load_config()
    except ConfigError as error:
        print(f"quayshell: {error}", file=sys.stderr)
        return 2
    options = parse_args(arguments, config=config)
    if options.remote_action == "diagnose":
        from quayshell.diagnostics import collect_diagnostics

        report = collect_diagnostics(options.backend)
        print(report.render())
        return 0 if report.supported else 1
    if options.remote_action:
        try:
            result = subprocess.run(
                [
                    "gapplication",
                    "action",
                    "dev.danielh.quayshell",
                    options.remote_action,
                ],
                check=False,
            )
        except OSError as error:
            print(f"quayshell: Cannot send the action: {error}", file=sys.stderr)
            return 1
        if result.returncode != 0:
            print(
                "quayshell: No running Quayshell accepted the action.", file=sys.stderr
            )
        return result.returncode

    from quayshell.diagnostics import collect_diagnostics

    report = collect_diagnostics(options.backend)
    if not report.supported:
        print(report.render(), file=sys.stderr)
        return 1

    try:
        from quayshell.app import run
    except (ImportError, OSError, ValueError) as error:
        print(
            f"quayshell: GTK4, VTE4, or gtk4-layer-shell is unavailable: {error}",
            file=sys.stderr,
        )
        return 1
    return run(options)


if __name__ == "__main__":
    raise SystemExit(main())
