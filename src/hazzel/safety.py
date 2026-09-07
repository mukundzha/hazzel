import difflib
from pathlib import Path

# (resolved path, prior content). None means the file did not exist.
_events: list[tuple[str, bytes | None]] = []

MAX_EVENTS = 200
MAX_DEPTH_PER_FILE = 20
MAX_DIFF_LINES = 80


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
