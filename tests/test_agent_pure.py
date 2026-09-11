from unittest.mock import MagicMock, patch

from hazzel import agent, config
from hazzel.providers import base
from hazzel.providers.base import ChatResponse


def test_normalize_namespaced():
    assert agent._normalize_tool_name("repobrowser.print_tree") == "list_files"
    assert agent._normalize_tool_name("LIST_FILES") == "list_files"
    assert agent._normalize_tool_name("cat") == "read_file"
    assert agent._normalize_tool_name("nope_nothing") is None


def test_extract_reasoning_content():
    msg = MagicMock(reasoning_content="  why this works  ", content="answer")
    assert base.extract_reasoning(msg) == "  why this works  "


def test_extract_reasoning_thinking_blocks():
    think = MagicMock(type="thinking", thinking="step one")
    text = MagicMock(type="text", text="hi")
    resp = MagicMock(content=[think, text])
    assert base.extract_reasoning(resp) == "step one"


def test_extract_reasoning_absent():
    assert base.extract_reasoning(MagicMock(content="plain", reasoning_content=None)) is None
    assert ChatResponse(content="x").reasoning is None
    agent._note_reasoning("  ")
    assert agent.get_last_reasoning() is None
    agent._note_reasoning("first thought")
    agent._note_reasoning("second thought")
    assert agent.get_last_reasoning() == "first thought\n\nsecond thought"
    agent._turn_reasoning.clear()


def test_parse_packages():
    assert agent._parse_package_names("tabulate and colorama") == ["tabulate", "colorama"]
    assert agent._parse_package_names("rich[all]") == ["rich[all]"]
    assert agent._parse_package_names("the app and run it") is None
    assert agent._parse_package_names("dependencies") is None


def test_prove_predicates(monkeypatch):
    trace = [{"tool": "write_file", "detail": "a.py", "success": True, "result": "x", "exit_code": None}]
    monkeypatch.setattr(config, "is_prove_enabled", lambda: False)
    assert agent._should_prove(trace, "done") is False
    monkeypatch.setattr(config, "is_prove_enabled", lambda: True)
    assert agent._should_prove(trace, "done") is True
    monkeypatch.setattr(agent, "_detect_repo_harness", lambda: None)
    assert agent._should_prove([{"tool": "edit_file", "detail": "notes.md", "success": True}], "done") is False


def test_contact_error_format():
    assert agent._format_contact_error(RuntimeError("boom")).startswith("Unable to contact")
    assert agent._format_contact_error(RuntimeError("Rate limit reached on Groq")).startswith("Rate limit")


def test_rate_limit_backoff():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("429 rate limit")
        return "ok"

    with patch.object(base.time, "sleep", lambda s: None):
        assert base.call_with_backoff("Groq", flaky) == "ok"
    assert calls["n"] == 3


def test_safe_chat_heals_bad_tool():
    provider = MagicMock()
    provider.chat.side_effect = [
        RuntimeError("Tool call validation failed: attempted to call tool 'repobrowser.printtree'"),
        ChatResponse(content="recovered", tool_calls=[]),
    ]
    msgs = [{"role": "user", "content": "hi"}]
    assert agent._safe_chat(provider, msgs, agent.TOOLS).content == "recovered"
    assert provider.chat.call_count == 2


def test_fast_install(monkeypatch):
    with patch.object(agent, "run_tool", return_value="ok") as run:
        msgs = [{"role": "system", "content": "x"}]
        reply, trace, _ = agent.try_fast_path(msgs, "download tabulate and colorama")
        assert run.call_args[0][1]["command"] == "pip install tabulate colorama"
        assert reply == "Installed tabulate, colorama."


def test_fast_run_guards(monkeypatch):
    with patch.object(agent, "run_tool", return_value="10 passed"):
        msgs = [{"role": "system", "content": "x"}]
        assert agent.try_fast_path(msgs, "run pytest -q")[0] == "10 passed"
    assert agent.try_fast_path([{"role": "system", "content": "x"}], "run rm -rf /") is None
    assert agent.try_fast_path([{"role": "system", "content": "x"}], "run the tests") is None


def test_plan_blocks_writes(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    assert agent.run_tool("write_file", {"path": "a.py", "content": "x"}).startswith("Blocked: plan mode")
    assert agent.run_tool("edit_file", {"path": "a.py", "old_text": "x", "new_text": "y"}).startswith("Blocked: plan mode")
    assert agent.run_tool("run_command", {"command": "ls"}).startswith("Blocked: plan mode")
    assert agent.run_tool("git_commit", {"message": "x"}).startswith("Blocked: plan mode")
    assert agent.run_tool("git_branch", {"action": "create", "name": "x"}).startswith("Blocked: plan mode")
    assert {t["function"]["name"] for t in agent.PLAN_TOOLS} == {"list_files", "read_file", "search_files", "git_status", "git_diff", "git_branch", "github_pr", "fetch_url", "review_diff"}


def test_plan_allows_reads(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    assert "Blocked" not in agent.run_tool("git_branch", {"action": "list"})
    monkeypatch.setattr(config, "is_plan_enabled", lambda: False)
    assert "Blocked" not in agent.run_tool("git_branch", {"action": "list"})


def test_plan_fast_path_defers(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    msgs = [{"role": "system", "content": "x"}]
    assert agent.try_fast_path(msgs, "delete foo.py") is None
    assert agent.try_fast_path(msgs, "run pytest -q") is None
    assert agent.try_fast_path(msgs, "download tabulate") is None


def test_fast_fetch_falls_through_to_model():
    msgs = [{"role": "system", "content": "x"}]
    assert agent.try_fast_path(msgs, "fetch https://example.com/docs") is None
    assert agent.try_fast_path(msgs, "read https://example.com/docs") is None


def test_fast_context_variants():
    for query in ("get context of README.md", "context of README.md", "context README.md"):
        msgs = [{"role": "system", "content": "x"}]
        with patch.object(agent.ui, "show_file_viewer", lambda *a: None):
            reply, trace, _ = agent.try_fast_path(msgs, query)
        assert "README.md" in reply
