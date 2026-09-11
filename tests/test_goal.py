from hazzel import agent, config


def _tmp_config(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "config.json")
    monkeypatch.setattr(config, "LEGACY_FILE", tmp_path / "legacy.json")
    monkeypatch.setattr(config, "_goal", None)


def test_goal_roundtrip(monkeypatch, tmp_path):
    _tmp_config(monkeypatch, tmp_path)
    try:
        assert config.get_goal() is None
        config.set_goal("  ship 1.4  ", " tests pass ")
        assert config.get_goal() == {"objective": "ship 1.4", "criteria": "tests pass"}
        config.set_goal("ship 1.4")
        assert config.get_goal() == {"objective": "ship 1.4", "criteria": ""}
        config.clear_goal()
        assert config.get_goal() is None
    finally:
        config._goal = None


def test_goal_persists(monkeypatch, tmp_path):
    _tmp_config(monkeypatch, tmp_path)
    try:
        config.set_goal("fix login", "pytest green")
        config._goal = None
        config._load_config()
        assert config.get_goal() == {"objective": "fix login", "criteria": "pytest green"}
    finally:
        config._goal = None


def test_goal_ignores_blank(monkeypatch, tmp_path):
    _tmp_config(monkeypatch, tmp_path)
    try:
        config.set_goal("   ")
        assert config.get_goal() is None
    finally:
        config._goal = None


def test_session_goal_note(monkeypatch):
    monkeypatch.setattr(config, "get_goal", lambda: {"objective": "fix login", "criteria": "pytest green"})
    note = agent._session_goal_note()
    assert "fix login" in note
    assert "pytest green" in note
    monkeypatch.setattr(config, "get_goal", lambda: {"objective": "fix login", "criteria": ""})
    note = agent._session_goal_note()
    assert "fix login" in note
    assert "Acceptance" not in note
    monkeypatch.setattr(config, "get_goal", lambda: None)
    assert agent._session_goal_note() == ""
    monkeypatch.setattr(config, "get_goal", _raise)
    assert agent._session_goal_note() == ""


def _raise():
    raise OSError("down")


def test_goal_run_task(monkeypatch):
    monkeypatch.setattr(config, "get_goal", lambda: {"objective": "fix login", "criteria": "pytest green"})
    task = agent.goal_run_task()
    assert "fix login" in task
    assert "pytest green" in task
    monkeypatch.setattr(config, "get_goal", lambda: {"objective": "fix login", "criteria": ""})
    assert "best judgment" in agent.goal_run_task()
    monkeypatch.setattr(config, "get_goal", lambda: None)
    assert agent.goal_run_task() is None
    monkeypatch.setattr(config, "get_goal", _raise)
    assert agent.goal_run_task() is None


def test_prompt_goal_criteria(monkeypatch):
    from hazzel import ui

    monkeypatch.setattr("builtins.input", lambda _: "tests pass")
    assert ui.prompt_goal_criteria() == "tests pass"
    monkeypatch.setattr("builtins.input", lambda _: "   ")
    assert ui.prompt_goal_criteria() == ""
    monkeypatch.setattr("builtins.input", _raise_input)
    assert ui.prompt_goal_criteria() == ""


def _raise_input(_prompt=""):
    raise EOFError
