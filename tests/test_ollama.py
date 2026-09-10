import io
import json
from unittest.mock import MagicMock, patch

from hazzel import config
from hazzel.providers import ollama


def _resp(payload):
    raw = io.BytesIO(json.dumps(payload).encode())
    resp = MagicMock()
    resp.__enter__.return_value = raw
    resp.__exit__.return_value = False
    return resp


def test_fetch_local_models():
    with patch("urllib.request.urlopen", return_value=_resp({"models": [{"name": "qwen3:8b"}, {"name": "llama3.1:8b"}, {}]})):
        assert ollama.fetch_local_models() == ["qwen3:8b", "llama3.1:8b"]


def test_fetch_local_models_offline():
    with patch("urllib.request.urlopen", side_effect=OSError("down")):
        assert ollama.fetch_local_models() == []


def test_tags_url_strips_v1(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://box:11434/v1")
    assert ollama._tags_url() == "http://box:11434/api/tags"
    monkeypatch.setenv("OLLAMA_HOST", "http://box:11434")
    assert ollama._tags_url() == "http://box:11434/api/tags"


def test_catalog_merges_local_only(monkeypatch):
    monkeypatch.setattr(ollama, "fetch_local_models", lambda: ["my-custom:7b", "llama3.1:8b"])
    catalog = config.get_catalog()
    ids = [m["id"] for m in catalog if m["provider"] == "ollama"]
    assert "my-custom:7b" in ids
    assert ids.count("llama3.1:8b") == 1
    entry = next(m for m in catalog if m["id"] == "my-custom:7b")
    assert entry["provider_display"] == "Ollama"
