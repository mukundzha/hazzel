import json
import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path.cwd()

CONFIG_DIR = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "hazzel"
CONFIG_FILE = CONFIG_DIR / "config.json"
LEGACY_FILE = Path.home() / ".hazzel" / "config.json"

MODEL_CATALOG = [
    {"display_name": "GPT-6 Astra", "id": "gpt-6-astra", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-5.6 Sol", "id": "gpt-5.6-sol", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-5.6 Terra", "id": "gpt-5.6-terra", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-5.6 Luna", "id": "gpt-5.6-luna", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-5", "id": "gpt-5", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-5 Mini", "id": "gpt-5-mini", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-4.1", "id": "gpt-4.1", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "GPT-4o", "id": "gpt-4o", "provider": "openai", "provider_display": "OpenAI"},
    {"display_name": "Claude Fable 5.1", "id": "claude-fable-5.1", "provider": "anthropic", "provider_display": "Anthropic"},
    {"display_name": "Claude Opus 5", "id": "claude-opus-5", "provider": "anthropic", "provider_display": "Anthropic"},
    {"display_name": "Claude Sonnet 5", "id": "claude-sonnet-5", "provider": "anthropic", "provider_display": "Anthropic"},
    {"display_name": "Claude Haiku 4.5", "id": "claude-haiku-4-5-20251001", "provider": "anthropic", "provider_display": "Anthropic"},
    {"display_name": "Mistral Medium 3.5", "id": "mistral-medium-latest", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Mistral Small 4", "id": "mistral-small-latest", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Mistral Large 3", "id": "mistral-large-latest", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Ministral 3 14B", "id": "ministral-3-14b", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Ministral 3 8B", "id": "ministral-3-8b", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Ministral 3 3B", "id": "ministral-3-3b", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Codestral", "id": "codestral-latest", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Z.ai GLM 5.2", "id": "zai-glm-5.2", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "Leanstral 1.5", "id": "leanstral-1.5", "provider": "mistral", "provider_display": "Mistral"},
    {"display_name": "GPT OSS 120B", "id": "openai/gpt-oss-120b", "provider": "groq", "provider_display": "Groq"},
    {"display_name": "GPT OSS 20B", "id": "openai/gpt-oss-20b", "provider": "groq", "provider_display": "Groq"},
]

PROVIDER_ENV = {
    "mistral": "MISTRAL_API_KEY",
    "openai": "OPENAI_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

PROVIDER_DISPLAY = {
    "mistral": "Mistral",
    "openai": "OpenAI",
    "groq": "Groq",
    "anthropic": "Anthropic",
}

_model = "openai/gpt-oss-120b"
_provider = "groq"
_display_name = "GPT OSS 120B"
_api_keys: dict[str, str] = {}
_prove_enabled = False
_plan_enabled = False

MODEL = _model


def get_api_key(provider=None):
    if provider is None:
        provider = _provider
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
    global _model, _provider, _display_name, MODEL, _prove_enabled, _plan_enabled
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
        valid = any(m["id"] == model and m["provider"] == provider for m in MODEL_CATALOG)
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


def _save_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CONFIG_DIR, 0o700)
    except OSError:
        pass
    data = {"keys": dict(_api_keys), "provider": _provider, "model": _model, "display_name": _display_name, "prove_enabled": _prove_enabled, "plan_enabled": _plan_enabled}
    tmp = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=str(CONFIG_DIR))
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


def get_catalog():
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
