"""Run Quayshell."""

from __future__ import annotations

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
