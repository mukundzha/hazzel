import os
import re
import shutil
import subprocess

from .. import tool_cache
from ..config import PROJECT_ROOT, resolve_project_path

SKIP_DIRS = frozenset({
    ".git", ".hg", ".svn",
    "__pycache__", ".venv", "venv", "env", ".env",
    "node_modules", "build", "dist", ".eggs",
    ".mypy_cache", ".ruff_cache", ".pytest_cache", ".tox", ".nox",
    ".idea", ".vscode",
})

MAX_MATCHES = 30
MAX_FILE_BYTES = 2_000_000
MAX_LINE_CHARS = 160


RG_TIMEOUT = 15

_no_match_message = "No matches found for '{pattern}' in '{path}'. Try a shorter literal, regex=True, or a wider path."


def search_files(pattern, path=".", regex=False):
    if not pattern:
        return "Search pattern is required — usage: search_files(pattern, path='.', regex=False)."

    try:
        root = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if not root.exists():
        return f"Path does not exist: {path}. Check the spelling or search from '.'."

    if regex:
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            return f"Invalid regex: {error}. Fix the pattern or retry with regex=False for a literal search."
    else:
        compiled = re.compile(re.escape(pattern))

    key = (pattern, str(root), bool(regex))
    use_cache = tool_cache.caching_enabled()
    if use_cache:
        hit = tool_cache.SEARCH.get(key)
        if hit is not None:
            return hit

    fast = _rg_search(pattern, root, bool(regex), path)
    result = fast if fast is not None else _py_search(compiled, root, pattern, path)
    if use_cache:
        tool_cache.SEARCH.set(key, result)
    return result


def _rg_search(pattern, root, use_regex, display="."):
    if not shutil.which("rg"):
        return None
    cmd = ["rg", "--no-heading", "--line-number", "--color=never", "--hidden",
           "--max-columns=200", f"--max-count={MAX_MATCHES + 1}"]
    for skipped in SKIP_DIRS:
        cmd += ["--glob", f"!{skipped}/**"]
    cmd += ["--glob", "!*.egg-info/**", "--max-filesize", str(MAX_FILE_BYTES)]
    if use_regex:
        cmd += ["-e", pattern]
    else:
        cmd += ["-F", "-e", pattern]
    cmd.append(str(root) if root.is_file() else str(root))
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=RG_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode == 1:
        return _no_match_message.format(pattern=pattern, path=display)
    if proc.returncode != 0:
        return None
    try:
        text = proc.stdout.decode("utf-8", errors="replace")
    except (ValueError, UnicodeDecodeError):
        return None
    matches = []
    truncated = False
    for raw_line in text.splitlines():
        parts = raw_line.split(":", 2)
        if len(parts) < 3:
            continue
        file_part, number, content = parts
        try:
            rel = os.path.relpath(os.path.join(str(root), file_part) if not os.path.isabs(file_part) else file_part, PROJECT_ROOT)
        except ValueError:
            rel = file_part
        line = content.strip()
        if len(line) > MAX_LINE_CHARS:
            line = line[:MAX_LINE_CHARS] + "…"
        if len(matches) >= MAX_MATCHES:
            truncated = True
            break
        matches.append(f"{rel}:{number.strip()}: {line}")
    if not matches:
        return _no_match_message.format(pattern=pattern, path=display)
    output = "\n".join(matches)
    if truncated:
        output += f"\n[Truncated at {MAX_MATCHES} matches; narrow the pattern or path]"
    return output


def _py_search(compiled, root, pattern, path):
    matches = []
    truncated = False

    if root.is_file():
        files = [str(root)]
    else:
        files = _iter_files(root)

    for file_path in files:
        try:
            if os.path.getsize(file_path) > MAX_FILE_BYTES:
                continue
            with open(file_path, "rb") as f:
                data = f.read()
        except OSError:
            continue

        # Null byte in the first block almost always means a binary file.
        if b"\0" in data[:8192]:
            continue

        text = data.decode("utf-8", errors="replace")

        # One search over the whole file skips non-matching files without splitting lines.
        if not compiled.search(text):
            continue

        rel = os.path.relpath(file_path, PROJECT_ROOT)
        for number, line in enumerate(text.splitlines(), 1):
            if compiled.search(line):
                if len(matches) >= MAX_MATCHES:
                    truncated = True
                    break
                line = line.strip()
                if len(line) > MAX_LINE_CHARS:
                    line = line[:MAX_LINE_CHARS] + "…"
                matches.append(f"{rel}:{number}: {line}")

        if truncated:
            break

    if not matches:
        return _no_match_message.format(pattern=pattern, path=path)

    output = "\n".join(matches)
    if truncated:
        output += f"\n[Truncated at {MAX_MATCHES} matches; narrow the pattern or path]"
    return output


def _name_index():
    try:
        return [(os.path.basename(p).lower(), os.path.relpath(p, PROJECT_ROOT)) for p in _iter_files(PROJECT_ROOT)]
    except OSError:
        return []


def missing_file_message(path, limit=3):
    # Suggest files elsewhere in the project with the same name so the model
    # can recover in one step instead of walking directories.
    name = os.path.basename(str(path).rstrip("/")).lower()
    matches = []
    if name:
        if tool_cache.caching_enabled():
            index = tool_cache.NAME_INDEX.get("all")
            if index is None:
                index = _name_index()
                tool_cache.NAME_INDEX.set("all", index)
            for base, rel in index:
                if base == name:
                    matches.append(rel)
                    if len(matches) >= limit:
                        break
        else:
            for file_path in _iter_files(PROJECT_ROOT):
                if os.path.basename(file_path).lower() == name:
                    matches.append(os.path.relpath(file_path, PROJECT_ROOT))
                    if len(matches) >= limit:
                        break
    message = f"File does not exist: {path}"
    if matches:
        message += f". Did you mean: {', '.join(matches)}?"
    return message


def _iter_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place so os.walk never descends into skipped directories.
        dirnames[:] = [
            d for d in dirnames
            if d not in SKIP_DIRS and not d.endswith(".egg-info")
        ]
        dirnames.sort()
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)
