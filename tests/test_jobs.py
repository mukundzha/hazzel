import time
from pathlib import Path

import pytest

from hazzel import agent, config
from hazzel import jobs as bg
from hazzel.jobs import split_background_marker


@pytest.fixture(autouse=True)
def _clean_jobs():
    bg.reset()
    yield
    bg.reset()


@pytest.fixture(autouse=True)
def _neutral_modes(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: False)


def _wait_done(job_id, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        out = bg.poll(job_id)
        if "running" not in out.splitlines()[0]:
            return out
        time.sleep(0.1)
    return bg.poll(job_id)


def test_split_background_marker():
    assert split_background_marker("sleep 5 &") == ("sleep 5", True)
    assert split_background_marker("sleep 5&") == ("sleep 5", True)
    assert split_background_marker("sleep 5") == ("sleep 5", False)
    # && is a shell operator, not a marker
    assert split_background_marker("a && b") == ("a && b", False)
    assert split_background_marker('echo "a & b"') == ('echo "a & b"', False)


def test_start_poll_list_roundtrip():
    receipt = bg.start("echo hello_bg_xyz", ".")
    assert "background job 1" in receipt
    out = _wait_done(1)
    assert "done" in out.splitlines()[0]
    assert "hello_bg_xyz" in out
    listing = bg.list_jobs()
    assert "echo hello_bg_xyz" in listing
    assert "1 · done" in listing


def test_poll_running_then_done():
    bg.start("sleep 3", ".")
    first = bg.poll(1)
    assert "running" in first.splitlines()[0]
    assert "sleep 3" in first.splitlines()[0]


def test_kill_long_job():
    import sys

    bg.start(f"{sys.executable} -c \"import time; time.sleep(30)\"", ".")
    assert "running" in bg.poll(1).splitlines()[0]
    msg = bg.kill(1)
    assert "Killed background job 1" in msg
    assert "killed" in bg.poll(1).splitlines()[0]


def test_wait_returns_done_output():
    bg.start("echo wait_done_xyz", ".")
    out = bg.wait(1, timeout=10)
    assert "done" in out.splitlines()[0]
    assert "wait_done_xyz" in out


def test_wait_timeout_reports_still_running():
    bg.start("sleep 30", ".")
    out = bg.wait(1, timeout=1)
    assert "running" in out.splitlines()[0]
    assert "still running after" in out


def test_wait_missing_job():
    assert bg.wait(99).startswith("No background job")
    assert bg.jobs_tool("wait", None).startswith("Usage")
    assert bg.jobs_tool("watch", None).startswith("Usage")


def test_clear_finished_keeps_running_and_deletes_logs():
    bg.start("echo clear_me_xyz", ".")
    bg.start("sleep 30", ".")
    deadline = time.monotonic() + 10
    while "done" not in bg.poll(1).splitlines()[0] and time.monotonic() < deadline:
        time.sleep(0.1)
    log_path = bg.poll(1).splitlines()[-1].split("Full log: ")[-1]
    assert Path(log_path).exists()
    msg = bg.jobs_tool("clear")
    assert "Cleared 1 finished job" in msg
    assert "1 running" in msg
    assert not Path(log_path).exists()
    assert "sleep 30" in bg.list_jobs()
    assert "clear_me_xyz" not in bg.list_jobs()


def test_clear_empty():
    assert bg.clear().startswith("No background jobs")
    assert bg.jobs_tool("clean").startswith("No background jobs")


def test_missing_job():
    assert bg.poll(99).startswith("No background job")
    assert bg.kill(99).startswith("No background job")
    assert bg.jobs_tool("poll", None).startswith("Usage")
    assert bg.jobs_tool("bogus").startswith("Usage")
    assert bg.list_jobs().startswith("No background jobs")


def test_agent_jobs_tool_and_alias():
    bg.start("echo via_agent_xyz", ".")
    out = agent.run_tool("jobs", {"action": "poll", "job_id": 1})
    # May still be running on a loaded box — either state is fine, job must exist.
    assert "Job 1" in out
    assert agent.run_tool("job", {"action": "list"}).startswith("Background jobs")
    assert agent._tool_cache_key("jobs", {"action": "list"}, "list") is None


def test_plan_blocks_kill_not_list(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    assert agent.run_tool("jobs", {"action": "list"}).startswith(
        ("No background jobs", "Background jobs")
    )
    assert agent.run_tool("jobs", {"action": "kill", "job_id": 1}).startswith("Blocked")
    assert agent.run_tool("jobs", {"action": "poll", "job_id": 1}).startswith(
        ("No background job", "Job 1")
    )
    assert agent.run_tool("jobs", {"action": "wait", "job_id": 1}).startswith(
        ("No background job", "Job 1")
    )
    assert agent.run_tool("jobs", {"action": "clear"}).startswith("Blocked")


def test_run_command_background_flag(monkeypatch):
    monkeypatch.setattr("hazzel.tools.run_command.ui.confirm", lambda *a, **k: True)
    out = agent.run_tool("run_command", {"command": "echo bg_flag_xyz", "background": True})
    assert "background job 1" in out
    done = _wait_done(1)
    assert "bg_flag_xyz" in done


def test_coerce_background_strings():
    assert agent._coerce_tool_args("run_command", {"command": "x", "background": "true"})[
        "background"
    ] is True
    coerced = agent._coerce_tool_args("jobs", {"action": "poll", "job_id": "2"})
    assert coerced["action"] == "poll"
    assert agent._coerce_tool_args("jobs", {"action": "wait", "timeout": "5"})["timeout"] == 5.0
    assert agent._tool_detail("jobs", {"action": "poll", "job_id": 2}) == "poll 2"
    assert agent._tool_detail("run_command", {"command": "sleep 5", "background": True}).endswith(
        "&"
    )
