from unittest.mock import patch

from hazzel import agent
from hazzel.tools.fetch_url import fetch_url
from hazzel.tools.web_search import web_search

DDG_HTML = b"""
<html><body>
<div class="result">
<a class="result__a" href="https://example.com/docs">Example Docs</a>
<a class="result__snippet" href="x">Docs snippet here</a>
</div>
<div class="result">
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fguide">Guide</a>
<a class="result__snippet" href="x">Guide snippet</a>
</div>
</body></html>
"""


class FakeHeaders(dict):
    def get(self, key, default=""):
        return super().get(key, default)


class FakeResp:
    def __init__(self, payload, content_type="text/html"):
        self._payload = payload
        self.headers = FakeHeaders({"Content-Type": content_type})

    def read(self, n=-1):
        return self._payload if n == -1 else self._payload[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_web_search_empty():
    assert web_search("").startswith("Search query is required")


def test_web_search_parses_and_unwraps():
    with patch("hazzel.tools.web_search.urllib.request.urlopen", return_value=FakeResp(DDG_HTML)):
        out = web_search("example", count=5)
    assert "1. Example Docs" in out
    assert "https://example.com/docs" in out
    assert "https://example.org/guide" in out
    assert "uddg" not in out


def test_web_search_count_clamped():
    with patch("hazzel.tools.web_search.urllib.request.urlopen", return_value=FakeResp(DDG_HTML)) as m:
        out = web_search("example", count=99)
    assert "2. Guide" in out
    assert m.called


def test_web_search_failure():
    with patch("hazzel.tools.web_search.urllib.request.urlopen", side_effect=Exception("down")):
        assert web_search("example").startswith("Tool error")


def test_web_search_no_results():
    with patch("hazzel.tools.web_search.urllib.request.urlopen", return_value=FakeResp(b"<html><body>nothing</body></html>")):
        assert web_search("zzz").startswith("No results found")


def _fetch_router(request, timeout=None):
    url = request.full_url if hasattr(request, "full_url") else str(request)
    if "one" in url:
        return FakeResp(b"<html><body><main><p>Alpha page content</p></main></body></html>")
    return FakeResp(b"<html><body><main><p>Beta page content</p></main></body></html>")


def test_fetch_multi_combines():
    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", side_effect=_fetch_router):
        out = fetch_url(urls=["https://example.com/one", "https://example.com/two"], query="alpha beta")
    assert "=== [1/2]" in out
    assert "=== [2/2]" in out
    assert "Alpha page content" in out
    assert "Beta page content" in out


def test_fetch_single_backward_compat():
    with patch("hazzel.tools.fetch_url.urllib.request.urlopen", side_effect=_fetch_router):
        out = fetch_url("https://example.com/one")
    assert out.startswith("Fetched https://example.com/one")


def test_agent_wiring():
    assert "web_search" in agent.TOOL_NAMES
    assert agent._normalize_tool_name("google") == "web_search"
    assert agent._normalize_tool_name("fetch_urls") == "fetch_url"
    assert "web_search" in agent.PLAN_TOOL_NAMES
    out = agent.run_tool("web_search", {"q": ""})
    assert out.startswith("Search query is required")
