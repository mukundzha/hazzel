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

    def stream(self, messages, tools, on_token=None):
        try:
            chunks = call_with_backoff(
                "Mistral",
                lambda: self.client.chat.stream(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=10000,
                ),
            )
        except Exception:
            return super().stream(messages, tools, on_token)
        parts = []
        acc = {}
        usage = None
        try:
            for event in chunks:
                data = getattr(event, "data", event)
                try:
                    u = _extract_usage(data)
                    if u and (u.input_tokens or u.output_tokens):
                        usage = u
                except Exception:
                    pass
                choices = getattr(data, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue
                text = getattr(delta, "content", None)
                if isinstance(text, list):
                    text = "".join(
                        p.get("text", "") if isinstance(p, dict) else getattr(p, "text", str(p)) for p in text
                    )
                if text:
                    parts.append(text)
                    if on_token:
                        try:
                            on_token(text)
                        except Exception:
                            pass
                for tc in getattr(delta, "tool_calls", None) or []:
                    idx = getattr(tc, "index", 0) or 0
                    entry = acc.setdefault(idx, {"id": "", "name": "", "args": ""})
                    if getattr(tc, "id", None):
                        entry["id"] = tc.id
                    fn = getattr(tc, "function", None)
                    if fn is not None:
                        if getattr(fn, "name", None):
                            entry["name"] = fn.name
                        args = getattr(fn, "arguments", None)
                        if isinstance(args, dict):
                            entry["args"] += json.dumps(args)
                        elif args:
                            entry["args"] += args
        except Exception as error:
            if not parts and not acc:
                raise
            msg = str(error).lower()
            if "401" in msg or "auth" in msg or "unauthorized" in msg:
                raise RuntimeError("Unable to connect to Mistral\n\nCheck your API key and try again.") from error
        tool_calls = []
        for idx in sorted(acc):
            entry = acc[idx]
            if entry["name"]:
                tool_calls.append(ToolCall(id=entry["id"] or f"call_{idx}", name=entry["name"], arguments=entry["args"] or "{}"))
        return ChatResponse(content="".join(parts) or None, tool_calls=tool_calls, usage=usage)
