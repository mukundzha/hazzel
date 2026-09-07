from .. import safety
from .. import ui
from ..config import resolve_project_path


def write_file(path, content):
    display = path
    try:
        path = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if len(content or "") > 8000:
        return "Content too large (>8000 chars): create a minimal version first, then extend with edit_file."

    if path.exists() and path.is_file():
        try:
            original = path.read_bytes()
        except OSError as error:
            return f"Tool error: cannot read existing file before overwrite ({error}). Check permissions."
        ui.show_diff(safety.diff_text(display, original, content or ""))
        if not ui.confirm(f"Overwrite {display}?"):
            return "Write cancelled by user"

    safety.checkpoint(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except OSError as error:
        return f"Tool error: cannot write file ({error}). Check the path and permissions."

    return "Written."