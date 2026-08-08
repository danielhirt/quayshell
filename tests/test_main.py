from subprocess import CompletedProcess

from quayshell.__main__ import main
from quayshell.config import Config


def test_summon_sends_application_action(monkeypatch):
    calls = []

    def run(arguments, *, check):
        calls.append((arguments, check))
        return CompletedProcess(arguments, 0)

    monkeypatch.setattr("quayshell.__main__.subprocess.run", run)
    monkeypatch.setattr("quayshell.__main__.load_config", Config)

    assert main(["--summon"]) == 0
    assert calls == [
        (
            [
                "gapplication",
                "action",
                "dev.danielh.quayshell",
                "summon",
            ],
            False,
        )
    ]
