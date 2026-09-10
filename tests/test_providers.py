from hazzel import config
from hazzel.providers import COMPAT_PROVIDERS, _ollama_base_url, create_provider


def test_compat_wiring():
    for provider, (name, base_url) in COMPAT_PROVIDERS.items():
        inst = create_provider(provider, "key", "model")
        assert inst.provider_name == name
        assert str(inst.client.base_url).rstrip("/") == base_url.rstrip("/")
        assert inst.model == "model"


def test_openai_unchanged():
    inst = create_provider("openai", "key", "gpt-4o")
    assert inst.provider_name == "OpenAI"
    assert "prompt_cache_key" in inst._create_kwargs([], [])
    deep = create_provider("deepseek", "key", "deepseek-chat")
    assert "prompt_cache_key" not in deep._create_kwargs([], [])


def test_ollama_keyless(monkeypatch):
    assert config.get_api_key("ollama") == "ollama"
    inst = create_provider("ollama", None, "llama3.1:8b")
    assert inst.provider_name == "Ollama"
    monkeypatch.setenv("OLLAMA_HOST", "http://box:11434/v1")
    assert _ollama_base_url() == "http://box:11434/v1"


def test_unknown_provider():
    try:
        create_provider("nope", "key", "m")
    except RuntimeError as error:
        assert "Unknown provider" in str(error)
    else:
        raise AssertionError("expected RuntimeError")


def test_catalog_valid():
    for m in config.get_catalog():
        assert m["provider"] in config.PROVIDER_ENV, m
        assert m["provider"] in config.PROVIDER_DISPLAY, m
        assert config.PROVIDER_DISPLAY[m["provider"]] == m["provider_display"], m
