from .. import safety
from .. import ui
from ..config import resolve_project_path
from .search_files import missing_file_message

MAX_EDITS = 10
MAX_ANCHOR = 2000


def apply_edits(edits):
    if not isinstance(edits, list) or not edits:
        return "No edits provided: pass edits as a list of {path, old_text, new_text}."
    if len(edits) > MAX_EDITS:
        return f"Too many edits ({len(edits)}): max {MAX_EDITS} per call. Split into smaller calls."
    plans = {}
    order = []
    errors = []
    for i, item in enumerate(edits):
        tag = f"edit {i + 1}"
        if not isinstance(item, dict):
            errors.append(f"{tag}: must be {{path, old_text, new_text}}.")
            continue
        display = item.get("path") or item.get("file") or item.get("filename") or item.get("filepath") or item.get("target") or ""
        old_text = item.get("old_text", "")
        new_text = item.get("new_text", "")
        if not display:
            errors.append(f"{tag}: path is required.")
            continue
        if old_text is None or old_text == "":
            errors.append(f"{tag} ({display}): old_text is required.")
            continue
        if len(old_text) > MAX_ANCHOR or len(new_text or "") > MAX_ANCHOR:
            errors.append(f"{tag} ({display}): anchor too large, keep old_text/new_text under {MAX_ANCHOR} chars.")
            continue
        try:
            resolved = resolve_project_path(display)
        except ValueError as error:
            errors.append(f"{tag} ({display}): {error}")
            continue
        if not resolved.exists():
            errors.append(f"{tag} ({display}): {missing_file_message(display)}")
            continue
        if not resolved.is_file():
            errors.append(f"{tag} ({display}): path is not a file.")
            continue
        key = str(resolved)
        if key not in plans:
            try:
                original = resolved.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                errors.append(f"{tag} ({display}): file is binary, edits not supported.")
                continue
            except OSError as error:
                errors.append(f"{tag} ({display}): cannot read file ({error}).")
                continue
            plans[key] = {"display": display, "resolved": resolved, "original": original, "working": original}
            order.append(key)
        working = plans[key]["working"]
        if old_text not in working:
            errors.append(f"{tag} ({display}): text to replace was not found. Use search_files or read_file to copy the exact text, including whitespace.")
            continue
        if working.count(old_text) > 1:
            errors.append(f"{tag} ({display}): anchor matches multiple places, include more surrounding lines to make it unique.")
            continue
        plans[key]["working"] = working.replace(old_text, new_text or "", 1)
    if errors:
        return "Applied nothing. Fix and retry:\n" + "\n".join(errors)
    changed = [(k, plans[k]) for k in order if plans[k]["working"] != plans[k]["original"]]
    if not changed:
        return "Applied nothing: edits match existing content."
    for _, plan in changed:
        ui.show_diff(safety.diff_text(plan["display"], plan["original"], plan["working"]))
    files = len(changed)
    total = len(edits)
    if not ui.confirm(f"Apply {total} edits across {files} files?"):
        return "Edits cancelled by user"
    try:
        for _, plan in changed:
            safety.checkpoint(plan["resolved"])
        for _, plan in changed:
            plan["resolved"].write_text(plan["working"])
    except OSError as error:
        for _, plan in changed:
            try:
                plan["resolved"].write_text(plan["original"])
            except OSError:
                continue
        return f"Tool error: failed to apply edits ({error}). Rolled back."
    names = ", ".join(p["display"] for _, p in changed[:4])
    extra = "" if len(changed) <= 4 else f" +{len(changed) - 4} more"
    return f"Applied {total} edits across {files} files: {names}{extra}."
