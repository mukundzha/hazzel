from pathlib import Path
from unittest.mock import patch

from hazzel.tools.edit_file import edit_file
from hazzel.tools.list_files import list_files
from hazzel.tools.read_file import read_file
from hazzel.tools.search_files import search_files
from hazzel.tools.write_file import write_file


def test_list_missing():
    assert list_files("definitely_missing_dir_xyz").startswith("Path does not exist")


def test_list_not_dir():
    assert list_files("pyproject.toml").startswith("Path is not a directory")


def test_list_outside():
    assert list_files("../outside_root_xyz").startswith("Path is outside the project root")


def test_list_ok():
    rows = list_files("src/hazzel")
    assert isinstance(rows, list) and any("agent.py" in r for r in rows)


def test_read_missing_suggests():
    assert read_file("agent_xyz.py").startswith("File does not exist")


def test_read_dir():
    assert read_file("src").startswith("Path is not a file")


def test_read_ok_numbered():
    out = read_file("pyproject.toml")
    assert "1|" in out.replace(" ", "")


def test_read_binary():
    with patch.object(Path, "read_text", side_effect=UnicodeDecodeError("utf-8", b"", 0, 1, "bad")):
        assert read_file("pyproject.toml").startswith("File is binary")


def test_search_no_match():
    out = search_files("zzz_no_match_xyz_123", "src/hazzel")
    assert out.startswith("No matches found")


def test_search_bad_regex():
    assert search_files("([bad", ".", True).startswith("Invalid regex")


def test_search_empty_pattern():
    assert search_files("").startswith("Search pattern is required")


def test_write_too_large():
    assert write_file("x_tmp.py", "y" * 8001).startswith("Content too large")


def test_edit_anchor_missing():
    assert edit_file("README.md", "zzz_anchor_missing_xyz", "new") == (
        "Text to replace was not found. Use search_files or read_file "
        "to copy the exact text, including whitespace."
    )


def test_edit_missing_file():
    assert edit_file("missing_xyz.py", "a", "b").startswith("File does not exist")
