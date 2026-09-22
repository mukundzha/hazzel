from hazzel import ui
from hazzel.ui import _state


def test_ui_state_proxy_console(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(ui, "console", sentinel)

    assert ui.console is sentinel
    assert _state.console is sentinel


def test_ui_state_proxy_quiet(monkeypatch):
    monkeypatch.setattr(_state, "_quiet", True)

    assert ui._quiet is True

    monkeypatch.setattr(ui, "_quiet", False)

    assert _state._quiet is False
    assert ui.is_quiet() is False


def test_ui_state_proxy_loader(monkeypatch):
    sentinel = object()

    monkeypatch.setattr(ui, "_loader", sentinel)

    assert ui._loader is sentinel
    assert _state._loader is sentinel


def test_confirm_accepts_yes_variants(monkeypatch):
    monkeypatch.setattr(ui, "_print_mode", False)
    monkeypatch.setattr(ui, "_pause_loader", lambda: False)
    monkeypatch.setattr(ui, "_resume_loader", lambda _was_active: None)

    for answer in ("y", "Y", "yes", "Yes"):
        monkeypatch.setattr("builtins.input", lambda _prompt, value=answer: value)
        assert ui.confirm("Allow?") is True

    for answer in ("n", "no", ""):
        monkeypatch.setattr("builtins.input", lambda _prompt, value=answer: value)
        assert ui.confirm("Allow?") is False


def test_format_elapsed():
    assert ui._format_elapsed(0.012) == "12ms"
    assert ui._format_elapsed(1.25) == "1.2s"
    assert ui._format_elapsed(None) == ""


def test_relativize_detail():
    assert ui._relativize_detail("/home/mukund/Code/Hazzel/hn.py") in (
        "hn.py",
        "/home/mukund/Code/Hazzel/hn.py",
    )
    assert ui._relativize_detail("utcfromtimestamp") == "utcfromtimestamp"
    assert ui._relativize_detail("/etc/hostname") == "/etc/hostname"


def test_visible_len_strips_ansi():
    assert ui._visible_len("  \x1b[1m❯\x1b[0m hello") == 9


def test_stream_buffers_silently(capsys):
    ui.begin_stream()
    ui.push_stream_token("hello ")
    ui.push_stream_token("world")
    assert ui.end_stream() == "hello world"
    assert capsys.readouterr().out == ""


def test_show_reasoning_empty_is_noop(capsys):
    ui.show_reasoning("")
    ui.show_reasoning("   ")
    out = capsys.readouterr().out
    assert "thinking" not in out


def test_docs_cover_core_workflows():
    from hazzel.docs import get_sections

    body = "\n".join(line for _, lines in get_sections() for line in lines)
    for keyword in ("/model", "/status", "/commit", "/plan", "/undo", "@"):
        assert keyword in body


def test_show_docs_prints(capsys):
    ui.show_docs()
    out = capsys.readouterr().out
    assert "Hazzel docs" in out
    assert "/plan" in out


def test_clip_paste_normalizes_and_caps():
    out = ui._clip_paste("a\r\n  indented\r\nb")
    assert out == "a\n  indented\nb"
    many = "\n".join(f"line {i}" for i in range(100))
    assert len(ui._clip_paste(many).split("\n")) == ui.MAX_PASTE_LINES
    assert len(ui._clip_paste("x" * 9000)) == ui.MAX_PASTE_CHARS


def test_visual_rows_counts_newlines():
    assert ui._visual_rows(["a\nb\nc"]) == 2
    assert ui._visual_rows(["a"]) == 0


def test_fuzzy_score_exact_beats_gappy():
    assert ui._fuzzy_score("abc", "abc") < ui._fuzzy_score("abc", "a_b_c")
    assert ui._fuzzy_score("xyz", "abc") is None
    assert ui._fuzzy_score("", "abc") is None


def test_fuzzy_score_boundary_bonus():
    assert ui._fuzzy_score("rc", "run_command.py") < ui._fuzzy_score(
        "rc", "src/hazzel/formatter.py"
    )


def test_mention_fuzzy_transpositions():
    cands, _ = ui._mention_candidates("agnt")
    assert any("agent" in c for c in cands)
    cands, _ = ui._mention_candidates("sfty")
    assert any("safety.py" in c for c in cands)
    cands, _ = ui._mention_candidates("runcmd")
    assert any("run_command.py" in c for c in cands)


def test_mention_exact_still_first():
    cands, _ = ui._mention_candidates("safety")
    assert any("safety.py" in c for c in cands[:2])


def test_slash_prefix_and_substring():
    names = [c["name"] for c in ui._filter_slash_commands("/mod")]
    assert "/model" in names
    names = [c["name"] for c in ui._filter_slash_commands("/odel")]
    assert "/model" in names


def test_slash_fuzzy_transpositions():
    assert ui._filter_slash_commands("/mdl") == []
    assert ui._filter_slash_commands("/stus") == []
    assert ui._filter_slash_commands("status") == []
    assert ui._filter_slash_commands("/zzzzzz") == []


def test_format_result_preview_short():
    out = ui._format_result_preview("hello world")
    assert out == "hello world"
    assert "more lines" not in out


def test_format_result_preview_truncates_lines():
    lines = "\n".join(f"line {i}" for i in range(20))
    out = ui._format_result_preview(lines)
    assert "more lines" in out
    preview_lines = out.splitlines()
    assert len(preview_lines) == 9  # 8 preview + 1 suffix line


def test_format_result_preview_empty():
    assert ui._format_result_preview("") == "(no output)"
    assert ui._format_result_preview(None) == "(no output)"
    assert ui._format_result_preview("\n\n\n") == "(no output)"


def test_format_result_preview_no_truncation_marker_when_short():
    out = ui._format_result_preview("one\ntwo\nthree")
    assert "more lines" not in out
    assert out == "one\ntwo\nthree"


def test_show_tool_result_signature_accepts_new_param():
    """show_tool must accept a result kwarg (backward compatible)."""
    import io
    from rich.console import Console

    buf = io.StringIO()
    old_console = ui.console
    ui.console = Console(file=buf, width=100, force_terminal=False)
    ui._quiet = False
    ui._loader = None
    try:
        ui.show_tool("read_file", "pyproject.toml", success=True, result="hello\nworld")
    finally:
        ui._quiet = False
        ui._loader = None
        ui.console = old_console

    out = buf.getvalue()
    assert "read_file" in out
    assert "hello" in out
    assert "world" in out


def test_show_tool_loader_rows_are_capped(monkeypatch):
    from hazzel.ui import input as ui_input

    class Loader:
        def __init__(self):
            self.updates = 0

        def update(self, _body):
            self.updates += 1

    loader = Loader()
    monkeypatch.setattr(ui, "_quiet", False)
    monkeypatch.setattr(ui, "_tool_rows", [])
    monkeypatch.setattr(ui, "_loader", loader)
    monkeypatch.setattr(ui, "_live_body", lambda _text: "body")
    monkeypatch.setattr(ui_input, "_MAX_TOOL_ROWS", 3)

    ui.show_tool("read_file", "pyproject.toml", success=True, result="one\ntwo\nthree")

    assert len(ui._tool_rows) == 3
    assert loader.updates == 2
