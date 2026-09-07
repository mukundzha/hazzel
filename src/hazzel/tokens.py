import json


def estimate_text(text):
    text = text or ""
    if not isinstance(text, str):
        text = str(text)
    return max(1, len(text) // 4)


def estimate_messages(messages, tools=None):
    total = 0
    for m in messages or []:
        total += estimate_text(m.get("content"))
        for tc in m.get("tool_calls") or []:
            fn = tc.get("function", {})
            total += estimate_text(fn.get("name"))
            total += estimate_text(fn.get("arguments"))
    if tools:
        try:
            total += estimate_text(json.dumps(tools))
        except (TypeError, ValueError):
            total += len(tools) * 100
    return total


def format_count(n):
    n = int(n or 0)
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)
