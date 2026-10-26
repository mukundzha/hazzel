import re

import pytest

import hazzel
from hazzel import __main__ as main_mod


def _installed_version():
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("hazzel")
    except PackageNotFoundError:
        return None


def test_source_version_is_parseable():
    assert re.fullmatch(r"\d+\.\d+\.\d+([.-].+)?", hazzel.__version__), hazzel.__version__


def test_installed_metadata_matches_source_version():
    installed = _installed_version()
    if installed is None:
        pytest.skip("hazzel is not installed in this environment")
    assert installed == hazzel.__version__, (
        f"installed metadata says {installed} but source says {hazzel.__version__} — "
        "run `pip install -e . --no-deps` after bumping __version__"
    )


def test_cli_version_reports_source_version():
    assert main_mod._version() == hazzel.__version__


def test_show_version_prints_all_four_lines(capsys, monkeypatch):
    import sys
    from pathlib import Path

    from hazzel import config as config_mod
    from hazzel import ui

    monkeypatch.setattr(config_mod, "get_current_display_name", lambda: "Groq / test-model")
    monkeypatch.setattr(config_mod, "CONFIG_FILE", Path("/tmp/fake/config.json"))
    ui.show_version()
    out = capsys.readouterr().out
    assert f"Hazzel {hazzel.__version__}" in out
    assert f"Python {sys.version.split()[0]}" in out
    assert "Groq / test-model" in out
    assert "/tmp/fake/config.json" in out


def test_version_command_registered_everywhere():
    """The issue's done-when list: palette, /help, /docs, README."""
    from pathlib import Path

    from hazzel import ui
    from hazzel.docs import get_sections
    from hazzel.ui import input as ui_input
    from hazzel.ui.help_docs import _HELP_SECTIONS

    assert callable(ui.show_version)
    assert any(c["name"] == "/version" for c in ui_input.SLASH_COMMANDS)
    assert any("/version" in row[0] for _title, rows in _HELP_SECTIONS for row in rows)
    assert any("/version" in line for _title, lines in get_sections() for line in lines)
    readme = Path(__file__).resolve().parents[1] / "README.md"
    assert "/version" in readme.read_text()


def test_main_dispatches_version_command():
    import inspect

    assert '"/version"' in inspect.getsource(main_mod.main)
