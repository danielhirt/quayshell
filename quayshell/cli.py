"""Command-line options for Quayshell."""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

from quayshell import __version__
from quayshell.config import Config


@dataclass(frozen=True)
class Options:
    width: int
    height: int
    margin: int
    monitor: str | None
    dock_namespace: str | None
    font: str
    shell: str | None
    max_scale: float
    cross_monitor: bool


def positive_integer(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("The value must be greater than zero.")
    return number


def nonnegative_integer(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("The value must be zero or greater.")
    return number


def scale_at_least_one(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 1.0:
        raise argparse.ArgumentTypeError("The value must be 1.0 or greater.")
    return number


def build_parser(config: Config | None = None) -> argparse.ArgumentParser:
    defaults = config or Config()
    parser = argparse.ArgumentParser(
        prog="quayshell",
        description="Show a persistent terminal on a Wayland layer surface.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--width",
        type=positive_integer,
        default=defaults.width,
        help=f"collapsed width in pixels (default: {defaults.width})",
    )
    parser.add_argument(
        "--height",
        type=positive_integer,
        default=defaults.height,
        help=f"collapsed height in pixels (default: {defaults.height})",
    )
    parser.add_argument(
        "--margin",
        type=nonnegative_integer,
        default=defaults.margin,
        help=f"screen margin in pixels (default: {defaults.margin})",
    )
    parser.add_argument(
        "--monitor",
        metavar="OUTPUT",
        default=defaults.monitor,
        help="startup Wayland output name",
    )
    parser.add_argument(
        "--dock-namespace",
        metavar="NAME",
        default=defaults.dock_namespace,
        help="Hyprland layer namespace for a bottom dock",
    )
    parser.add_argument(
        "--font",
        default=defaults.font,
        help=f"Pango font description (default: {defaults.font})",
    )
    parser.add_argument(
        "--shell",
        metavar="PATH",
        default=defaults.shell,
        help="shell path (default: $SHELL)",
    )
    parser.add_argument(
        "--max-scale",
        type=scale_at_least_one,
        default=defaults.max_scale,
        help=f"maximum resize scale (default: {defaults.max_scale:g})",
    )
    parser.add_argument(
        "--cross-monitor",
        action=argparse.BooleanOptionalAction,
        default=defaults.cross_monitor,
        help="allow dragging between outputs (default: enabled)",
    )
    return parser


def parse_args(
    arguments: list[str] | None = None,
    *,
    config: Config | None = None,
) -> Options:
    defaults = config or Config()
    args = build_parser(defaults).parse_args(arguments)
    return Options(
        width=args.width,
        height=args.height,
        margin=args.margin,
        monitor=args.monitor,
        dock_namespace=args.dock_namespace,
        font=args.font,
        shell=args.shell,
        max_scale=args.max_scale,
        cross_monitor=args.cross_monitor,
    )
