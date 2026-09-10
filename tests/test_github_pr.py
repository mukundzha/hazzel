from unittest.mock import patch

from hazzel import github
from hazzel.agent import _plan_blocked, run_tool
from hazzel.tools.github_pr import github_pr


def test_parse_number():
    assert github.parse_number("#12") == 12
    assert github.parse_number("7") == 7
    assert github.parse_number("abc") is None
    assert github.parse_number("0") is None


def test_pr_validation_no_subprocess():
    assert github.pr_view("abc")[0] is False
    assert github.pr_diff("")[0] is False
    assert github.pr_create("")[0] is False
    assert github.pr_merge("x", "bad")[0] is False
    assert github.pr_comment("1", "")[0] is False


def test_gh_missing_graceful():
    with patch("hazzel.github.git.is_repo", return_value=True):
        with patch("hazzel.github.subprocess.run", side_effect=FileNotFoundError()):
            ok, out = github.pr_list()
            assert ok is False
            assert "gh CLI" in out


def test_tool_unknown_action():
    assert github_pr("nope").startswith("Tool error")


def test_close_validation():
    assert github_pr("close", "")[0:10].startswith("Tool error") or "required" in github_pr("close", "")
    assert github.pr_close("abc")[0] is False


def test_tool_plan_blocking():
    assert _plan_blocked("github_pr", {"action": "list"}) is False
    assert _plan_blocked("github_pr", {"action": "create"}) is True
    assert _plan_blocked("github_pr", {"action": "merge"}) is True


def test_run_tool_dispatch_readonly():
    with patch("hazzel.agent.github_pr", return_value="No open pull requests.") as m:
        out = run_tool("github_pr", {"action": "list"})
        assert "No open" in out
        m.assert_called_once()


def test_run_command_blocks_raw_gh():
    out = run_tool("run_command", {"command": "gh pr create --title x"})
    assert out.startswith("Blocked: use github_pr")


def test_suggest_draft():
    title, body = github.suggest_pr_draft("diff --git a/x", " M x")
    assert title
    assert "Summary" in body
