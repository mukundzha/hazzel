import pytest

from hazzel import agent, config
from hazzel import skills as skill_mod


@pytest.fixture(autouse=True)
def _clean_cache():
    skill_mod.clear_skill_cache()
    yield
    skill_mod.clear_skill_cache()


@pytest.fixture()
def proj_skills(tmp_path, monkeypatch):
    proj = tmp_path / ".hazzel" / "skills"
    proj.mkdir(parents=True)
    monkeypatch.setattr(skill_mod, "_project_skill_dirs", lambda: [(proj, "project")])
    monkeypatch.setattr(skill_mod, "_global_skill_dirs", lambda: [])
    return proj


def _make_skill(base, name, description="Does things.", body="# Skill\nFollow me."):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n")
    return d


def test_parse_frontmatter():
    meta, body = skill_mod._parse_frontmatter("---\nname: foo\ndescription: Does x.\n---\n\n# Hi\n")
    assert meta["name"] == "foo"
    assert meta["description"] == "Does x."
    assert body.startswith("# Hi")


def test_parse_no_frontmatter():
    meta, body = skill_mod._parse_frontmatter("# Just body\n")
    assert meta == {}
    assert "Just body" in body


def test_discover_finds_project_skill(proj_skills):
    _make_skill(proj_skills, "review-buddy")
    found = skill_mod.discover_skills()
    assert [s["name"] for s in found] == ["review-buddy"]
    assert found[0]["description"] == "Does things."
    assert found[0]["source"] == "project"


def test_discover_skips_missing_and_invalid(proj_skills):
    (proj_skills / "empty-dir").mkdir()
    bad = proj_skills / "bad name!"
    bad.mkdir()
    (bad / "SKILL.md").write_text("---\nname: bad name!\n---\nbody\n")
    _make_skill(proj_skills, "good-one")
    assert [s["name"] for s in skill_mod.discover_skills()] == ["good-one"]


def test_discover_project_wins_on_clash(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    proj.mkdir()
    glob = tmp_path / "glob"
    glob.mkdir()
    _make_skill(proj, "same")
    _make_skill(glob, "same")
    monkeypatch.setattr(skill_mod, "_project_skill_dirs", lambda: [(proj, "project")])
    monkeypatch.setattr(skill_mod, "_global_skill_dirs", lambda: [(glob, "global")])
    found = skill_mod.discover_skills()
    assert len(found) == 1 and found[0]["source"] == "project"


def test_load_skill_ok_with_siblings(proj_skills):
    d = _make_skill(proj_skills, "helper")
    (d / "notes.md").write_text("extra")
    out = skill_mod.load_skill("helper")
    assert "loaded" in out
    assert "Follow me." in out
    assert "notes.md" in out


def test_load_skill_missing(proj_skills):
    _make_skill(proj_skills, "helper")
    assert skill_mod.load_skill("nope_xyz").startswith("Skill not found: nope_xyz")


def test_load_skill_suggests_close(proj_skills):
    _make_skill(proj_skills, "helper")
    assert "helper" in skill_mod.load_skill("help")


def test_load_skill_invalid_name():
    assert skill_mod.load_skill("../escape").startswith("Invalid skill name")


def test_load_skill_empty_lists(proj_skills):
    _make_skill(proj_skills, "helper")
    out = skill_mod.load_skill("")
    assert "helper" in out


def test_load_skill_caps_body(proj_skills, monkeypatch):
    _make_skill(proj_skills, "big", body="x" * (skill_mod.MAX_SKILL_CHARS + 100))
    out = skill_mod.load_skill("big")
    assert "chars skipped" in out
    assert len(out) < skill_mod.MAX_SKILL_CHARS + 2000


def test_list_skills_empty(proj_skills):
    assert skill_mod.list_skills().startswith("No skills installed")


def test_agent_registers_skill_tool():
    assert "skill" in agent.TOOL_NAMES
    assert "skill" in agent.PLAN_TOOL_NAMES
    assert "skill" in agent.PARALLEL_SAFE
    assert agent._normalize_tool_name("load_skill") == "skill"
    assert agent._normalize_tool_name("skills") == "skill"
    assert "skill" in agent.SYSTEM_PROMPT


def test_agent_run_tool_skill_lists(proj_skills):
    _make_skill(proj_skills, "helper")
    out = agent.run_tool("skill", {"name": ""})
    assert "helper" in out


def test_agent_run_tool_skill_loads(proj_skills):
    _make_skill(proj_skills, "helper")
    out = agent.run_tool("skill", {"name": "helper"})
    assert "Follow me." in out


def test_skills_prompt_empty(monkeypatch):
    monkeypatch.setattr(skill_mod, "discover_skills", lambda: [])
    assert skill_mod.skills_prompt() == ""


def test_skills_prompt_lists(monkeypatch):
    monkeypatch.setattr(
        skill_mod, "discover_skills",
        lambda: [{"name": "helper", "description": "Helps.", "path": None, "source": "project"}],
    )
    prompt = skill_mod.skills_prompt()
    assert "helper" in prompt and "skill(name)" in prompt


def test_neutral_plan_mode(monkeypatch):
    monkeypatch.setattr(config, "is_plan_enabled", lambda: True)
    assert any(t["function"]["name"] == "skill" for t in agent._active_tools())


def test_find_skill_ok_and_missing(proj_skills):
    _make_skill(proj_skills, "helper")
    assert skill_mod.find_skill("helper")["name"] == "helper"
    assert skill_mod.find_skill("nope_xyz") is None
    assert skill_mod.find_skill("../escape") is None


def test_get_skill_body(proj_skills):
    _make_skill(proj_skills, "helper")
    assert "Follow me." in skill_mod.get_skill_body("helper")
    assert skill_mod.get_skill_body("nope_xyz") is None


def test_expand_mentions_resolves_skill(proj_skills):
    from hazzel.mentions import expand_mentions

    _make_skill(proj_skills, "helper")
    ctx, attached, _, errors, attached_skills = expand_mentions("@helper fix it")
    assert attached_skills == ["helper"]
    assert attached == ["helper"]
    assert not errors
    assert '<skill name="helper">' in ctx
    assert "Follow me." in ctx


def test_expand_mentions_file_wins_over_skill(proj_skills, tmp_path, monkeypatch):
    from hazzel import config as _config
    from hazzel.mentions import expand_mentions

    monkeypatch.setattr(_config, "PROJECT_ROOT", tmp_path)
    (tmp_path / "helper").write_text("file body here")
    _make_skill(proj_skills, "helper")
    ctx, attached, _, errors, attached_skills = expand_mentions("@helper")
    assert attached_skills == []
    assert '<file path="helper">' in ctx


def test_expand_mentions_empty_still_five_tuple():
    from hazzel.mentions import expand_mentions

    assert expand_mentions("plain text") == ("", [], {}, [], [])


def test_skill_candidates_prefix(monkeypatch):
    from hazzel import ui as _ui

    monkeypatch.setattr(
        skill_mod, "discover_skills",
        lambda: [
            {"name": "helper", "description": "", "path": None, "source": "project"},
            {"name": "other", "description": "", "path": None, "source": "project"},
        ],
    )
    assert _ui._skill_candidates("hel") == ["helper"]
    assert _ui._skill_candidates("zzz-no-match") == []


def test_mention_candidates_include_skills(proj_skills):
    from hazzel import ui as _ui

    _make_skill(proj_skills, "helper")
    cands, _ = _ui._mention_candidates("helpe")
    assert "helper" in cands


def test_select_skill_fallback_number(monkeypatch):
    import sys

    from hazzel import ui as _ui

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *a: "2")
    skills = [{"name": "a", "description": "", "source": "project"}, {"name": "b", "description": "", "source": "project"}]
    assert _ui.select_skill(skills)["name"] == "b"


def test_select_skill_fallback_cancel(monkeypatch):
    import sys

    from hazzel import ui as _ui

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr("builtins.input", lambda *a: "")
    assert _ui.select_skill([{"name": "a", "description": "", "source": "project"}]) is None
    assert _ui.select_skill([]) is None
