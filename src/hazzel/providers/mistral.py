import json
from .base import BaseProvider, ChatResponse, ToolCall, Usage, call_with_backoff


def _extract_usage(resp):
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return None
        if isinstance(u, dict):
            prompt = int(u.get("prompt_tokens", 0) or 0)
            completion = int(u.get("completion_tokens", 0) or 0)
        else:
            prompt = int(getattr(u, "prompt_tokens", 0) or 0)
            completion = int(getattr(u, "completion_tokens", 0) or 0)
        return Usage(input_tokens=prompt, output_tokens=completion)
    except (TypeError, ValueError):
        return None


class MistralProvider(BaseProvider):
    def __init__(self, api_key, model):
        from mistralai.client import Mistral
        if not api_key:
            raise RuntimeError("Unable to connect to Mistral\n\nCheck your API key and try again.")
        self.client = Mistral(api_key=api_key)
        self.model = model

    def chat(self, messages, tools):
        try:
            resp = call_with_backoff(
                "Mistral",
                lambda: self.client.chat.complete(
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
                raise RuntimeError("Unable to connect to Mistral\n\nCheck your API key and try again.") from e
            if "model" in msg and ("not found" in msg or "invalid" in msg):
                raise RuntimeError(f"Invalid model: {self.model}") from e
            raise RuntimeError(f"Unable to connect to Mistral: {e}") from e
        choice = resp.choices[0].message
        tool_calls = []
        if getattr(choice, "tool_calls", None):
            for tc in choice.tool_calls:
                args = tc.function.arguments
                if isinstance(args, dict):
                    args = json.dumps(args)
                elif args is None:
                    args = "{}"
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        content = getattr(choice, "content", None)
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
                elif hasattr(part, "text"):
                    text_parts.append(part.text)
                else:
                    text_parts.append(str(part))
            content = "".join(text_parts) if text_parts else None
        return ChatResponse(content=content, tool_calls=tool_calls, usage=_extract_usage(resp))
