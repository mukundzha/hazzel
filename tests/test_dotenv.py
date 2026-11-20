import os

from hazzel import config


def _load(monkeypatch, tmp_path, text):
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config._load_dotenv()


def test_loads_provider_key(monkeypatch, tmp_path):
    _load(monkeypatch, tmp_path, "GROQ_API_KEY=dotenv-groq-key\n")
    assert os.environ["GROQ_API_KEY"] == "dotenv-groq-key"
    assert config.get_api_key("groq") == "dotenv-groq-key"


def test_quoted_value(monkeypatch, tmp_path):
    _load(monkeypatch, tmp_path, "GROQ_API_KEY='quoted-groq-key'\n")
    assert os.environ["GROQ_API_KEY"] == "quoted-groq-key"


def test_inline_comment_stripped(monkeypatch, tmp_path):
    _load(monkeypatch, tmp_path, "GROQ_API_KEY=dotenv-groq-key # my groq key\n")
    assert os.environ["GROQ_API_KEY"] == "dotenv-groq-key"


def test_hash_inside_quotes_kept(monkeypatch, tmp_path):
    _load(monkeypatch, tmp_path, 'GROQ_API_KEY="key-#123"\n')
    assert os.environ["GROQ_API_KEY"] == "key-#123"


def test_real_environment_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "real-env-key")
    (tmp_path / ".env").write_text("GROQ_API_KEY=dotenv-groq-key\n", encoding="utf-8")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    config._load_dotenv()
    assert os.environ["GROQ_API_KEY"] == "real-env-key"


def test_unknown_keys_ignored(monkeypatch, tmp_path):
    monkeypatch.delenv("FOO", raising=False)
    _load(monkeypatch, tmp_path, "FOO=bar\n")
    assert "FOO" not in os.environ


def test_missing_file_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    config._load_dotenv()
    assert "GROQ_API_KEY" not in os.environ
