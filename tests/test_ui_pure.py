from hazzel import ui


def test_format_elapsed():
    assert ui._format_elapsed(0.012) == "12ms"
    assert ui._format_elapsed(1.25) == "1.2s"
    assert ui._format_elapsed(None) == ""


def test_relativize_detail():
    assert ui._relativize_detail("/home/mukund/Code/Hazzel/hn.py") in ("hn.py", "/home/mukund/Code/Hazzel/hn.py")
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
    for keyword in ("/model", "/pr", "/plan", "/prove", "/undo", "@", "gh auth login"):
        assert keyword in body


def test_show_docs_prints(capsys):
    ui.show_docs()
    out = capsys.readouterr().out
    assert "Hazzel docs" in out
    assert "/pr" in out


def test_clip_paste_normalizes_and_caps():
    out = ui._clip_paste("a\r\n  indented\r\nb")
    assert out == "a\n  indented\nb"
    many = "\n".join(f"line {i}" for i in range(100))
    assert len(ui._clip_paste(many).split("\n")) == ui.MAX_PASTE_LINES
    assert len(ui._clip_paste("x" * 9000)) == ui.MAX_PASTE_CHARS


def test_visual_rows_counts_newlines():
    assert ui._visual_rows(["a\nb\nc"]) == 2
    assert ui._visual_rows(["a"]) == 0
