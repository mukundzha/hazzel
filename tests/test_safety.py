from unittest.mock import patch

from hazzel import agent, config, safety
from hazzel.tools import run_command as rc


def _isolate_undo(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "cfg")
    safety.clear_undo_log()
    assert safety.pending_count() == 0


def test_checkpoint_undo_restores(tmp_path, monkeypatch):
    _isolate_undo(tmp_path, monkeypatch)
    target = tmp_path / "a.txt"
    target.write_text("v1")
    safety.checkpoint(target)
    target.write_text("v2")
    assert safety.undo() != []
    assert target.read_text() == "v1"
    assert safety.pending_count() == 0


def test_undo_removes_new_file(tmp_path, monkeypatch):
    _isolate_undo(tmp_path, monkeypatch)
    target = tmp_path / "new.txt"
    safety.checkpoint(target)
    target.write_text("hello")
    safety.undo()
    assert not target.exists()


def test_undo_skips_dir(tmp_path, monkeypatch):
    _isolate_undo(tmp_path, monkeypatch)
    d = tmp_path / "d"
    d.mkdir()
    safety._events.append((str(d), None))
    assert safety.undo() == []
    assert d.exists()
    safety._events.clear()
    safety._persist_save()


def test_per_file_cap(tmp_path, monkeypatch):
    _isolate_undo(tmp_path, monkeypatch)
    target = tmp_path / "cap.txt"
    target.write_text("x")
    for _ in range(safety.MAX_DEPTH_PER_FILE + 5):
        safety.checkpoint(target)
    assert len([1 for k, _, _ in safety._events if k == str(target)]) == safety.MAX_DEPTH_PER_FILE


def test_diff_truncates():
    out = safety.diff_text("f", "a\n" * 200, "b\n" * 200)
    assert "…diff truncated…" in out


def test_persist_roundtrip(tmp_path, monkeypatch):
    _isolate_undo(tmp_path, monkeypatch)
    target = tmp_path / "p.txt"
    target.write_text("orig")
    safety.checkpoint(target)
    target.write_text("changed")
    assert (config.CONFIG_DIR / "undo" / "index.json").exists()
    saved = list(safety._events)
    safety._events.clear()
    safety._persist_load()
    assert safety.pending_count() == len(saved)
    safety.undo()
    assert target.read_text() == "orig"


def test_is_safe_allowlists():
    assert rc.is_safe_command("ls") is True
    assert rc.is_safe_command("git status") is True
    assert rc.is_safe_command("git push") is False
    assert rc.is_safe_command("rm -rf /") is False
    assert rc.is_safe_command("echo hi | grep h") is False


def test_coerce_timeout_clamps():
    assert rc._coerce_timeout(None) == rc.DEFAULT_TIMEOUT
    assert rc._coerce_timeout(0) == 1
    assert rc._coerce_timeout(9999) == rc.MAX_TIMEOUT
    assert rc._coerce_timeout("bad") == rc.DEFAULT_TIMEOUT


def test_resolve_cwd_blocks_escape():
    try:
        rc._resolve_cwd("../outside_xyz")
    except ValueError as e:
        assert "outside" in str(e).lower()
    else:
        raise AssertionError("expected escape to be blocked")


def test_destructive_targets_checkpoint_rm_mv_cp(monkeypatch):
    seen = []
    monkeypatch.setattr(safety, "checkpoint", lambda p: seen.append(str(p)))
    monkeypatch.setattr(safety, "_persist_save", lambda: None)
    rc._checkpoint_destructive_targets("rm a.txt b.txt")
    assert len(seen) == 2
    seen.clear()
    rc._checkpoint_destructive_targets("mv a.txt dest.txt")
    assert any("dest.txt" in s for s in seen)
    seen.clear()
    rc._checkpoint_destructive_targets("cp a.txt copy.txt")
    assert any("copy.txt" in s for s in seen)
    seen.clear()
    rc._checkpoint_destructive_targets("echo hi")
    assert seen == []


def test_run_command_cancelled(monkeypatch):
    monkeypatch.setattr(rc.ui, "confirm", lambda *a, **k: False)
    out = rc.run_command("rm -rf important_stuff_xyz")
    assert out == "Command cancelled by user"


def test_run_command_preapproved_echo():
    out = rc.run_command("echo hello", preapproved=True)
    assert "hello" in out


def test_plan_blocks_writes_and_allows_reads(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    assert agent.run_tool("apply_edits", {"edits": []}).startswith("Blocked: plan mode")
    assert agent.run_tool("run_command", {"command": "ls"}).startswith("Blocked: plan mode")
    assert "Blocked" not in agent.run_tool("search_files", {"pattern": "x"})
    monkeypatch.setattr(config, "is_plan_enabled", lambda: False)


def test_run_tool_blocks_raw_git():
    out = agent.run_tool("run_command", {"command": "git commit -m x"})
    assert out.startswith("Blocked: use git_commit")


def test_run_tool_passes_commands_through():
    with patch.object(rc.ui, "confirm", return_value=True):
        out = agent.run_tool("run_command", {"command": "ls"})
        assert "Blocked" not in out
