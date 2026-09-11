from hazzel import config, ui


def _hist_file(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "HISTORY_FILE", tmp_path / "history")
    return config.HISTORY_FILE


def test_history_roundtrip_multiline(monkeypatch, tmp_path):
    _hist_file(monkeypatch, tmp_path)
    config.append_input_history("fix this\nline two")
    assert config.load_input_history() == ["fix this\nline two"]


def test_history_skips_empty_and_dup(monkeypatch, tmp_path):
    _hist_file(monkeypatch, tmp_path)
    config.append_input_history("   ")
    config.append_input_history("hello")
    config.append_input_history("hello")
    assert config.load_input_history() == ["hello"]


def test_history_caps_entries(monkeypatch, tmp_path):
    _hist_file(monkeypatch, tmp_path)
    monkeypatch.setattr(config, "HISTORY_MAX_ENTRIES", 3)
    for i in range(5):
        config.append_input_history(f"cmd {i}")
    assert config.load_input_history() == ["cmd 2", "cmd 3", "cmd 4"]


def test_history_tolerates_corrupt_lines(monkeypatch, tmp_path):
    path = _hist_file(monkeypatch, tmp_path)
    path.write_text('not json{{{\n"ok entry"\n', encoding="utf-8")
    assert config.load_input_history() == ["not json{{{", "ok entry"]


def test_clip_paste_normalizes_and_caps():
    out = ui._clip_paste("a\r\n  indented\r\nb")
    assert out == "a\n  indented\nb"
    many = "\n".join(f"line {i}" for i in range(100))
    assert len(ui._clip_paste(many).split("\n")) == ui.MAX_PASTE_LINES
    assert len(ui._clip_paste("x" * 9000)) == ui.MAX_PASTE_CHARS


def test_history_nav_bounds():
    hist = ["a", "b"]
    assert ui._history_up(hist, 2) == 1
    assert ui._history_up(hist, 0) == 0
    assert ui._history_down(hist, 0) == 1
    assert ui._history_down(hist, 2) == 2
    assert ui._history_up([], 0) == 0


def test_visual_rows_counts_newlines():
    assert ui._visual_rows(["a\nb\nc"]) == 2
    assert ui._visual_rows(["a"]) == 0
