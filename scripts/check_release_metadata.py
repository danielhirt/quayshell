"""Fail when package templates disagree about the Quayshell version."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def read_match(path: str, pattern: str) -> str:
    text = (ROOT / path).read_text()
    match = re.search(pattern, text, re.MULTILINE)
    if match is None:
        raise SystemExit(f"Cannot find a version in {path}.")
    return match.group(1)


def main() -> int:
    with (ROOT / "pyproject.toml").open("rb") as file:
        expected = tomllib.load(file)["project"]["version"]
    versions = {
        "quayshell/__init__.py": read_match(
            "quayshell/__init__.py", r'^__version__ = "([^"]+)"$'
        ),
        "packaging/arch/PKGBUILD": read_match(
            "packaging/arch/PKGBUILD", r"^pkgver=([^\s]+)$"
        ),
        "packaging/fedora/quayshell.spec": read_match(
            "packaging/fedora/quayshell.spec", r"^Version:\s+([^\s]+)$"
        ),
        "packaging/opensuse/quayshell.spec": read_match(
            "packaging/opensuse/quayshell.spec", r"^Version:\s+([^\s]+)$"
        ),
        "packaging/debian/changelog": read_match(
            "packaging/debian/changelog", r"^quayshell \(([^-]+)-"
        ),
        "flake.nix": read_match("flake.nix", r'^\s+version = "([^"]+)";$'),
    }
    mismatches = {path: value for path, value in versions.items() if value != expected}
    if mismatches:
        details = ", ".join(f"{path}={value}" for path, value in mismatches.items())
        raise SystemExit(f"Expected version {expected}; found {details}.")
    print(f"All package templates use version {expected}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
