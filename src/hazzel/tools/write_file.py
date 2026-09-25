from .. import safety
from .. import tool_cache
from .. import ui
from ..config import resolve_project_path
from .approvals import check as _approval_check
from .approvals import remember as _approval_remember
from .approvals import repeat_denial as _repeat_denial
from .approvals import sha_key


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
        key = sha_key("write_file", str(path), content or "")
        prior = _approval_check(key)
        if prior is False:
            return _repeat_denial("Write cancelled by user")
        if prior is None:
            ui.show_diff(safety.diff_text(display, original, content or ""))
            approved = ui.confirm(f"Overwrite {display}?")
            _approval_remember(key, approved)
            if not approved:
                return "Write cancelled by user"

    safety.checkpoint(path, content or "")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    except OSError as error:
        return f"Tool error: cannot write file ({error}). Check the path and permissions."

    tool_cache.invalidate_fs()
    return "Written."