"""Shared fixtures: isolated store, blocked network, unset credentials."""

from __future__ import annotations

import pytest

from jev_governor import config, storage


@pytest.fixture(autouse=True)
def _no_provider_traffic(monkeypatch):
    import socket
    import urllib.request

    class _BlockedSocket:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("network blocked in tests")

    monkeypatch.setattr(socket, "socket", _BlockedSocket)
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network blocked in tests")),
    )
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("JEV_GOVERNOR_JEV_ENABLED", "false")
    monkeypatch.setenv("JEV_GOVERNOR_LIVE_MAX_ATTEMPTS", "0")


@pytest.fixture()
def data_dir(tmp_path):
    directory = tmp_path / "gov-data"
    directory.mkdir()
    return directory


@pytest.fixture()
def settings(data_dir):
    return config.load_settings(data_dir)


@pytest.fixture()
def conn(settings):
    connection = storage.connect(settings)
    yield connection
    connection.close()


def run_cli(monkeypatch, capsys, data_dir, *args):
    """Run the CLI with an isolated data dir; return (exit_code, out, err)."""
    from jev_governor import cli as cli_mod

    argv = ["--data-dir", str(data_dir), *[str(a) for a in args]]
    code = cli_mod.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture()
def cli_runner(monkeypatch, capsys, data_dir):
    def run(*args):
        return run_cli(monkeypatch, capsys, data_dir, *args)

    return run
