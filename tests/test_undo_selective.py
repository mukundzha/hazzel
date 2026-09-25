from hazzel import config, safety


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    safety.clear_undo_log()
    assert safety.pending_count() == 0
    assert safety.redo_count() == 0


def test_clean_undo_restores(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "a.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-fixed\nl3\n")
    out = safety.undo()
    assert out and out[0][1] == "restored"
    assert target.read_text() == "l1\nl2\nl3\n"


def test_undo_keeps_user_edit_elsewhere(tmp_path, monkeypatch):
    # The X-post case: agent fixes line2, user edits line1 after. Undo
    # reverts only the agent hunk.
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "b.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-fixed\nl3\n")
    target.write_text("l1-user\nl2-fixed\nl3\n")
    out = safety.undo()
    assert out and out[0][1].startswith("merged")
    assert target.read_text() == "l1-user\nl2\nl3\n"


def test_undo_conflict_keeps_file_and_event(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "c.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-user\nl3\n")
    out = safety.undo()
    assert out and out[0][1].startswith("kept")
    assert target.read_text() == "l1\nl2-user\nl3\n"
    assert safety.pending_count() == 1


def test_undo_force_discards_user_edit(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "d.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-user\nl3\n")
    out = safety.undo(force=True)
    assert out and out[0][1] == "restored"
    assert target.read_text() == "l1\nl2\nl3\n"


def test_preview_changes_nothing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "e.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1-user\nl2-fixed\nl3\n")
    prev = safety.preview_undo()
    assert prev and "merges" in prev[0][1]
    assert target.read_text() == "l1-user\nl2-fixed\nl3\n"
    assert safety.pending_count() == 1


def test_redo_reapplies_clean_undo(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "f.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-fixed\nl3\n")
    safety.undo()
    assert target.read_text() == "l1\nl2\nl3\n"
    out = safety.redo()
    assert out and out[0][1] == "redone"
    assert target.read_text() == "l1\nl2-fixed\nl3\n"


def test_redo_keeps_newer_user_edit(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "g.txt"
    target.write_text("l1\nl2\nl3\n")
    safety.checkpoint(target, "l1\nl2-fixed\nl3\n")
    target.write_text("l1\nl2-fixed\nl3\n")
    safety.undo()
    target.write_text("l1\nl2\nl3-user\n")
    out = safety.redo()
    assert out and out[0][1].startswith("reapplied")
    assert target.read_text() == "l1\nl2-fixed\nl3-user\n"


def test_new_file_keeps_user_edit(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "new.txt"
    safety.checkpoint(target, "agent\n")
    target.write_text("agent\n")
    target.write_text("agent\nuser\n")
    out = safety.undo()
    assert out and out[0][1].startswith("kept")
    assert target.exists()
    out = safety.undo(force=True)
    assert not target.exists()


def test_paths_filter_undoes_one_file(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("a1\n")
    b.write_text("b1\n")
    safety.checkpoint(a, "a2\n")
    a.write_text("a2\n")
    safety.checkpoint(b, "b2\n")
    b.write_text("b2\n")
    out = safety.undo(paths=[str(a)])
    assert len(out) == 1 and out[0][0] == str(a)
    assert a.read_text() == "a1\n"
    assert b.read_text() == "b2\n"


def test_legacy_checkpoint_without_post_is_blind(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "h.txt"
    target.write_text("v1\n")
    safety.checkpoint(target)
    target.write_text("v2-user\n")
    out = safety.undo()
    assert out and out[0][1] == "restored"
    assert target.read_text() == "v1\n"


def test_persist_v2_roundtrip_keeps_post(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    target = tmp_path / "p.txt"
    target.write_text("l1\nl2\n")
    safety.checkpoint(target, "l1\nl2-fixed\n")
    target.write_text("l1-user\nl2-fixed\n")
    saved_events = list(safety._events)
    safety._events.clear()
    safety._redo.clear()
    safety._persist_load()
    assert safety.pending_count() == len(saved_events)
    out = safety.undo()
    assert out and out[0][1].startswith("merged")
    assert target.read_text() == "l1-user\nl2\n"
