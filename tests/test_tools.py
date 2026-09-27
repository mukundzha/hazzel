from pathlib import Path
from unittest.mock import patch

from hazzel.tools.edit_file import edit_file
from hazzel.tools.fetch_url import fetch_url
from hazzel.tools.glob_files import glob_files
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
    assert isinstance(rows, list) and any(r == "agent/" for r in rows)


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


def test_glob_required():
    assert glob_files("").startswith("Glob pattern is required")
    assert glob_files("  ").startswith("Glob pattern is required")


def test_glob_missing_path():
    assert glob_files("*.py", "definitely_missing_dir_xyz").startswith("Path does not exist")


def test_glob_outside():
    assert glob_files("*.py", "../outside_root_xyz").startswith("Path is outside the project root")


def test_glob_file_path():
    assert glob_files("*.py", "pyproject.toml").startswith("Path is not a directory")


def test_glob_recursive():
    out = glob_files("**/test_tools.py")
    assert "tests/test_tools.py" in out


def test_glob_star_stays_in_root():
    assert glob_files("*.toml") == ["pyproject.toml"]


def test_glob_no_match_hints_recursion():
    out = glob_files("zzz_no_such_name_xyz.py")
    assert out.startswith("No matches") and "**/zzz_no_such_name_xyz.py" in out


def test_glob_skips_vcs_and_caches():
    out = glob_files("**/*", "src")
    assert not any(row.startswith(".git/") for row in out)
    assert not any("__pycache__" in row for row in out)
    assert "src/hazzel/tools/glob_files.py" in out


def test_glob_caps_output():
    out = glob_files("**/*")
    assert out[-1].startswith("[more than 100 matches") or out[-1].startswith("[stopped after")


def test_glob_dirs_only():
    out = glob_files("*/")
    assert out
    assert all(row.endswith("/") for row in out)
    assert "src/" in out


def test_glob_brace_group():
    out = glob_files("**/*.{toml,cfg}")
    assert "pyproject.toml" in out
    assert not any(row.endswith(".py") for row in out)


def test_glob_character_class():
    assert "pyproject.toml" in glob_files("**/[pt]*.toml")


def test_glob_sorted_and_capped():
    out = glob_files("**/*.py", "src")
    assert out == sorted(out)
    assert any(row.endswith("toolspec.py") for row in out)


def test_glob_leading_dot_slash():
    assert glob_files("./pyproject.toml") == ["pyproject.toml"]


def test_glob_registered_as_read_only_tool():
    from hazzel import agent

    assert "glob" in agent.TOOL_NAMES
    assert "glob" in agent.PLAN_TOOL_NAMES
    assert "glob" in agent.PARALLEL_SAFE
    schema = next(t for t in agent.TOOLS if t["function"]["name"] == "glob")
    assert schema["function"]["parameters"]["required"] == ["pattern"]


def test_glob_dispatch_reaches_the_tool():
    from hazzel import agent

    assert agent.run_tool("glob", {"pattern": "pyproject.toml"}) == ["pyproject.toml"]
    assert "src/hazzel/tools/glob_files.py" in agent.run_tool("find_files", {"glob": "**/glob_files.py"})


def test_write_too_large():
    assert write_file("x_tmp.py", "y" * 8001).startswith("Content too large")


def test_edit_anchor_missing():
    assert edit_file("README.md", "zzz_anchor_missing_xyz", "new") == (
        "Text to replace was not found. Use search_files or read_file "
        "to copy the exact text, including whitespace."
    )


def test_edit_missing_file():
    assert edit_file("missing_xyz.py", "a", "b").startswith("File does not exist")


def test_fetch_missing_url():
    assert fetch_url("").startswith("URL is required")


def test_fetch_bad_scheme():
    assert fetch_url("ftp://example.com/x").startswith("Unsupported")


def test_fetch_blocked_local():
    assert fetch_url("http://localhost/x").startswith("Blocked")


def test_fetch_html_to_text():
    class FakeHeaders(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    class FakeResp:
        headers = FakeHeaders({"Content-Type": "text/html"})
        def read(self, n=-1):
            return b"<html><body><h1>Hi</h1><script>var x=1</script><p>Hello world</p></body></html>"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", return_value=FakeResp()):
        out = fetch_url("https://example.com/docs")
    assert "Hello world" in out
    assert "var x=1" not in out


def test_fetch_prefers_main_content():
    class FakeHeaders(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    class FakeResp:
        headers = FakeHeaders({"Content-Type": "text/html"})
        def read(self, n=-1):
            return b"<html><body><nav>Nav links</nav><main><p>Real content</p></main><footer>Foot</footer></body></html>"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", return_value=FakeResp()):
        out = fetch_url("https://example.com/docs")
    assert "Real content" in out
    assert "Nav links" not in out
    assert "Foot" not in out


def test_fetch_dedupes_repeated_lines():
    class FakeHeaders(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    class FakeResp:
        headers = FakeHeaders({"Content-Type": "text/html"})
        def read(self, n=-1):
            return b"<html><body><main><p>Item</p><p>Item</p><p>Item</p><p>Other</p></main></body></html>"
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", return_value=FakeResp()):
        out = fetch_url("https://example.com/docs")
    assert out.count("Item") == 1
    assert "Other" in out


def test_fetch_condenses_long_page():
    class FakeHeaders(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    body = "".join(f"<p>Topic alpha release notes version {i} details here</p>" for i in range(200))

    class FakeResp:
        headers = FakeHeaders({"Content-Type": "text/html"})
        def read(self, n=-1):
            return ("<html><body><main>" + body + "</main></body></html>").encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", return_value=FakeResp()):
        out = fetch_url("https://example.com/docs")
    assert "Condensed" in out
    assert "alpha" in out
    assert len(out) < 2600


def test_fetch_query_boost():
    class FakeHeaders(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    filler = "".join(f"<p>Filler line number {i} about nothing much at all here</p>" for i in range(150))
    target = "<p>Astronomy telescope orbit calibration results published</p><p>Second telescope orbit measurement confirms drift</p>"

    class FakeResp:
        headers = FakeHeaders({"Content-Type": "text/html"})
        def read(self, n=-1):
            return ("<html><body><main>" + filler + target + "</main></body></html>").encode()
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False

    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", return_value=FakeResp()):
        out = fetch_url("https://example.com/docs", query="telescope orbit")
    assert "telescope" in out
    assert "Filler line number 149" not in out
