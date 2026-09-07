import json
from .base import BaseProvider, ChatResponse, ToolCall, Usage, call_with_backoff


def _extract_usage(resp):
    try:
        u = getattr(resp, "usage", None)
        if not u:
            return None
        prompt = int(getattr(u, "input_tokens", 0) or 0)
        completion = int(getattr(u, "output_tokens", 0) or 0)
        cached = int(getattr(u, "cache_read_input_tokens", 0) or 0)
        created = int(getattr(u, "cache_creation_input_tokens", 0) or 0)
        return Usage(input_tokens=prompt, output_tokens=completion, cached_tokens=cached + created)
    except (TypeError, ValueError):
        return None


def _openai_tools_to_anthropic(tools):
    anth = []
    for t in tools or []:
        fn = t.get("function", {})
        anth.append({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            "cache_control": {"type": "ephemeral"},
        })
    return anth


def _messages_to_anthropic(messages):
    system = ""
    anth_msgs = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            c = m.get("content") or ""
            if isinstance(c, list):
                c = " ".join([x.get("text", "") if isinstance(x, dict) else str(x) for x in c])
            system = f"{system}\n{c}" if system else c
            continue
        if role == "user":
            content = m.get("content") or ""
            if isinstance(content, list):
                content = "\n".join(str(x) for x in content)
            anth_msgs.append({"role": "user", "content": [{"type": "text", "text": str(content)}]})
        elif role == "assistant":
            blocks = []
            c = m.get("content")
            if c:
                if isinstance(c, list):
                    c = "\n".join(str(x) for x in c)
                blocks.append({"type": "text", "text": str(c)})
            for tc in m.get("tool_calls") or []:
                fn = tc.get("function", {})
                raw_args = fn.get("arguments", "{}")
                try:
                    parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}
                blocks.append({"type": "tool_use", "id": tc.get("id"), "name": fn.get("name"), "input": parsed})
            if not blocks:
                blocks.append({"type": "text", "text": ""})
            anth_msgs.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            content = m.get("content") or ""
            tool_id = m.get("tool_call_id") or ""
            anth_msgs.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_id, "content": str(content)}]})
    return system, anth_msgs


class AnthropicProvider(BaseProvider):
    def __init__(self, api_key, model):
        import anthropic
        if not api_key:
            raise RuntimeError("Unable to connect to Anthropic\n\nCheck your API key and try again.")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def chat(self, messages, tools):
        system, anth_messages = _messages_to_anthropic(messages)
        anth_tools = _openai_tools_to_anthropic(tools)
        kwargs = {
            "model": self.model,
            "messages": anth_messages,
            "max_tokens": 10000,
        }
        if system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if anth_tools:
            kwargs["tools"] = anth_tools
        try:
            resp = call_with_backoff("Anthropic", lambda: self.client.messages.create(**kwargs))
        except RuntimeError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "401" in msg or "auth" in msg or "api_key" in msg or "unauthorized" in msg:
                raise RuntimeError("Unable to connect to Anthropic\n\nCheck your API key and try again.") from e
            if "model" in msg and ("not found" in msg or "invalid" in msg):
                raise RuntimeError(f"Invalid model: {self.model}") from e
            raise RuntimeError(f"Unable to connect to Anthropic: {e}") from e
        content_text = ""
        tool_calls = []
        for block in getattr(resp, "content", []) or []:
            btype = getattr(block, "type", None)
            if btype == "text":
                content_text += getattr(block, "text", "") or ""
            elif btype == "tool_use":
                args = getattr(block, "input", {}) or {}
                args_json = json.dumps(args)
                tool_calls.append(ToolCall(id=getattr(block, "id", ""), name=getattr(block, "name", ""), arguments=args_json))
        return ChatResponse(content=content_text if content_text else None, tool_calls=tool_calls, usage=_extract_usage(resp))
