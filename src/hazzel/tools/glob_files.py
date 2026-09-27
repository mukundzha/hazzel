import os
import re

from .. import tool_cache
from ..config import PROJECT_ROOT, resolve_project_path
from .search_files import SKIP_DIRS

MAX_MATCHES = 100

# Hard ceiling on visited paths so a huge tree can't stall a turn.
MAX_SCAN = 200_000

_usage_message = "Glob pattern is required — usage: glob(pattern, path='.')."


def glob_files(pattern, path="."):
    if not str(pattern or "").strip():
        return _usage_message
    pattern = str(pattern).strip()
    if pattern.startswith("./"):
        pattern = pattern[2:]
    # A trailing slash narrows the match to directories.
    dirs_only = pattern.endswith("/")
    if dirs_only:
        pattern = pattern.rstrip("/")
    if not pattern:
        return _usage_message

    try:
        root = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if not root.exists():
        return f"Path does not exist: {path}. Check the spelling or glob from '.'."

    if not root.is_dir():
        return f"Path is not a directory: {path}. Glob from its parent instead."

    key = (pattern, str(root), dirs_only)
    if tool_cache.caching_enabled():
        hit = tool_cache.GLOB.get(key)
        if hit is not None:
            return list(hit)

    matchers = [_translate(part) for part in _expand_braces(pattern)]
    matches = []
    scanned = 0
    hit_cap = False
    scan_capped = False
    for relative, is_dir in _iter_entries(root):
        scanned += 1
        if scanned > MAX_SCAN:
            scan_capped = True
            break
        if dirs_only and not is_dir:
            continue
        if not any(matcher.match(relative) for matcher in matchers):
            continue
        if len(matches) >= MAX_MATCHES:
            hit_cap = True
            break
        matches.append(relative + "/" if is_dir else relative)

    if not matches:
        return _no_match(pattern, path)

    matches.sort()
    rows = list(matches)
    if scan_capped:
        rows.append(f"[stopped after {MAX_SCAN} paths; narrow the path or pattern]")
    elif hit_cap:
        rows.append(f"[more than {MAX_MATCHES} matches; narrow the pattern or path]")
    if tool_cache.caching_enabled():
        tool_cache.GLOB.set(key, rows)
    return rows


def _no_match(pattern, path):
    if "/" not in pattern:
        return (f"No matches for '{pattern}' in '{path}'. Patterns match from the search root — "
                f"retry with '**/{pattern}' to search recursively, or widen the path.")
    return f"No matches for '{pattern}' in '{path}'. Loosen the pattern or widen the path."


def _iter_entries(root):
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place so os.walk never descends into skipped directories.
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        dirnames.sort()
        for name in dirnames:
            yield _relative(os.path.join(dirpath, name)), True
        for name in sorted(filenames):
            yield _relative(os.path.join(dirpath, name)), False


def _relative(full):
    try:
        relative = os.path.relpath(full, str(PROJECT_ROOT))
    except ValueError:
        relative = full
    return relative.replace(os.sep, "/")


def _expand_braces(pattern):
    """Turn '*.{py,pyi}' into ['*.py', '*.pyi'] so brace groups work like a shell."""
    start = pattern.find("{")
    if start == -1:
        return [pattern]
    depth = 0
    end = -1
    for index in range(start, len(pattern)):
        if pattern[index] == "{":
            depth += 1
        elif pattern[index] == "}":
            depth -= 1
            if depth == 0:
                end = index
                break
    if end == -1:
        return [pattern]
    head, body, tail = pattern[:start], pattern[start + 1:end], pattern[end + 1:]
    return [head + choice + tail for choice in body.split(",")]


def _translate(pattern):
    parts = []
    index = 0
    length = len(pattern)
    while index < length:
        char = pattern[index]
        if pattern.startswith("**/", index):
            parts.append("(?:.*/)?")
            index += 3
        elif pattern.startswith("**", index):
            parts.append(".*")
            index += 2
        elif char == "*":
            parts.append("[^/]*")
            index += 1
        elif char == "?":
            parts.append("[^/]")
            index += 1
        elif char == "[":
            close = _class_end(pattern, index)
            if close == -1:
                parts.append(re.escape(char))
                index += 1
            else:
                parts.append(_character_class(pattern[index:close + 1]))
                index = close + 1
        else:
            parts.append(re.escape(char))
            index += 1
    return _compile("".join(parts) + r"\Z", pattern)


def _class_end(pattern, start):
    index = start + 1
    if index < len(pattern) and pattern[index] in "!^":
        index += 1
    if index < len(pattern) and pattern[index] == "]":
        index += 1
    while index < len(pattern) and pattern[index] != "]":
        index += 1
    return index if index < len(pattern) else -1


def _character_class(chunk):
    inner = chunk[1:-1]
    if inner.startswith("!"):
        inner = "^" + inner[1:]
    elif inner.startswith("^"):
        inner = "\\" + inner
    return "[" + inner + "]"


def _compile(expression, pattern):
    try:
        return re.compile(expression)
    except re.error:
        # A malformed class like '[z-a]' — match the text literally instead of failing.
        return re.compile(re.escape(pattern) + r"\Z")
