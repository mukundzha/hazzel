from ..config import resolve_project_path
from .search_files import missing_file_message

MAX_READ_CHARS = 3000
DEFAULT_READ_LIMIT = 60


def read_file(path, offset=1, limit=60):
    try:
        resolved = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if not resolved.exists():
        return missing_file_message(path)

    if not resolved.is_file():
        return f"Path is not a file: {path}. Use list_files to browse it."

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"File is binary: {path}. Reads not supported — describe what you need and I will search around it."
    except OSError as error:
        return f"Tool error: cannot read file ({error}). Check permissions."
    text = content if isinstance(content, str) else content.decode("utf-8", errors="replace")

    try:
        offset = int(offset)
    except (TypeError, ValueError):
        offset = 1
    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = DEFAULT_READ_LIMIT

    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return f"File `{path}` is empty."
    start = max(1, min(offset, total)) - 1

    end = None
    if limit is None:
        slice_lines = lines[start:start + DEFAULT_READ_LIMIT]
        end = start + DEFAULT_READ_LIMIT
    else:
        end = start + max(0, limit)
        slice_lines = lines[start:end]

    if not slice_lines:
        return f"File `{path}` exists but no content at offset {offset}."

    body = "\n".join(f"{i + 1:6d}| {line[:300]}" for i, line in enumerate(slice_lines, start))
    body = body[:MAX_READ_CHARS]
    out = [body]

    if end is not None and end < total:
        out.append(f"[{len(slice_lines)} of {total} lines; offset={end + 1} for more]")
    return "\n".join(out)