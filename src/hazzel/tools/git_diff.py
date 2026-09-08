from .. import git


def git_diff(staged=False, path="."):
    path = path or "."
    if path != ".":
        ok, out = git.diff_file(path, bool(staged))
        return out
    ok, files, err = git.changed_files(bool(staged))
    if not ok:
        return err
    if not files:
        return "No changes."
    summary = [f"{len(files)} files changed:"]
    for f in files:
        summary.append(f"  {f['status']} {f['path']} (+{f['added']} -{f['deleted']})")
    ok, out = git.diff_text(bool(staged), ".")
    return "\n".join(summary) + "\n\n" + out
