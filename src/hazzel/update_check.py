"""Best-effort PyPI update notice for the interactive REPL.

One small module, stdlib only: check ``https://pypi.org/pypi/hazzel/json``
with a ~1s timeout, cache the result for 24h under ``~/.config/hazzel/`` so
it fires at most once a day, and stay silent on any network error. Never
called from ``hazzel -p`` (stdout must stay clean for scripts).
"""

import json
import re
import time
import urllib.request

PYPI_URL = "https://pypi.org/pypi/hazzel/json"
CACHE_FILENAME = "update_check.json"
CACHE_TTL_SECONDS = 24 * 3600
REQUEST_TIMEOUT = 1.0
MAX_RESPONSE_BYTES = 65536


def _local_version():
    try:
        from hazzel import __version__ as ver
    except Exception:
        return "0.0.0"
    return ver if isinstance(ver, str) and ver else "0.0.0"


def _version_key(version):
    """Numeric tuple for comparison so 1.5.10 > 1.5.9 (not lexicographic)."""
    try:
        return tuple(int(n) for n in re.findall(r"\d+", str(version)))
    except (TypeError, ValueError):
        return ()


def is_newer(latest, local):
    if not isinstance(latest, str) or not isinstance(local, str):
        return False
    if not latest.strip() or not local.strip():
        return False
    if latest.strip() == local.strip():
        return False
    return _version_key(latest) > _version_key(local)


def _cache_path():
    from hazzel import config

    return config.CONFIG_DIR / CACHE_FILENAME


def _read_cache():
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    checked_at = data.get("checked_at")
    latest = data.get("latest")
    if not isinstance(checked_at, (int, float)):
        checked_at = None
    if not isinstance(latest, str) or not latest.strip():
        latest = None
    return checked_at, latest


def _write_cache(checked_at, latest):
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"checked_at": checked_at, "latest": latest}),
            encoding="utf-8",
        )
    except OSError:
        pass


def _fetch_latest(timeout=REQUEST_TIMEOUT):
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES)
    except Exception:
        return None
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(data, dict):
        return None
    info = data.get("info")
    if not isinstance(info, dict):
        return None
    version = info.get("version")
    if not isinstance(version, str) or not version.strip():
        return None
    return version.strip()


def check_for_update(now=None, timeout=REQUEST_TIMEOUT, cache_ttl=CACHE_TTL_SECONDS):
    """Return the newer PyPI version string, or None. Never raises."""
    try:
        local = _local_version()
        current = now if isinstance(now, (int, float)) else time.time()
        checked_at, cached = _read_cache()
        if checked_at is not None and current - checked_at < cache_ttl:
            if cached and is_newer(cached, local):
                return cached
            return None
        latest = _fetch_latest(timeout=timeout)
        if latest is None:
            # Throttle retries: remember the check so an offline box does
            # not pay the ~1s timeout on every startup.
            _write_cache(current, cached)
            if cached and is_newer(cached, local):
                return cached
            return None
        _write_cache(current, latest)
        if is_newer(latest, local):
            return latest
        return None
    except Exception:
        return None


def format_notice(latest, local=None):
    current = local if isinstance(local, str) and local else _local_version()
    return f"hazzel {latest} available (you have {current}) — pip install -U hazzel"
