import io
import re

import pytest
from rich.text import Text

from hazzel import config, ui
from hazzel import __main__ as main_module
from hazzel.print_mode import EXIT_OK, run_print

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


def test_is_no_color_env(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ui.is_no_color() is False

    monkeypatch.setenv("NO_COLOR", "")
    assert ui.is_no_color() is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.is_no_color() is True

    monkeypatch.setenv("NO_COLOR", "0")
    assert ui.is_no_color() is True

    monkeypatch.setenv("NO_COLOR", "true")
    assert ui.is_no_color() is True


def test_main_shares_ui_console():
    assert main_module.console is ui.console


def test_console_no_color_dynamic(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ui.console.no_color is False

    monkeypatch.setenv("NO_COLOR", "1")
    assert ui.console.no_color is True

    monkeypatch.delenv("NO_COLOR", raising=False)
    assert ui.console.no_color is False


def test_console_print_no_ansi_when_no_color(monkeypatch):
    buf_color = io.StringIO()
    monkeypatch.delenv("NO_COLOR", raising=False)
    test_console = ui.HazzelConsole(file=buf_color, force_terminal=True)
    test_console.print(Text("hello world", style="bold red"))
    assert ANSI_ESCAPE_RE.search(buf_color.getvalue()) is not None

    buf_nocolor = io.StringIO()
    monkeypatch.setenv("NO_COLOR", "1")
    test_console_nc = ui.HazzelConsole(file=buf_nocolor, force_terminal=True)
    test_console_nc.print(Text("hello world", style="bold red"))
    out_nc = buf_nocolor.getvalue()
    assert "hello world" in out_nc
    assert ANSI_ESCAPE_RE.search(out_nc) is None


def test_rule_ansi_respects_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert "\x1b[2m" in ui._rule_ansi()

    monkeypatch.setenv("NO_COLOR", "1")
    rule = ui._rule_ansi()
    assert "\x1b" not in rule
    assert "─" in rule


def test_format_context_meter_respects_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert "\x1b" in ui.format_context_meter(100, 1000)

    monkeypatch.setenv("NO_COLOR", "1")
    meter = ui.format_context_meter(100, 1000)
    assert "\x1b" not in meter
    assert "10.0%" in meter


def test_highlight_mentions_respects_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert "\x1b" in ui._highlight_mentions("@file.py")

    monkeypatch.setenv("NO_COLOR", "1")
    assert "\x1b" not in ui._highlight_mentions("@file.py")
    assert ui._highlight_mentions("@file.py") == "@file.py"


def test_run_print_no_color(monkeypatch, capsys):
    from hazzel import agent

    monkeypatch.setattr(agent, "run", lambda m, p: ("mocked reply", [], None))
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")

    code = run_print("hi", approve=False, output_format="text")
    out, err = capsys.readouterr()

    assert code == EXIT_OK
    assert out == "mocked reply\n"
    assert err == ""
    assert ANSI_ESCAPE_RE.search(out) is None
    assert ANSI_ESCAPE_RE.search(err) is None


def test_main_print_mode_no_color(monkeypatch, capsys):
    from hazzel import agent

    monkeypatch.setattr(agent, "run", lambda m, p: ("mocked reply", [], None))
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    monkeypatch.setenv("NO_COLOR", "1")

    with pytest.raises(SystemExit) as exc:
        main_module.main(["-p", "hi"])

    assert exc.value.code == EXIT_OK
    out, err = capsys.readouterr()
    assert "mocked reply" in out
    assert ANSI_ESCAPE_RE.search(out) is None
    assert ANSI_ESCAPE_RE.search(err) is None
