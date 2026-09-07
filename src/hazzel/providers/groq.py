from .base import BaseProvider, ChatResponse, ToolCall, Usage, call_with_backoff


def _extract_usage(resp):
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return None
        prompt = int(getattr(u, "prompt_tokens", 0) or 0)
        completion = int(getattr(u, "completion_tokens", 0) or 0)
        cached = 0
        details = getattr(u, "prompt_tokens_details", None)
        if details:
            cached = int(getattr(details, "cached_tokens", 0) or 0)
        return Usage(input_tokens=prompt, output_tokens=completion, cached_tokens=cached)
    except (TypeError, ValueError):
        return None


class GroqProvider(BaseProvider):
    def __init__(self, api_key, model):
        from groq import Groq
        if not api_key:
            raise RuntimeError("Unable to connect to Groq\n\nCheck your API key and try again.")
        self.client = Groq(api_key=api_key)
        self.model = model
        self.provider_name = "Groq"

    def chat(self, messages, tools):
        try:
            resp = call_with_backoff(
                self.provider_name,
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=10000,
                ),
            )
        except RuntimeError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "auth" in msg or "api_key" in msg or "unauthorized" in msg:
                raise RuntimeError("Unable to connect to Groq\n\nCheck your API key and try again.") from e
            if "model" in msg and ("not found" in msg or "invalid" in msg):
                raise RuntimeError(f"Invalid model: {self.model}") from e
            raise RuntimeError(f"Unable to connect to Groq: {e}") from e
        choice = resp.choices[0].message
        tool_calls = []
        if getattr(choice, "tool_calls", None):
            for tc in choice.tool_calls:
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}"))
        content = getattr(choice, "content", None)
        return ChatResponse(content=content, tool_calls=tool_calls, usage=_extract_usage(resp))
