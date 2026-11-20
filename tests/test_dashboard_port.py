import socket

import pytest

from desto.app import dashboard


def test_port_is_free_detects_a_port_in_use():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        assert not dashboard.port_is_free("127.0.0.1", port)
    assert dashboard.port_is_free("127.0.0.1", port)


def test_main_exits_with_a_hint_when_the_port_is_taken(monkeypatch):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]
        monkeypatch.setenv("DESTO_HOST", "127.0.0.1")
        monkeypatch.setenv("DESTO_PORT", str(port))
        monkeypatch.setattr(dashboard.ui, "run", lambda *a, **k: pytest.fail("ui.run should not be called"))
        messages = []
        monkeypatch.setattr(dashboard.logger, "error", messages.append)

        with pytest.raises(SystemExit) as exc:
            dashboard.main()

    assert exc.value.code == 1
    assert f"DESTO_PORT={port + 1} desto" in messages[0]
