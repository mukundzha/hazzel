from .. import git


def git_status():
    ok, out, branch = git.status_porcelain()
    if not ok:
        return out
    if out.strip() in ("(clean)", ""):
        head = f"On {branch or 'HEAD'} — clean." if branch else "Clean."
        return head
    header = f"On {branch}." if branch else "Git status."
    return f"{header}\n{out}"
