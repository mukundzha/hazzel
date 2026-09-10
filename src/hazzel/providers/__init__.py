from ..config import get_api_key, get_current_model, get_current_provider
from .base import BaseProvider


_CACHE: dict = {}


def get_provider() -> BaseProvider:
    provider = get_current_provider()
    model = get_current_model()
    key = get_api_key(provider)
    cache_key = (provider, model)
    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached
    instance = create_provider(provider, key, model)
    _CACHE[cache_key] = instance
    if len(_CACHE) > 8:
        oldest = next(iter(_CACHE))
        del _CACHE[oldest]
    return instance


COMPAT_PROVIDERS = {
    "gemini": ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai/"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com/v1"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1"),
}


def _ollama_base_url():
    import os
    return os.getenv("OLLAMA_HOST", "http://localhost:11434/v1")


def create_provider(provider, api_key, model):
    if provider == "groq":
        from .groq import GroqProvider
        return GroqProvider(api_key, model)
    if provider == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider(api_key, model)
    if provider == "mistral":
        from .mistral import MistralProvider
        return MistralProvider(api_key, model)
    if provider == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(api_key, model)
    if provider in COMPAT_PROVIDERS:
        from .openai import OpenAIProvider
        name, base_url = COMPAT_PROVIDERS[provider]
        return OpenAIProvider(api_key, model, base_url=base_url, provider_name=name)
    if provider == "ollama":
        from .openai import OpenAIProvider
        return OpenAIProvider(api_key or "ollama", model, base_url=_ollama_base_url(), provider_name="Ollama")
    raise RuntimeError(f"Unknown provider: {provider}")
