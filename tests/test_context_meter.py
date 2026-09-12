from hazzel import agent, config, ui


def test_plain_formats():
    assert ui.format_context_plain(0, 1_000_000) == "0.0%/1.0M (auto)"
    assert ui.format_context_plain(65536, 131072) == "50.0%/131k (auto)"
    assert ui.format_context_plain(100, 0) == "0.1%/131k (auto)"
    assert ui.format_context_plain(None, None) == "0.0%/131k (auto)"


def test_meter_colors():
    assert "\x1b[32m" in ui.format_context_meter(100, 1_000_000)
    assert "\x1b[33m" in ui.format_context_meter(60000, 100000)
    assert "\x1b[31m" in ui.format_context_meter(90000, 100000)
    assert ui.format_context_meter(0, 100).endswith("\x1b[2m")


def test_catalog_windows():
    assert config.DEFAULT_CONTEXT_WINDOW > 0
    for m in config.MODEL_CATALOG:
        assert isinstance(m.get("context"), int) and m["context"] > 0
    assert config.get_context_window() > 0


def test_agent_context_usage():
    used, window = agent.context_usage([{"role": "system", "content": "hello world"}])
    assert used > 0
    assert window == config.get_context_window()
    used_empty, _ = agent.context_usage([])
    assert used_empty > 0


def test_agent_context_tracks_session_burn():
    agent._session_usage["input"] = 13000
    try:
        used, _ = agent.context_usage([])
        assert used == 13000
    finally:
        agent._session_usage["input"] = 0


def test_usage_body_context_line():
    session = {"input": 100, "output": 50, "cached": 0, "calls": 2}
    lines = list(ui._usage_body(session, None, (65536, 131072)))
    text = "\n".join(getattr(line, "plain", "") for line in lines if hasattr(line, "plain"))
    assert "50.0%/131k (auto)" in text
