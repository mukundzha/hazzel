import os
import sys
from unittest.mock import MagicMock, patch

from hazzel import ui, wincompat
from hazzel.tools.run_command import is_safe_command


def _windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    wincompat._ANSI_OK = None
    return wincompat


def _posix(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    wincompat._ANSI_OK = None
    return wincompat


def test_is_windows(monkeypatch):
    assert _windows(monkeypatch).is_windows() is True
    assert _posix(monkeypatch).is_windows() is False


def test_popen_kwargs(monkeypatch):
    assert _windows(monkeypatch).popen_kwargs() == {}
    assert _posix(monkeypatch).popen_kwargs() == {"start_new_session": True}


def test_kill_proc_posix(monkeypatch):
    _posix(monkeypatch)
    proc = MagicMock()
    proc.pid = 1234
    with patch.object(os, "killpg") as killpg:
        wincompat.kill_proc(proc)
    killpg.assert_called_once()
    proc.kill.assert_not_called()


def test_kill_proc_posix_falls_back(monkeypatch):
    _posix(monkeypatch)
    proc = MagicMock()
    with patch.object(os, "killpg", side_effect=OSError("nope")):
        wincompat.kill_proc(proc)
    proc.kill.assert_called_once()


def test_kill_proc_windows(monkeypatch):
    _windows(monkeypatch)
    proc = MagicMock()
    wincompat.kill_proc(proc)
    proc.kill.assert_called_once()


def test_enable_ansi_posix(monkeypatch):
    assert _posix(monkeypatch).enable_ansi() is True


def test_enable_ansi_windows_no_console(monkeypatch):
    _windows(monkeypatch)
    assert wincompat.enable_ansi() is False


def test_input_windows_simple(monkeypatch, capsys):
    _windows(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda: "hello")
    assert ui.get_input() == "hello"
    assert "hello" in capsys.readouterr().out


class _FakeMsvcrt:
    def __init__(self, keys):
        self._keys = list(keys)

    def getwch(self):
        if not self._keys:
            raise OSError("no more keys")
        return self._keys.pop(0)


def _msvcrt_keys(monkeypatch, keys):
    _windows(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setitem(sys.modules, "msvcrt", _FakeMsvcrt(keys))


def test_win_input_prefill_and_type(monkeypatch, capsys):
    _msvcrt_keys(monkeypatch, ["f", "i", "x", "\r"])
    assert ui.get_input(prefill="@helper ") == "@helper fix"
    assert "@helper fix" in capsys.readouterr().out


def test_win_input_backspace_and_esc(monkeypatch):
    _msvcrt_keys(monkeypatch, ["\x08", "\r"])
    assert ui.get_input(prefill="@helper ") == "@helper"
    _msvcrt_keys(monkeypatch, ["\x1b", "o", "k", "\r"])
    assert ui.get_input(prefill="@helper ") == "ok"


def test_win_input_ctrl_c_and_extended(monkeypatch):
    import pytest

    _msvcrt_keys(monkeypatch, ["\x03"])
    with pytest.raises(KeyboardInterrupt):
        ui.get_input(prefill="@helper ")
    _msvcrt_keys(monkeypatch, ["\xe0", "H", "o", "k", "\r"])
    assert ui.get_input() == "ok"


def test_safe_commands_windows(monkeypatch):
    _windows(monkeypatch)
    assert is_safe_command("dir") is True
    assert is_safe_command("git status") is True
    assert is_safe_command("rm -rf /") is False


def test_safe_commands_posix(monkeypatch):
    _posix(monkeypatch)
    assert is_safe_command("ls") is True
    assert is_safe_command("dir") is False


def test_expand_key_without_termios(monkeypatch):
    monkeypatch.setitem(sys.modules, "termios", None)
    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0)
    assert ui._read_expand_key() is False
