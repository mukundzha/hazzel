from hazzel import agent
from hazzel.init_map import build_map


def test_build_map_structure_and_stack(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref\n")
    (tmp_path / "__pycache__").mkdir()
    out = build_map(tmp_path)
    assert "Python (pyproject)" in out
    assert "src/" in out and "src/main.py" in out
    assert ".git" not in out and "__pycache__" not in out
    assert "`/init`" in out


def test_build_map_empty(tmp_path):
    out = build_map(tmp_path)
    assert "unknown" in out and "(empty)" in out


def test_repo_instructions_are_included_in_system_prompt(tmp_path):
    (tmp_path / "AGENTS.md").write_text("# Repo instructions\n- Prefer `pytest`.\n", encoding="utf-8")
    prompt = agent.build_system_prompt(tmp_path)
    assert "Repo instructions" in prompt
    assert "Prefer `pytest`." in prompt


def test_missing_repo_instructions_leave_system_prompt_unchanged(tmp_path):
    assert agent.build_system_prompt(tmp_path) == agent.SYSTEM_PROMPT


def test_empty_repo_instructions_leave_system_prompt_unchanged(tmp_path):
    (tmp_path / "AGENTS.md").write_text("", encoding="utf-8")
    assert agent.build_system_prompt(tmp_path) == agent.SYSTEM_PROMPT


def test_repo_instructions_are_capped_and_non_utf8_is_replaced(tmp_path):
    content = b"\xff" + (b"x" * (agent.MAX_AGENTS_CHARS + 100))
    (tmp_path / "AGENTS.md").write_bytes(content)
    prompt = agent.build_system_prompt(tmp_path)
    assert "[AGENTS.md truncated at 4000 characters]" in prompt
    assert len(prompt.rsplit("Repository instructions from AGENTS.md:\n", 1)[1]) < agent.MAX_AGENTS_CHARS + 100
