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
