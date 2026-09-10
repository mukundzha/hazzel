import json
import urllib.request


def _tags_url():
    import os
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434/v1").rstrip("/")
    if host.endswith("/v1"):
        host = host[: -len("/v1")]
    return host + "/api/tags"


def fetch_local_models(timeout=2):
    try:
        with urllib.request.urlopen(_tags_url(), timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8") or "{}")
    except Exception:
        return []
    names = []
    for m in data.get("models", None) or []:
        name = m.get("name") if isinstance(m, dict) else None
        if name and name not in names:
            names.append(name)
    return names
