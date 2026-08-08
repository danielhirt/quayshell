import os
import shutil
import subprocess
from pathlib import Path

import pytest

INTEGRATION = Path(__file__).parents[1] / "quayshell" / "shell_integration"
STATUS_SEQUENCE = b"\x1b]666;vte.ext.quayshell.shell.postexec=7\x1b\\"


def test_bash_hook_emits_exit_status(tmp_path):
    result = subprocess.run(
        [
            "bash",
            "--noprofile",
            "--norc",
            "-c",
            f"source {INTEGRATION / 'bash'}; (exit 7); __quayshell_precmd",
        ],
        check=False,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )

    assert result.returncode == 7
    assert STATUS_SEQUENCE in result.stdout


@pytest.mark.skipif(shutil.which("zsh") is None, reason="Zsh is not installed")
def test_zsh_hook_emits_exit_status(tmp_path):
    result = subprocess.run(
        [
            "zsh",
            "-f",
            "-c",
            f"source {INTEGRATION / 'zsh' / '.zshrc'}; (exit 7); __quayshell_precmd",
        ],
        check=False,
        capture_output=True,
        env={**os.environ, "HOME": str(tmp_path)},
    )

    assert result.returncode == 7
    assert STATUS_SEQUENCE in result.stdout
