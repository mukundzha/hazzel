import io
import json

import pytest

from hazzel import agent, config, ui
from hazzel.agent.dispatch import (
    _active_tools,
    is_print_readonly,
    run_tool,
    set_print_approvals,
)
from hazzel.agent.fastpath import try_fast_path
from hazzel.print_mode import (
    EXIT_CANCELLED,
    EXIT_OK,
    EXIT_TURN_FAILED,
    EXIT_USAGE,
    build_parser,
    combine_prompt,
    read_piped_stdin,
    run_print,
)


@pytest.fixture(autouse=True)
def _clean_print_state():
    yield
    set_print_approvals(None)
    ui.set_print_mode(False)
    ui.set_auto_approve(False)
    ui.set_quiet(False)
    agent.reset_conversation_state()


# --- argument parsing ---


def test_parser_print_text():
    args = build_parser().parse_args(["-p", "summarize this"])
    assert args.prompt == "summarize this"
    assert args.approve is False
    assert args.output_format == "text"


def test_parser_print_bare_and_flags():
    args = build_parser().parse_args(["-p", "-y", "--output-format", "json"])
    assert args.prompt == ""
    assert args.approve is True
    assert args.output_format == "json"


def test_parser_no_print_is_repl():
    args = build_parser().parse_args([])
    assert args.prompt is None


def test_parser_bad_format_exits_2():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["-p", "x", "--output-format", "yaml"])
    assert exc.value.code == 2


# --- prompt / stdin handling ---


def test_combine_prompt_text_only():
    assert combine_prompt("do it", None) == "do it"


def test_combine_stdin_only():
    assert combine_prompt("", "piped body") == "piped body"
    assert combine_prompt(None, "piped body") == "piped body"


def test_combine_both():
    out = combine_prompt("explain", "some diff")
    assert out.startswith("explain")
    assert "some diff" in out
    assert "<piped_input>" in out


def test_combine_neither_is_none():
    assert combine_prompt("", None) is None
    assert combine_prompt(None, "   ") is None


class _TtyStdin(io.StringIO):
    def isatty(self):
        return True


class _PipeStdin(io.StringIO):
    def isatty(self):
        return False


def test_read_piped_stdin_tty_is_none():
    assert read_piped_stdin(_TtyStdin("hi")) is None


def test_read_piped_stdin_pipe_returns_text():
    assert read_piped_stdin(_PipeStdin("hello")) == "hello"


def test_read_piped_stdin_truncates():
    from hazzel.print_mode import STDIN_MAX_CHARS

    out = read_piped_stdin(_PipeStdin("z" * (STDIN_MAX_CHARS + 100)))
    assert len(out) < STDIN_MAX_CHARS + 200
    assert "truncated" in out


# --- read-only gating ---


def test_active_tools_readonly_is_plan_set():
    set_print_approvals(False)
    names = {t.get("function", {}).get("name") for t in _active_tools()}
    assert names == {"list_files", "read_file", "search_files", "glob", "git_status", "git_diff", "web_search", "fetch_url", "skill", "mcp", "jobs"}


def test_active_tools_approve_is_full_set():
    set_print_approvals(True)
    names = {t.get("function", {}).get("name") for t in _active_tools()}
    assert "write_file" in names and "run_command" in names


def test_run_tool_blocked_without_approve():
    set_print_approvals(False)
    assert is_print_readonly()
    for tool, argv in [
        ("write_file", {"path": "probe_xyz_tmp.txt", "content": "x"}),
        ("edit_file", {"path": "probe_xyz_tmp.txt", "old_text": "a", "new_text": "b"}),
        ("apply_edits", {"edits": [{"path": "probe_xyz_tmp.txt", "old_text": "a", "new_text": "b"}]}),
        ("run_command", {"command": "echo hi"}),
    ]:
        assert run_tool(tool, argv).startswith("Blocked: print mode is read-only")


def test_run_tool_reads_still_work():
    set_print_approvals(False)
    rows = run_tool("list_files", {"path": "src/hazzel"})
    assert isinstance(rows, list) and any(r == "agent/" for r in rows)


def test_fast_delete_defers_when_readonly():
    set_print_approvals(False)
    assert try_fast_path([], "delete missing_xyz_123.txt") is None


def test_fast_delete_answers_when_interactive():
    reply, _, _ = try_fast_path([], "delete missing_xyz_123.txt")
    assert "No such file" in reply


def test_fast_read_print_mode_returns_content(capsys):
    from hazzel import ui as _ui

    _ui.set_print_mode(True)
    reply, _, _ = try_fast_path([], "read pyproject.toml")
    out, _ = capsys.readouterr()
    assert out == ""
    assert "hazzel" in reply


# --- silent UI ---


def test_confirm_print_mode_no_input(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("input() must not be called in print mode")

    monkeypatch.setattr("builtins.input", _boom)
    ui.set_print_mode(True)
    ui.set_auto_approve(False)
    assert ui.confirm("Allow?") is False
    ui.set_auto_approve(True)
    assert ui.confirm("Allow?") is True


def test_loader_and_diff_stay_silent(capsys):
    ui.set_print_mode(True)
    ui.show_loader("Working…")
    assert ui._loader is None
    ui.show_diff("+added\n-removed\n")
    ui.show_file_viewer("x.py", "body", 1, 1)
    out, _ = capsys.readouterr()
    assert out == ""


# --- run_print end to end (provider mocked) ---


def _ok_run(messages, user_input):
    return "mocked reply", [], None


def test_run_print_text(monkeypatch, capsys):
    monkeypatch.setattr(agent, "run", _ok_run)
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    code = run_print("summarize this", approve=False, output_format="text")
    out, err = capsys.readouterr()
    assert code == EXIT_OK
    assert out == "mocked reply\n"
    assert err == ""


def test_run_print_json(monkeypatch, capsys):
    monkeypatch.setattr(agent, "run", _ok_run)
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    code = run_print("summarize this", approve=False, output_format="json")
    out, _ = capsys.readouterr()
    assert code == EXIT_OK
    payload = json.loads(out)
    assert payload["success"] is True
    assert payload["response"] == "mocked reply"
    assert payload["model"]
    assert "input" in payload["usage"]


def test_run_print_no_key_exits_usage(monkeypatch, capsys):
    monkeypatch.setattr(config, "has_any_key", lambda: False)
    monkeypatch.setattr(config, "get_current_provider", lambda: "groq")
    code = run_print("hi", approve=False, output_format="text")
    out, err = capsys.readouterr()
    assert code == EXIT_USAGE
    assert out == ""
    assert "API key" in err


def test_run_print_contact_failure_exits_1(monkeypatch, capsys):
    monkeypatch.setattr(agent, "run", lambda m, u: ("Unable to contact the model: boom", [], None))
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    code = run_print("hi", approve=False, output_format="text")
    out, err = capsys.readouterr()
    assert code == EXIT_TURN_FAILED
    assert out == ""
    assert "Unable to contact" in err


def test_run_print_exception_exits_1(monkeypatch, capsys):
    def _raise(messages, user_input):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(agent, "run", _raise)
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    assert run_print("hi") == EXIT_TURN_FAILED


def test_run_print_cancelled_exits_130(monkeypatch, capsys):
    def _cancel(messages, user_input):
        raise KeyboardInterrupt

    monkeypatch.setattr(agent, "run", _cancel)
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    assert run_print("hi") == EXIT_CANCELLED


def test_run_print_resets_global_flags(monkeypatch):
    monkeypatch.setattr(agent, "run", _ok_run)
    monkeypatch.setattr(config, "has_any_key", lambda: True)
    run_print("hi", approve=True)
    assert not is_print_readonly()
    assert ui.is_print_mode() is False
    assert ui.is_quiet() is False


# --- __main__ wiring ---


def test_main_version(capsys):
    from hazzel.__main__ import main

    main(["--version"])
    out, _ = capsys.readouterr()
    assert out.startswith("Hazzel ")


def test_main_print_delegates(monkeypatch, capsys):
    import hazzel.__main__ as entry
    import hazzel.print_mode as pm

    seen = {}

    def _fake_run_print(prompt, approve=False, output_format="text"):
        seen.update(prompt=prompt, approve=approve, output_format=output_format)
        return EXIT_OK

    monkeypatch.setattr(pm, "run_print", _fake_run_print)
    monkeypatch.setattr(pm, "read_piped_stdin", lambda: None)
    with pytest.raises(SystemExit) as exc:
        entry.main(["-p", "do the thing", "-y"])
    assert exc.value.code == EXIT_OK
    assert seen == {"prompt": "do the thing", "approve": True, "output_format": "text"}


def test_main_print_empty_exits_2(monkeypatch):
    import hazzel.__main__ as entry
    import hazzel.print_mode as pm

    monkeypatch.setattr(pm, "read_piped_stdin", lambda: None)
    with pytest.raises(SystemExit) as exc:
        entry.main(["-p", ""])
    assert exc.value.code == EXIT_USAGE
