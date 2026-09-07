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
    if len(_CACHE) > 4:
        oldest = next(iter(_CACHE))
        del _CACHE[oldest]
    return instance


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
    raise RuntimeError(f"Unknown provider: {provider}")
