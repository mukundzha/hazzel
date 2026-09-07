import os
import re

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
            regex = re.compile(pattern)
        except re.error as error:
            return f"Invalid regex: {error}. Fix the pattern or retry with regex=False for a literal search."
    else:
        regex = re.compile(re.escape(pattern))

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
        if not regex.search(text):
            continue

        rel = os.path.relpath(file_path, PROJECT_ROOT)
        for number, line in enumerate(text.splitlines(), 1):
            if regex.search(line):
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
        return f"No matches found for '{pattern}' in '{path}'. Try a shorter literal, regex=True, or a wider path."

    output = "\n".join(matches)
    if truncated:
        output += f"\n[Truncated at {MAX_MATCHES} matches; narrow the pattern or path]"
    return output


def missing_file_message(path, limit=3):
    # Suggest files elsewhere in the project with the same name so the model
    # can recover in one step instead of walking directories.
    name = os.path.basename(str(path).rstrip("/")).lower()
    matches = []
    if name:
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
