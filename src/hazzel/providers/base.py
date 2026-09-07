import time
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


RATE_LIMIT_ATTEMPTS = 3
RATE_LIMIT_DELAYS = (2.0, 4.0)


def is_rate_limit_error(error):
    text = str(error).lower()
    if "429" in text:
        return True
    return any(k in text for k in [
        "rate limit",
        "rate_limit",
        "ratelimit",
        "too many requests",
        "quota",
        "capacity",
        "overloaded",
        "server is busy",
        "try again later",
    ])


def rate_limit_message(provider_name):
    return (
        f"Rate limit reached on {provider_name} — requests are throttled, nothing is broken. "
        "Wait a minute and retry, or switch model with /model."
    )


def call_with_backoff(provider_name, fn, attempts=RATE_LIMIT_ATTEMPTS):
    last = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except Exception as error:
            if not is_rate_limit_error(error):
                raise
            last = error
            if i < attempts - 1:
                try:
                    time.sleep(RATE_LIMIT_DELAYS[min(i, len(RATE_LIMIT_DELAYS) - 1)])
                except Exception:
                    pass
    raise RuntimeError(rate_limit_message(provider_name)) from last


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    estimated: bool = False


@dataclass
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None


class BaseProvider(ABC):
    @abstractmethod
    def chat(self, messages, tools) -> ChatResponse:
        ...
