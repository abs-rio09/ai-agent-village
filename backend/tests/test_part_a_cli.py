"""Part A: the ./village bash CLI (syntax and the commands that are safe to run in tests)."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from app.config import ROOT_DIR

VILLAGE = ROOT_DIR / "village"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(VILLAGE), *args], capture_output=True, text=True, timeout=30)


def test_cli_is_executable_and_parses() -> None:
    assert VILLAGE.is_file()
    assert VILLAGE.stat().st_mode & 0o111, "village must be executable"
    result = subprocess.run(["bash", "-n", str(VILLAGE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_cli_passes_shellcheck() -> None:
    result = subprocess.run(["shellcheck", str(VILLAGE)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout


def test_cli_never_calls_sudo() -> None:
    for line in VILLAGE.read_text(encoding="utf-8").splitlines():
        code = line.split("#", 1)[0].strip()
        if "sudo" in code:
            # sudo may only ever appear inside text that is printed for the user
            assert code.startswith(("info ", "report ")), line


@pytest.mark.parametrize("args", [(), ("help",), ("--help",)])
def test_cli_usage(args: tuple[str, ...]) -> None:
    result = _run(*args)
    assert result.returncode == 0
    for command in ("setup", "start", "stop", "restart", "status", "logs", "doctor", "backup", "restore"):
        assert command in result.stdout


@pytest.mark.parametrize("command", ["backup", "restore"])
def test_cli_backup_restore_are_placeholders(command: str) -> None:
    result = _run(command)
    assert result.returncode == 0
    assert "coming in M8" in result.stdout


def test_cli_unknown_command_fails() -> None:
    result = _run("definitely-not-a-command")
    assert result.returncode != 0
