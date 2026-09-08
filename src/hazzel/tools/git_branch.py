from .. import git
from .. import ui


def git_branch(action="current", name=""):
    action = (action or "current").strip().lower()
    if action in ("current", "show"):
        ok, out, current = git.branch_list()
        if not ok:
            return out
        return out or f"On {current}."
    if action == "list":
        ok, out, _ = git.branch_list()
        return out
    if action == "log":
        ok, out = git.log_entries(10)
        return out
    if action == "create":
        if not (name or "").strip():
            return "Tool error: branch name is required for create."
        if not ui.confirm(f"Create and switch to branch '{name.strip()}'?"):
            return "Branch cancelled by user"
        ok, out = git.create_branch(name)
        return out
    if action == "switch":
        if not (name or "").strip():
            return "Tool error: branch name is required for switch."
        if not ui.confirm(f"Switch to branch '{name.strip()}'?"):
            return "Branch cancelled by user"
        ok, out = git.switch_branch(name)
        return out
    return "Tool error: unknown branch action. Use current, list, log, create, switch."
