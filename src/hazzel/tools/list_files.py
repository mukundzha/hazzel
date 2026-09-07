from ..config import resolve_project_path


def list_files(path):
    try:
        path = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if not path.exists():
        return f"Path does not exist: {path}. Check the spelling or list a parent directory."

    if not path.is_dir():
        return f"Path is not a directory: {path}. Use read_file to view it, or list its parent."

    try:
        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError as error:
        return f"Tool error: cannot list directory ({error}). Check permissions."
    names = [item.name + ("/" if item.is_dir() else "") for item in items[:200]]
    if len(items) > 200:
        names.append(f"[{len(items) - 200} more; use search_files to narrow]")
    return names