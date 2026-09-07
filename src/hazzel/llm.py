from hazzel.providers import get_provider
from hazzel.agent import TOOLS as tools


def chat(messages):
    provider = get_provider()
    return provider.chat(messages, tools)
