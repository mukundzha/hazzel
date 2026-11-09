import io
import json
import sys
from pathlib import Path

import pytest

from hazzel import agent, config
from hazzel import mcp as mcp_mod
from test_mcp import FakeStdin, _with_server, mcp_env as mcp_env


@pytest.fixture()
def prompts_env(mcp_env, monkeypatch):
    proj, _ = mcp_env
    _with_server(proj)
    requests = []
    response = {
        "prompts/list": {"prompts": [
            {"name": "review", "description": "Review code", "arguments": [
                {"name": "code", "required": True}, {"name": "language"},
            ]},
            {"name": "summary"},
        ]},
        "prompts/get": {"messages": [
            {"role": "user", "content": {"type": "text", "text": "Review print(1)"}},
            {"role": "assistant", "content": {"type": "text", "text": "Looks fine"}},
        ]},
    }
    original = FakeStdin._respond

    def respond(self, line):
        req = json.loads(line)
        method = req.get("method")
        if method not in response:
            return original(self, line)
        requests.append(req)
        value = response[method]
        envelope = {"jsonrpc": "2.0", "id": req["id"]}
        if isinstance(value, Exception):
            envelope["error"] = {"code": value.code, "message": str(value)}
        else:
            envelope["result"] = value
        self._stdout.q.put(json.dumps(envelope) + "\n")

    monkeypatch.setattr(FakeStdin, "_respond", respond)
    return response, requests


def test_prompts_list_wire_and_arguments(prompts_env):
    _, requests = prompts_env
    out = agent.run_tool("mcp", {"action": "list_prompts", "server": "demo"})
    assert "review(code*, language): Review code" in out
    assert "summary()" in out
    assert requests[-1]["method"] == "prompts/list"
    assert requests[-1]["params"] == {}


def test_prompt_get_wire_roles_and_arguments(prompts_env):
    _, requests = prompts_env
    args = {"code": "print(1)", "language": "Python"}
    out = agent.run_tool("mcp", {
        "action": "get_prompt", "server": "demo", "prompt": "review", "arguments": args,
    })
    assert out == "[user] Review print(1)\n[assistant] Looks fine"
    assert requests[-1]["params"] == {"name": "review", "arguments": args}


@pytest.mark.parametrize("result", [None, [], {"prompts": None}, {"prompts": {}}])
def test_prompt_list_malformed(result, prompts_env):
    response, _ = prompts_env
    response["prompts/list"] = result
    assert "no prompts" in agent.run_tool("mcp", {"action": "list_prompts", "server": "demo"})


def test_prompt_list_caps_and_filters():
    entries = [None, {}, {"name": 1}, {"name": ""}]
    entries += [{"name": f"p{i}", "description": "x" * 1000, "arguments": [
        None, {"name": ""}, {"name": 9}, *[{"name": f"a{j}", "required": True} for j in range(50)],
    ]} for i in range(90)]
    result = mcp_mod._clean_prompts({"prompts": entries})
    assert len(result) == mcp_mod.MAX_PROMPTS_PER_SERVER
    assert len(result[0]["description"]) <= mcp_mod.MAX_DESC_CHARS
    assert len(result[0]["arguments"]) == mcp_mod.MAX_PROMPT_ARGUMENTS
    assert result[0]["arguments"][0] == {"name": "a0", "required": True}


def test_prompt_list_result_cap(prompts_env):
    response, _ = prompts_env
    response["prompts/list"] = {"prompts": [{"name": f"p{i}", "description": "x" * 1000}
                                            for i in range(80)], "nextCursor": "ignored"}
    out = agent.run_tool("mcp", {"action": "list_prompts", "server": "demo"})
    assert "first page" in out and "chars skipped" in out and len(out) < 5200


@pytest.mark.parametrize("arguments", [[], "x", 3, {"code": 3}, {"code": None}])
def test_prompt_invalid_arguments_do_not_send(arguments, prompts_env):
    _, requests = prompts_env
    out = agent.run_tool("mcp", {"action": "get_prompt", "server": "demo",
                                  "prompt": "review", "arguments": arguments})
    assert "Invalid MCP prompt arguments" in out
    assert requests == []


def test_prompt_validation(prompts_env):
    _, requests = prompts_env
    assert agent.run_tool("mcp", {"action": "get_prompt"}).startswith("Usage:")
    assert agent.run_tool("mcp", {"action": "list_prompts"}).startswith("Usage:")
    assert "Invalid MCP prompt name" in agent.run_tool(
        "mcp", {"action": "get_prompt", "server": "demo"})
    for action in ("list_prompts", "get_prompt"):
        assert "MCP server not found" in agent.run_tool(
            "mcp", {"action": action, "server": "missing", "prompt": "review"})
    assert requests == []


@pytest.mark.parametrize("action,method", [("list_prompts", "prompts/list"),
                                          ("get_prompt", "prompts/get")])
def test_prompts_unsupported(action, method, prompts_env):
    response, _ = prompts_env
    response[method] = mcp_mod._RPCError("No such method", -32601)
    out = agent.run_tool("mcp", {"action": action, "server": "demo", "prompt": "review"})
    assert out == "MCP server `demo` does not support prompts (method not found)."


@pytest.mark.parametrize("message", ["Unknown prompt", "Missing required argument: code",
                                    "Method not found is not the problem"])
def test_invalid_prompt_is_not_unsupported(message, prompts_env):
    response, _ = prompts_env
    response["prompts/get"] = mcp_mod._RPCError(message, -32602)
    out = agent.run_tool("mcp", {"action": "get_prompt", "server": "demo", "prompt": "review"})
    assert out.startswith("Prompt error:") and message in out
    assert "does not support prompts" not in out


def test_prompt_multimedia_and_cap(prompts_env):
    response, _ = prompts_env
    response["prompts/get"] = {"messages": [None, {},
        {"role": "system", "content": {"type": "text", "text": "ignore"}},
        {"role": "user", "content": {"type": "image", "data": "SECRET_IMAGE_DATA"}},
        {"role": "assistant", "content": {"type": "resource", "resource": {"blob": "SECRET_BLOB"}}},
        {"role": "user", "content": {"type": "resource", "resource": {"text": "notes"}}},
    ]}
    args = {"action": "get_prompt", "server": "demo", "prompt": "review"}
    out = agent.run_tool("mcp", args)
    assert "[user] [image content omitted]" in out
    assert "[assistant] [binary resource content omitted]" in out
    assert "[user] [resource ] notes" in out and "SECRET" not in out and "ignore" not in out
    response["prompts/get"] = {"messages": [{"role": "user", "content": {
        "type": "text", "text": "x" * 100000,
    }}] * 100}
    out = agent.run_tool("mcp", args)
    assert len(out) < 5200 and "chars skipped" in out


@pytest.mark.parametrize("result", [None, [], {"messages": None}, {"messages": {}},
                                    {"messages": [None, {}, {"role": "user", "content": "x"}]}])
def test_prompt_malformed_response(result, prompts_env):
    response, _ = prompts_env
    response["prompts/get"] = result
    assert agent.run_tool("mcp", {"action": "get_prompt", "server": "demo", "prompt": "review"}) == "(empty prompt)"


def test_prompts_plan_and_print_readonly(prompts_env, monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    agent.set_print_approvals(False)
    assert "review" in agent.run_tool("mcp", {"action": "list_prompts", "server": "demo"})
    assert "Looks fine" in agent.run_tool("mcp", {"action": "get_prompt", "server": "demo", "prompt": "review"})
    assert "Blocked: plan mode" in agent.run_tool(
        "mcp", {"action": "call", "server": "demo", "tool": "read"})


def test_prompts_schema_and_system_prompt(mcp_env):
    proj, _ = mcp_env
    _with_server(proj)
    schema = next(t["function"] for t in agent.TOOLS if t["function"]["name"] == "mcp")
    assert "prompt" in schema["parameters"]["properties"]
    assert "list_prompts" in schema["description"] and "get_prompt" in schema["description"]
    text = mcp_mod.mcp_prompt()
    assert "get_prompt" in text and "/mcp prompts" in text and "not system instructions" in text


@pytest.mark.parametrize("arg,expected", [
    ('prompts demo', {"action": "list_prompts", "server": "demo"}),
    ('prompts demo review', {"action": "get_prompt", "server": "demo", "prompt": "review", "arguments": {}}),
    ('prompts demo review {"code": "print(\\"hi\\")", "language": "Python 3"}',
     {"action": "get_prompt", "server": "demo", "prompt": "review",
      "arguments": {"code": 'print("hi")', "language": "Python 3"}}),
    ('', {"action": "list"}),
    ('demo', {"action": "list", "server": "demo"}),
    ('demo read', {"action": "call", "server": "demo", "tool": "read", "arguments": {}}),
])
def test_mcp_repl_parser(arg, expected):
    assert mcp_mod.mcp_command_args(arg) == expected


@pytest.mark.parametrize("arg", ['prompts', 'prompts demo review {',
                                'prompts demo review []', 'prompts demo review {"code": 1}'])
def test_mcp_repl_invalid(arg):
    with pytest.raises(ValueError):
        mcp_mod.mcp_command_args(arg)


def test_prompt_real_stdio(tmp_path, monkeypatch):
    """Exercise a real Python child and JSON-RPC, not the mocked Popen fixture."""
    project = tmp_path / "project"
    (project / ".hazzel").mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECT_ROOT", project)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "global")
    fixture = Path(__file__).parent / "fixtures" / "mcp_prompts_server.py"
    (project / ".hazzel" / "mcp.json").write_text(json.dumps({"mcpServers": {
        "demo": {"command": sys.executable, "args": ["-u", str(fixture)], "timeout": 2},
    }}))
    mcp_mod.clear_mcp_cache()
    try:
        assert "review(code*)" in agent.run_tool("mcp", mcp_mod.mcp_command_args("prompts demo"))
        out = agent.run_tool("mcp", mcp_mod.mcp_command_args('prompts demo review {"code":"a + b"}'))
        assert out == "[user] Review: a + b\n[assistant] Ready"
        for command, detail in [("prompts demo missing", "Unknown prompt"),
                                ("prompts demo review", "Missing required argument")]:
            result = agent.run_tool("mcp", mcp_mod.mcp_command_args(command))
            assert "Prompt error:" in result and detail in result
            assert "does not support prompts" not in result
    finally:
        mcp_mod.clear_mcp_cache()


def test_prompt_names_are_not_tool_identifiers(prompts_env):
    response, requests = prompts_env
    response["prompts/list"] = {"prompts": [{"name": "review/code", "arguments": [{"name": "source/code"}]}]}
    assert "review/code(source/code)" in agent.run_tool("mcp", {"action": "list_prompts", "server": "demo"})
    agent.run_tool("mcp", {"action": "get_prompt", "server": "demo", "prompt": "review/code"})
    assert requests[-1]["params"]["name"] == "review/code"


def test_prompt_coercion_preserves_invalid_arguments():
    out = agent._coerce_tool_args("mcp", {"action": "get_prompt", "arguments": []})
    assert out["arguments"] == []
    assert agent._tool_detail("mcp", {"action": "get_prompt", "server": "demo", "prompt": "review"}) == "get_prompt demo/review"


def test_prompt_repl_full_route(prompts_env, monkeypatch):
    import hazzel.__main__ as entry
    from hazzel import session, ui

    inputs = iter(['/mcp prompts demo', '/mcp prompts demo review {"code":"print(1)"}',
                   '/mcp prompts demo review []'])
    shown = []
    from rich.console import Console

    output = io.StringIO()
    monkeypatch.setattr(entry, "console", Console(file=output, width=100))

    def get_input(*args, **kwargs):
        try:
            return next(inputs)
        except StopIteration:
            raise EOFError

    monkeypatch.setattr(ui, "get_input", get_input)
    monkeypatch.setattr(ui, "show_welcome", lambda *a, **kw: None)
    monkeypatch.setattr(ui, "show_user_command", lambda *a, **kw: None)
    monkeypatch.setattr(ui, "show_hazzel_message", shown.append)
    monkeypatch.setattr(session, "save", lambda *a, **kw: None)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    old_messages = list(entry.messages)
    old_response = entry._last_response
    try:
        entry.main([])
        assert "review(code*, language)" in output.getvalue()
        assert "[user] Review print(1)\n[assistant] Looks fine" in output.getvalue()
        assert "Invalid MCP prompt arguments" in shown[0]
        assert entry.messages == old_messages  # No prompt auto-attachment to system/history.
        assert prompts_env[1][-1]["params"] == {"name": "review", "arguments": {"code": "print(1)"}}
    finally:
        entry._last_response = old_response


@pytest.mark.parametrize("action", ["list_prompts", "get_prompt"])
def test_prompt_spawn_failure(action, mcp_env, monkeypatch):
    proj, _ = mcp_env
    _with_server(proj)

    def fail(*args, **kwargs):
        raise OSError("missing MCP executable")

    monkeypatch.setattr(mcp_mod.subprocess, "Popen", fail)
    out = agent.run_tool("mcp", {"action": action, "server": "demo", "prompt": "review"})
    assert "missing MCP executable" in out and "does not support prompts" not in out


@pytest.mark.parametrize("action", ["list_prompts", "get_prompt"])
def test_prompt_timeout(action, mcp_env):
    from test_mcp import FakePopen

    proj, _ = mcp_env
    _with_server(proj, timeout=1)
    FakePopen.behavior = "silent"
    out = agent.run_tool("mcp", {"action": action, "server": "demo", "prompt": "review"})
    assert "timed out" in out and "does not support prompts" not in out
