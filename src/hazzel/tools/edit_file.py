from .. import safety
from .. import tool_cache
from .. import ui
from ..config import resolve_project_path
from .approvals import check as _approval_check
from .approvals import remember as _approval_remember
from .approvals import repeat_denial as _repeat_denial
from .approvals import sha_key
from .search_files import missing_file_message


def edit_file(path, old_text, new_text):
    try:
        resolved = resolve_project_path(path)
    except ValueError as error:
        return str(error)

    if len(old_text or "") > 2000 or len(new_text or "") > 2000:
        return "Anchor too large: keep old_text/new_text under 2000 chars. Use a smaller unique anchor or multiple edits."

    if not resolved.exists():
        return missing_file_message(path)

    if not resolved.is_file():
        return "Path is not a file"

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"File is binary: {path}. Edits not supported."
    except OSError as error:
        return f"Tool error: cannot read file for editing ({error}). Check permissions."

    if content.count(old_text) > 1:
        return "Anchor matches multiple places: include more surrounding lines to make it unique."

    if old_text not in content:
        return "Text to replace was not found. Use search_files or read_file to copy the exact text, including whitespace."

    updated = content.replace(old_text, new_text, 1)

    key = sha_key("edit_file", str(resolved), old_text or "", new_text or "")
    prior = _approval_check(key)
    if prior is False:
        return _repeat_denial("Edit cancelled by user")
    if prior is None:
        ui.show_diff(safety.diff_text(path, content, updated))
        approved = ui.confirm(f"Apply edit to {path}?")
        _approval_remember(key, approved)
        if not approved:
            return "Edit cancelled by user"

    safety.checkpoint(resolved, updated)
    resolved.write_text(updated)

    tool_cache.invalidate_fs()
    return "Edited."

