from .base import BaseProvider, ChatResponse, ToolCall, Usage, call_with_backoff, extract_reasoning


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


class OpenAIProvider(BaseProvider):
    def __init__(self, api_key, model):
        from openai import OpenAI
        if not api_key:
            raise RuntimeError("Unable to connect to OpenAI\n\nCheck your API key and try again.")
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def chat(self, messages, tools):
        try:
            resp = call_with_backoff(
                "OpenAI",
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=10000,
                    prompt_cache_key="hazzel-v1",
                ),
            )
        except RuntimeError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "auth" in msg or "api_key" in msg or "unauthorized" in msg:
                raise RuntimeError("Unable to connect to OpenAI\n\nCheck your API key and try again.") from e
            if "model" in msg and ("not found" in msg or "invalid" in msg):
                raise RuntimeError(f"Invalid model: {self.model}") from e
            raise RuntimeError(f"Unable to connect to OpenAI: {e}") from e
        choice = resp.choices[0].message
        tool_calls = []
        if getattr(choice, "tool_calls", None):
            for tc in choice.tool_calls:
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}"))
        content = getattr(choice, "content", None)
        return ChatResponse(content=content, tool_calls=tool_calls, usage=_extract_usage(resp), reasoning=extract_reasoning(choice))

    def stream(self, messages, tools, on_token=None):
        try:
            chunks = call_with_backoff(
                "OpenAI",
                lambda: self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    max_tokens=10000,
                    prompt_cache_key="hazzel-v1",
                    stream=True,
                ),
            )
        except Exception:
            return super().stream(messages, tools, on_token)
        parts = []
        think = []
        acc = {}
        usage = None
        try:
            for chunk in chunks:
                try:
                    u = _extract_usage(chunk)
                    if u and (u.input_tokens or u.output_tokens):
                        usage = u
                except Exception:
                    pass
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue
                reason = extract_reasoning(delta)
                if reason:
                    think.append(reason)
                text = getattr(delta, "content", None)
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
                        if getattr(fn, "arguments", None):
                            entry["args"] += fn.arguments
        except Exception as error:
            if not parts and not acc:
                raise
            msg = str(error).lower()
            if "401" in msg or "auth" in msg or "unauthorized" in msg:
                raise RuntimeError("Unable to connect to OpenAI\n\nCheck your API key and try again.") from error
        tool_calls = []
        for idx in sorted(acc):
            entry = acc[idx]
            if entry["name"]:
                tool_calls.append(ToolCall(id=entry["id"] or f"call_{idx}", name=entry["name"], arguments=entry["args"] or "{}"))
        thinking = "".join(think).strip() or None
        return ChatResponse(content="".join(parts) or None, tool_calls=tool_calls, usage=usage, reasoning=thinking)
