from .. import git
from .. import ui


def git_commit(message=None, files=None):
    if isinstance(files, str):
        files = [files] if files.strip() else None
    if files is not None and not isinstance(files, list):
        return "Tool error: files must be a list of paths."
    ok, preview = git.diff_text(False, ".")
    if not ok:
        return preview
    if preview.strip() in ("No changes.", "(clean)"):
        return "Nothing to commit — working tree clean."
    suggest_mode = not (message or "").strip() or (message or "").strip().lower() in ("suggest", "auto")
    if suggest_mode:
        from ..git_suggest import suggest_message

        _, status_out, _ = git.status_porcelain()
        try:
            ui.show_loader("Drafting commit message…")
            suggestion, fallback = suggest_message(preview, status_out)
        finally:
            ui.end_turn()
        ui.show_git_suggest(suggestion, fallback)
        action = ui.prompt_suggest_action()
        if action == "n":
            return "Commit cancelled by user"
        if action == "e":
            edited = ui.prompt_suggest_edit(suggestion)
            if edited is None:
                return "Commit cancelled by user"
            message = edited.strip()
            if not message:
                return "Commit cancelled by user"
            if len(message) > 500:
                return "Tool error: commit message too long (>500 chars)."
            scope = ", ".join(files) if files else "all changes"
            if not ui.confirm(f"Commit {scope} with message: {message!r}?"):
                return "Commit cancelled by user"
        else:
            message = suggestion
        ok, out = git.commit(message, files)
        return out
    if len(message.strip()) > 500:
        return "Tool error: commit message too long (>500 chars)."
    ui.show_diff(preview)
    scope = ", ".join(files) if files else "all changes"
    if not ui.confirm(f"Commit {scope} with message: {message!r}?"):
        return "Commit cancelled by user"
    ok, out = git.commit(message, files)
    return out
