import difflib
import json
from pathlib import Path

# (resolved path, prior content). None means the file did not exist.
_events: list[tuple[str, bytes | None]] = []

MAX_EVENTS = 200
MAX_DEPTH_PER_FILE = 20
MAX_DIFF_LINES = 80
MAX_PERSIST_BYTES = 2_000_000


def _undo_dir():
    from . import config as _cfg

    return Path(_cfg.CONFIG_DIR) / "undo"


def _index_path():
    return _undo_dir() / "index.json"


def _backups_dir():
    return _undo_dir() / "backups"


def _persist_save():
    try:
        undo_dir = _undo_dir()
        backups = _backups_dir()
        undo_dir.mkdir(parents=True, exist_ok=True)
        backups.mkdir(parents=True, exist_ok=True)
        try:
            undo_dir.chmod(0o700)
        except OSError:
            pass
        items = []
        for i, (key, prior) in enumerate(_events):
            if prior is None:
                items.append({"path": key, "backup": None})
                continue
            if len(prior) > MAX_PERSIST_BYTES:
                items.append({"path": key, "backup": None, "too_large": True})
                continue
            name = f"{i:04d}-{abs(hash(key)) % 10_000_000:07d}.bak"
            try:
                dest = backups / name
                dest.write_bytes(prior)
                try:
                    dest.chmod(0o600)
                except OSError:
                    pass
                items.append({"path": key, "backup": name})
            except OSError:
                items.append({"path": key, "backup": None})
        try:
            tmp = _index_path().with_suffix(".tmp")
            tmp.write_text(json.dumps({"v": 1, "items": items}), encoding="utf-8")
            tmp.replace(_index_path())
        except OSError:
            pass
        try:
            valid = {it.get("backup") for it in items if it.get("backup")}
            for blob in backups.glob("*.bak"):
                if blob.name not in valid:
                    try:
                        blob.unlink()
                    except OSError:
                        pass
        except OSError:
            pass
    except Exception:
        pass


def _persist_load():
    global _events
    try:
        index = _index_path()
        if not index.exists():
            return
        data = json.loads(index.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return
        backups = _backups_dir()
        loaded: list[tuple[str, bytes | None]] = []
        for it in items[-MAX_EVENTS:]:
            if not isinstance(it, dict) or not it.get("path"):
                continue
            name = it.get("backup")
            if not name:
                loaded.append((it["path"], None))
                continue
            try:
                blob = backups / str(name)
                if not blob.exists() or blob.stat().st_size > MAX_PERSIST_BYTES:
                    loaded.append((it["path"], None))
                    continue
                loaded.append((it["path"], blob.read_bytes()))
            except OSError:
                loaded.append((it["path"], None))
        if loaded:
            _events = loaded
    except Exception:
        pass


def clear_undo_log():
    global _events
    _events = []
    try:
        index = _index_path()
        if index.exists():
            index.unlink()
        backups = _backups_dir()
        if backups.exists():
            for blob in backups.glob("*.bak"):
                try:
                    blob.unlink()
                except OSError:
                    pass
    except OSError:
        pass


def checkpoint(path):
    path = Path(path)
    key = str(path)
    try:
        prior = path.read_bytes() if path.exists() and path.is_file() else None
    except OSError:
        return
    _events.append((key, prior))
    while len([1 for k, _ in _events if k == key]) > MAX_DEPTH_PER_FILE:
        for i, (k, _) in enumerate(_events):
            if k == key:
                del _events[i]
                break
    del _events[: max(0, len(_events) - MAX_EVENTS)]
    _persist_save()


def undo(count=1):
    restored = []
    for _ in range(max(1, count)):
        if not _events:
            break
        key, prior = _events.pop()
        path = Path(key)
        try:
            if prior is None:
                if not path.exists():
                    continue
                if path.is_dir():
                    continue
                path.unlink()
                restored.append((key, "removed"))
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(prior)
                restored.append((key, "restored"))
        except OSError:
            continue
    if restored:
        _persist_save()
    return restored


def pending_count():
    return len(_events)


def diff_text(display_path, original, updated):
    def _lines(data):
        if data is None:
            return []
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return str(data).splitlines()

    diff = difflib.unified_diff(
        _lines(original),
        _lines(updated),
        fromfile=f"a/{display_path}",
        tofile=f"b/{display_path}",
        lineterm="",
    )
    lines = list(diff)
    if not lines:
        return "(no changes)"
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + ["[…diff truncated…]"]
    return "\n".join(lines)


try:
    _persist_load()
except Exception:
    pass
