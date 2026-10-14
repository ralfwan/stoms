import subprocess
import webbrowser
from typing import Any

import pytest

from stoms.web import server

URL = "http://127.0.0.1:8765/#/aggregations/agg_1"


class FakeProcess:
    def __init__(self, status: int | None) -> None:
        self.status = status

    def wait(self, timeout: float) -> int:
        if self.status is None:
            raise subprocess.TimeoutExpired("xdg-open", timeout)
        return self.status


@pytest.fixture
def linux(monkeypatch) -> list[list[str]]:
    """Linux with xdg-open and no BROWSER; records xdg-open calls."""
    calls: list[list[str]] = []
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.delenv("BROWSER", raising=False)
    monkeypatch.setattr(
        server.shutil, "which", lambda name: f"/usr/bin/{name}"
    )
    monkeypatch.setattr(server, "_on_wsl", lambda: False)
    monkeypatch.setattr(
        webbrowser, "open", lambda url: pytest.fail("webbrowser must not run")
    )
    return calls


def _xdg(monkeypatch, calls: list[list[str]], status: int | None) -> None:
    def popen(args: list[str], **kwargs: Any) -> FakeProcess:
        calls.append(args)
        assert kwargs["stdout"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        return FakeProcess(status)

    monkeypatch.setattr(server.subprocess, "Popen", popen)


def _open(capsys) -> str:
    thread = server.open_browser_page(URL)
    if thread is not None:
        thread.join(5)
    return capsys.readouterr().err


def test_failed_xdg_open_prints_address_not_noise(
    monkeypatch, capsys, linux
) -> None:
    _xdg(monkeypatch, linux, status=3)
    err = _open(capsys)
    assert linux == [["xdg-open", URL]]
    assert (
        err
        == f"Could not open a web browser. Open this address in your browser:\n  {URL}\n"
    )


def test_wsl_gets_a_hint(monkeypatch, capsys, linux) -> None:
    _xdg(monkeypatch, linux, status=3)
    monkeypatch.setattr(server, "_on_wsl", lambda: True)
    assert "install wslu and set BROWSER=wslview" in _open(capsys)


@pytest.mark.parametrize("status", [0, None])
def test_working_or_running_xdg_open_stays_quiet(
    monkeypatch, capsys, linux, status
) -> None:
    _xdg(monkeypatch, linux, status=status)
    assert _open(capsys) == ""


def test_other_systems_use_webbrowser(monkeypatch, capsys) -> None:
    opened: list[str] = []
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.setattr(
        webbrowser, "open", lambda url: opened.append(url) or True
    )
    assert _open(capsys) == ""
    assert opened == [URL]

    monkeypatch.setattr(webbrowser, "open", lambda url: False)
    assert "Could not open a web browser" in _open(capsys)


def test_browser_variable_or_missing_xdg_open_use_webbrowser(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.setattr(server, "_on_wsl", lambda: False)
    monkeypatch.setattr(webbrowser, "open", lambda url: False)
    monkeypatch.setenv("BROWSER", "wslview")
    assert "Could not open a web browser" in _open(capsys)

    monkeypatch.delenv("BROWSER")
    monkeypatch.setattr(server.shutil, "which", lambda name: None)

    def broken(url: str) -> bool:
        raise webbrowser.Error("could not locate runnable browser")

    monkeypatch.setattr(webbrowser, "open", broken)
    assert "Could not open a web browser" in _open(capsys)
