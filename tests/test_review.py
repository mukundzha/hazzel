from unittest.mock import patch

from hazzel import agent, git_review, ui
from hazzel.tools.review_diff import review_diff


class _Resp:
    def __init__(self, content):
        self.content = content


def _files():
    return [{"status": "M", "path": "a.py", "added": 3, "deleted": 1}]


def test_prompt_shape():
    assert "Verdict" in git_review.REVIEW_SYSTEM
    assert "[Critical]" in git_review.REVIEW_SYSTEM
    assert "security" in git_review.REVIEW_SYSTEM.lower()


def test_no_changes():
    with patch("hazzel.git.changed_files", return_value=(True, [], "")):
        assert review_diff() == "No unstaged changes to review."


def test_model_review():
    with patch("hazzel.git.changed_files", return_value=(True, _files(), "")):
        with patch("hazzel.git.diff_text", return_value=(True, "diff --git a/a.py\n+x=1")):
            with patch("hazzel.providers.get_provider") as provider:
                provider.return_value.chat.return_value = _Resp("Verdict: APPROVE — safe.")
                out = review_diff()
    assert out == "Verdict: APPROVE — safe."


def test_offline_fallback():
    with patch("hazzel.git.changed_files", return_value=(True, _files(), "")):
        with patch("hazzel.git.diff_text", return_value=(True, "diff --git a/a.py\n+x=1")):
            with patch("hazzel.providers.get_provider", side_effect=OSError("down")):
                out = review_diff()
    assert "a.py" in out
    assert "verify by hand" in out


def test_staged_scope():
    with patch("hazzel.git.diff_file", return_value=(True, "diff --git a/a.py\n+x=1")):
        with patch("hazzel.providers.get_provider") as provider:
            provider.return_value.chat.return_value = _Resp("Verdict: APPROVE — safe.")
            out = review_diff(True, "a.py")
    assert out == "Verdict: APPROVE — safe."
    body = provider.return_value.chat.call_args[0][0][1]["content"]
    assert "staged changes in a.py" in body


def test_tool_routes_through_agent():
    with patch("hazzel.agent.review_diff", return_value="Verdict: APPROVE — safe.") as fn:
        out = agent.run_tool("review_diff", {"staged": True, "path": "a.py"})
    assert out == "Verdict: APPROVE — safe."
    fn.assert_called_once_with(True, "a.py", False)


def test_tool_alias():
    assert agent._normalize_tool_name("review") == "review_diff"
    assert agent._normalize_tool_name("code_review") == "review_diff"


def test_coerce_alias_before_default():
    assert agent._coerce_tool_args("review_diff", {"file": "a.py"})["path"] == "a.py"
    assert agent._coerce_tool_args("review_diff", {})["path"] == "."
    assert agent._coerce_tool_args("review_diff", {"path": "b.py", "file": "a.py"})["path"] == "b.py"


def test_parse_review_args():
    parse = git_review.parse_review_args
    assert parse("") == (False, ".", False)
    assert parse("--staged") == (True, ".", False)
    assert parse("--staged=false") == (False, ".", False)
    assert parse("--staged=0 src/x.py") == (False, "src/x.py", False)
    assert parse("--path=src/x.py") == (False, "src/x.py", False)
    assert parse("src/x.py --staged") == (True, "src/x.py", False)
    assert parse("--unknown") == (False, ".", False)
    assert parse("@a.py") == (False, "a.py", False)
    assert parse('@"my file.py"') == (False, "my file.py", False)
    assert parse("codebase") == (False, ".", True)
    assert parse("codebase --staged") == (True, ".", True)


def test_review_file_falls_back_to_content():
    with patch("hazzel.git.diff_file", return_value=(True, "No changes.")):
        with patch("hazzel.providers.get_provider") as provider:
            provider.return_value.chat.return_value = _Resp("Verdict: APPROVE — safe.")
            assert review_diff(False, "pyproject.toml") == "Verdict: APPROVE — safe."
    body = provider.return_value.chat.call_args[0][0][1]["content"]
    assert "full content" in body
    assert "hazzel" in body


def test_review_file_missing():
    with patch("hazzel.git.diff_file", return_value=(True, "No changes.")):
        out = review_diff(False, "nope_missing_xyz.py")
    assert "not a readable file" in out


def test_review_strips_mention():
    with patch("hazzel.git.diff_file", return_value=(True, "diff --git a/a.py\n+x=1")) as df:
        with patch("hazzel.providers.get_provider") as provider:
            provider.return_value.chat.return_value = _Resp("Verdict: APPROVE — safe.")
            assert review_diff(False, "@a.py") == "Verdict: APPROVE — safe."
    df.assert_called_once_with("a.py", False)


def test_review_codebase_combines():
    with patch("hazzel.git.changed_files", side_effect=[(True, _files(), ""), (True, [{"status": "A", "path": "b.py", "added": 5, "deleted": 0}], "")]):
        with patch("hazzel.git.diff_text", side_effect=[(True, "diff-u"), (True, "diff-s")]):
            with patch("hazzel.providers.get_provider") as provider:
                provider.return_value.chat.return_value = _Resp("Verdict: APPROVE — safe.")
                assert review_diff(False, ".", True) == "Verdict: APPROVE — safe."
    body = provider.return_value.chat.call_args[0][0][1]["content"]
    assert "whole codebase" in body
    assert "a.py" in body and "b.py" in body
    assert "diff-u" in body and "diff-s" in body


def test_review_codebase_empty():
    with patch("hazzel.git.changed_files", return_value=(True, [], "")):
        assert review_diff(False, ".", True) == "No changes to review in the whole codebase."


def test_show_review_scope(capsys):
    ui.show_review("Verdict: APPROVE — safe.", "a.py")
    assert "a.py" in capsys.readouterr().out


_SAMPLE = """Verdict: REQUEST CHANGES — undefined variable breaks runtime.

Findings:
[Critical]
src/hazzel/agent.py:495 — missing return.
  Fix: add the call.
[Minor]
src/hazzel/agent.py:144 — plan-mode note.

Good: Tool catalog updates are correct."""


def test_parse_review():
    verdict, sections, good = ui._parse_review(_SAMPLE)
    assert verdict.startswith("REQUEST CHANGES")
    assert [s for s, _ in sections] == ["Critical", "Minor"]
    assert "missing return" in sections[0][1][0]
    assert good.startswith("Tool catalog")


def test_show_review_structured(capsys):
    ui.show_review(_SAMPLE)
    out = capsys.readouterr().out
    assert "Code review" in out
    assert "3 findings" in out
    assert "REQUEST CHANGES" in out
    assert "[Critical]" in out
    assert "[Minor]" in out
    assert "1. src/hazzel/agent.py:495" in out
    assert "Fix findings" in out


def test_show_review_fallback(capsys):
    ui.show_review("No unstaged changes to review.")
    out = capsys.readouterr().out
    assert "No unstaged changes to review." in out


def test_show_review_approve_card(capsys):
    ui.show_review("Verdict: APPROVE — clean change.\n\nGood: Nothing notable, tests cover the branch.")
    out = capsys.readouterr().out
    assert "APPROVE" in out
    assert "✓ Good" in out
    assert "Clean — /commit when ready." in out
    assert "Fix findings" not in out
