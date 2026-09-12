import json
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path.cwd()

CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hazzel"
CONFIG_FILE = CONFIG_DIR / "config.json"
LEGACY_FILE = Path.home() / ".hazzel" / "config.json"
STAR_NUDGE_FILE = CONFIG_DIR / ".star_nudged"


def should_show_star_nudge():
    try:
        return not STAR_NUDGE_FILE.exists()
    except OSError:
        return False


def mark_star_nudged():
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        STAR_NUDGE_FILE.touch(exist_ok=True)
    except OSError:
        pass


DEFAULT_CONTEXT_WINDOW = 131072
OLLAMA_CONTEXT_WINDOW = 32768

MODEL_CATALOG = [
    {"display_name": "GPT OSS 120B", "id": "openai/gpt-oss-120b", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "Llama 3.1 8B Instant", "id": "llama-3.1-8b-instant", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "Llama 3.3 70B Versatile", "id": "llama-3.3-70b-versatile", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "GPT OSS 20B", "id": "openai/gpt-oss-20b", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "GPT OSS Safeguard 20B", "id": "openai/gpt-oss-safeguard-20b", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "Qwen3.6 27B", "id": "qwen/qwen3.6-27b", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "Qwen3.8 27B", "id": "qwen/qwen3.8-27b", "provider": "groq", "provider_display": "Groq", "context": 131072},
    {"display_name": "GPT-6 Astra", "id": "gpt-6-astra", "provider": "openai", "provider_display": "OpenAI", "context": 400000},
    {"display_name": "GPT-5.6 Sol", "id": "gpt-5.6-sol", "provider": "openai", "provider_display": "OpenAI", "context": 400000},
    {"display_name": "GPT-5.6 Terra", "id": "gpt-5.6-terra", "provider": "openai", "provider_display": "OpenAI", "context": 400000},
    {"display_name": "GPT-5.6 Luna", "id": "gpt-5.6-luna", "provider": "openai", "provider_display": "OpenAI", "context": 400000},
    {"display_name": "GPT-5.6 Cyber", "id": "gpt-5.6-cyber", "provider": "openai", "provider_display": "OpenAI", "context": 400000},
    {"display_name": "Claude Fable 5", "id": "claude-fable-5", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Haiku 4.5", "id": "claude-haiku-4-5", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Haiku 4.5 20251001", "id": "claude-haiku-4-5-20251001", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 4.5", "id": "claude-opus-4-5", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 4.5 20251101", "id": "claude-opus-4-5-20251101", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 4.6", "id": "claude-opus-4-6", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 4.7", "id": "claude-opus-4-7", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 4.8", "id": "claude-opus-4-8", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Opus 5", "id": "claude-opus-5", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Claude Sonnet 4.5", "id": "claude-sonnet-4-5", "provider": "anthropic", "provider_display": "Anthropic", "context": 200000},
    {"display_name": "Mistral Medium 3.5", "id": "mistral-medium-3.5", "provider": "mistral", "provider_display": "Mistral", "context": 131072},
    {"display_name": "Mistral Small 4", "id": "mistral-small-4", "provider": "mistral", "provider_display": "Mistral", "context": 131072},
    {"display_name": "Mistral Large 3", "id": "mistral-large-3", "provider": "mistral", "provider_display": "Mistral", "context": 131072},
    {"display_name": "Codestral", "id": "codestral", "provider": "mistral", "provider_display": "Mistral", "context": 262144},
    {"display_name": "Codestral Embed", "id": "codestral-embed", "provider": "mistral", "provider_display": "Mistral", "context": 32768},
    {"display_name": "Gemini 3.8 Flash", "id": "gemini-3.8-flash", "provider": "gemini", "provider_display": "Gemini", "context": 1048576},
    {"display_name": "Gemini 3.7 Flash", "id": "gemini-3.7-flash", "provider": "gemini", "provider_display": "Gemini", "context": 1048576},
    {"display_name": "Gemini 3.1 Pro", "id": "gemini-3.1-pro-preview", "provider": "gemini", "provider_display": "Gemini", "context": 1048576},
    {"display_name": "Gemini 2.5 Pro", "id": "gemini-2.5-pro", "provider": "gemini", "provider_display": "Gemini", "context": 1048576},
    {"display_name": "DeepSeek V4 Flash", "id": "deepseek-v4-flash", "provider": "deepseek", "provider_display": "DeepSeek", "context": 131072},
    {"display_name": "DeepSeek V4 Pro", "id": "deepseek-v4-pro", "provider": "deepseek", "provider_display": "DeepSeek", "context": 131072},
    {"display_name": "GPT-6 Astra", "id": "openai/gpt-6-astra", "provider": "openrouter", "provider_display": "OpenRouter", "context": 400000},
    {"display_name": "Gemini 3.8 Flash", "id": "google/gemini-3.8-flash", "provider": "openrouter", "provider_display": "OpenRouter", "context": 1048576},
]


def get_context_window():
    try:
        size = get_current_entry().get("context")
        if isinstance(size, int) and size > 0:
            return size
    except Exception:
        pass
    try:
        if get_current_provider() == "ollama":
            return OLLAMA_CONTEXT_WINDOW
    except Exception:
        pass
    return DEFAULT_CONTEXT_WINDOW

PROVIDER_ENV = {
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "ollama": None,
}

PROVIDER_DISPLAY = {
    "mistral": "Mistral",
    "openai": "OpenAI",
    "groq": "Groq",
    "anthropic": "Anthropic",
    "gemini": "Gemini",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "ollama": "Ollama",
}

KEYLESS_PROVIDERS = frozenset({"ollama"})

_model = "openai/gpt-oss-120b"
_provider = "groq"
_display_name = "GPT OSS 120B"
_api_keys: dict[str, str] = {}
_prove_enabled = False
_plan_enabled = False
_goal = None

MODEL = _model


def get_api_key(provider=None):
    if provider is None:
        provider = _provider
    if provider in KEYLESS_PROVIDERS:
        return "ollama"
    env = PROVIDER_ENV.get(provider)
    if env:
        val = os.getenv(env)
        if val and val.strip():
            return val.strip()
    if provider in _api_keys and _api_keys[provider]:
        return _api_keys[provider]
    return None


def _get_config_file():
    if CONFIG_FILE.exists():
        return CONFIG_FILE
    if LEGACY_FILE.exists():
        return LEGACY_FILE
    return CONFIG_FILE


def _load_config():
    global _model, _provider, _display_name, MODEL, _prove_enabled, _plan_enabled, _goal
    path = _get_config_file()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return
    keys = data.get("keys")
    if isinstance(keys, dict):
        for k, v in keys.items():
            if k in PROVIDER_ENV and isinstance(v, str) and v.strip():
                _api_keys[k] = v.strip()
    provider = data.get("provider")
    model = data.get("model")
    if isinstance(provider, str) and isinstance(model, str) and provider in PROVIDER_ENV:
        valid = provider in KEYLESS_PROVIDERS or any(m["id"] == model and m["provider"] == provider for m in MODEL_CATALOG)
        if not valid:
            _provider = "groq"
            _model = "openai/gpt-oss-120b"
            MODEL = _model
            _display_name = "GPT OSS 120B"
            try:
                _save_config()
            except OSError:
                pass
            return
        _provider = provider
        _model = model
        MODEL = _model
        dn = data.get("display_name")
        if isinstance(dn, str) and dn.strip():
            _display_name = dn.strip()
        else:
            for m in MODEL_CATALOG:
                if m["id"] == model and m["provider"] == provider:
                    _display_name = m["display_name"]
                    break
            else:
                _display_name = model
    if isinstance(data.get("prove_enabled"), bool):
        _prove_enabled = data["prove_enabled"]
    if isinstance(data.get("plan_enabled"), bool):
        _plan_enabled = data["plan_enabled"]
    goal = data.get("goal")
    if isinstance(goal, dict) and isinstance(goal.get("objective"), str) and goal["objective"].strip():
        _goal = {"objective": goal["objective"].strip()[:500], "criteria": goal.get("criteria", "") if isinstance(goal.get("criteria"), str) else ""}
        _goal["criteria"] = _goal["criteria"].strip()[:500]
    elif goal is None:
        _goal = None


def _save_config():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_FILE.parent, 0o700)
    except OSError:
        pass
    data = {"keys": dict(_api_keys), "provider": _provider, "model": _model, "display_name": _display_name, "prove_enabled": _prove_enabled, "plan_enabled": _plan_enabled, "goal": _goal}
    tmp = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_FILE.parent))
        os.close(fd)
        tmp = Path(tmp_path)
        tmp.write_text(json.dumps(data, indent=2) + "\n")
        os.chmod(tmp, 0o600)
        tmp.replace(CONFIG_FILE)
        try:
            os.chmod(CONFIG_FILE, 0o600)
        except OSError:
            pass
    except OSError:
        if tmp is not None and tmp.exists() and tmp != CONFIG_FILE:
            try:
                tmp.unlink()
            except OSError:
                pass
        raise
    else:
        if tmp is not None and tmp.exists() and tmp != CONFIG_FILE:
            try:
                tmp.unlink()
            except OSError:
                pass


def set_api_key(provider, key):
    _api_keys[provider] = key
    env = PROVIDER_ENV.get(provider)
    if env:
        os.environ[env] = key
    try:
        _save_config()
    except OSError:
        pass


def clear_api_keys():
    _api_keys.clear()
    for env in PROVIDER_ENV.values():
        if env in os.environ:
            try:
                del os.environ[env]
            except OSError:
                pass
    try:
        _save_config()
    except OSError:
        pass


def has_any_key():
    for p in PROVIDER_ENV:
        if get_api_key(p):
            return True
    return False


def get_current_model():
    return _model


def get_current_provider():
    return _provider


def get_current_display_name():
    return _display_name


def get_current_entry():
    for m in MODEL_CATALOG:
        if m["id"] == _model and m["provider"] == _provider:
            return m
    return {"display_name": _display_name, "id": _model, "provider": _provider, "provider_display": PROVIDER_DISPLAY.get(_provider, _provider)}


def set_model(provider, model_id, display_name=None):
    global _model, _provider, _display_name, MODEL
    _provider = provider
    _model = model_id
    if display_name:
        _display_name = display_name
    else:
        for m in MODEL_CATALOG:
            if m["id"] == model_id and m["provider"] == provider:
                _display_name = m["display_name"]
                break
        else:
            _display_name = model_id
    MODEL = _model
    try:
        _save_config()
    except OSError:
        pass


def is_prove_enabled():
    return _prove_enabled


def set_prove_enabled(enabled):
    global _prove_enabled
    _prove_enabled = bool(enabled)
    try:
        _save_config()
    except OSError:
        pass


def is_plan_enabled():
    return _plan_enabled


def set_plan_enabled(enabled):
    global _plan_enabled
    _plan_enabled = bool(enabled)
    try:
        _save_config()
    except OSError:
        pass


def get_goal():
    if isinstance(_goal, dict) and isinstance(_goal.get("objective"), str) and _goal["objective"].strip():
        return {"objective": _goal["objective"], "criteria": _goal.get("criteria", "") or ""}
    return None


def set_goal(objective, criteria=""):
    global _goal
    objective = (objective or "").strip()
    if not objective:
        _goal = None
    else:
        _goal = {"objective": objective[:500], "criteria": (criteria or "").strip()[:500]}
    try:
        _save_config()
    except OSError:
        pass


def clear_goal():
    set_goal("")


def get_catalog():
    try:
        from .providers.ollama import fetch_local_models
        known = {m["id"] for m in MODEL_CATALOG}
        extra = [
            {"display_name": f"{name} (local)", "id": name, "provider": "ollama", "provider_display": "Ollama"}
            for name in fetch_local_models()
            if name not in known
        ]
        if extra:
            return MODEL_CATALOG + extra
    except Exception:
        pass
    return MODEL_CATALOG


def resolve_project_path(path):
    original = path
    path = PROJECT_ROOT / path
    try:
        path = path.resolve()
        path.relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        raise ValueError(f"Path is outside the project root: {original}. Use a relative path inside {PROJECT_ROOT.name}.")
    return path


def _load_dotenv():
    path = PROJECT_ROOT / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    allowed = set(PROVIDER_ENV.values())
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key not in allowed or os.getenv(key):
            continue
        value = value.strip().strip("'\"").strip()
        if value:
            os.environ[key] = value


def mask_key(key):
    if not key or len(key) <= 8:
        return "••••"
    return "•" * 8 + key[-4:]


try:
    _load_dotenv()
except OSError:
    pass

try:
    _load_config()
except (OSError, json.JSONDecodeError):
    pass
