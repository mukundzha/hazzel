from __future__ import annotations


REVIEW_SYSTEM = (
    "You are a world-class staff software engineer and code reviewer — the person teams "
    "call when a change must not break production. Review the diff below with senior-level judgment."
    "\n\nCheck in order: 1) correctness bugs (logic, off-by-one, wrong conditions, missing branches), "
    "2) security issues (injection, secrets, auth, unsafe input, SSRF), "
    "3) edge cases and error handling (nulls, empty input, failures, timeouts), "
    "4) data loss and concurrency risks, 5) performance regressions, "
    "6) API and naming clarity, 7) missing or weak tests."
    "\n\nReply in exactly this shape:"
    "\nVerdict: APPROVE or REQUEST CHANGES plus one line saying why."
    "\nFindings: grouped under [Critical], [Major], [Minor], [Nit] — each item gives file:line, "
    "what is wrong, and the concrete fix. Skip empty groups. No more than 8 findings total."
    "\nGood: one or two lines on what the change does well, or 'Nothing notable'."
    "\n\nRules: review only what the diff changes. Be specific — quote the line. "
    "No hedging, no generic advice, no style nitpicks beyond consistency with the file. "
    "If the diff is trivially safe, say APPROVE with an empty findings list."
)

MAX_REVIEW_DIFF = 8000


def parse_review_args(rest):
    import shlex

    staged = False
    path = "."
    codebase = False
    try:
        parts = shlex.split(rest or "", posix=True)
    except ValueError:
        parts = (rest or "").split()
    for part in parts:
        low = part.lower()
        if low in ("--staged", "staged"):
            staged = True
        elif low in ("--unstaged", "unstaged"):
            staged = False
        elif low in ("codebase", "/codebase"):
            codebase = True
        elif part.startswith("--"):
            key, _, value = part[2:].partition("=")
            value = value.strip().strip("\"'")
            if key.lower() == "staged":
                staged = value not in ("0", "false", "no", "off")
            elif key.lower() == "path" and value:
                path = value
        elif not part.startswith("-"):
            path = part[1:] if part.startswith("@") else part
    return staged, path, codebase


def heuristic_review(summary: str, scope: str) -> str:
    lines = [
        f"Review draft for {scope} (model unreachable — verify by hand):",
        "",
        summary,
        "",
        "Check by hand: correctness of changed conditions, unhandled errors and empty input, "
        "secrets or unsafe input, and whether tests cover the new branches.",
    ]
    return "\n".join(lines)


def review(staged: bool = False, path: str = ".", codebase: bool = False) -> str:
    from . import git

    path = (path or ".").strip()
    if path.startswith("@"):
        path = path[1:].strip().strip("\"'")
    if not path:
        path = "."
    scope = "staged changes" if staged else "unstaged changes"
    if path != ".":
        scope += f" in {path}"
    if codebase:
        scope = "whole codebase (staged + unstaged changes)"
    try:
        if codebase:
            ok, u_files, u_err = git.changed_files(False)
            if not ok:
                return u_err
            ok, s_files, s_err = git.changed_files(True)
            if not ok:
                return s_err
            merged = {f["path"]: f for f in u_files + s_files}
            files = list(merged.values())
            if not files:
                return "No changes to review in the whole codebase."
            ok, u_diff = git.diff_text(False, ".")
            if not ok:
                return u_diff
            ok, s_diff = git.diff_text(True, ".")
            if not ok:
                return s_diff
            diff = "\n".join(d for d in (u_diff, s_diff) if d and d.strip() != "No changes.")
        elif path != ".":
            ok, diff = git.diff_file(path, bool(staged))
            files = []
            if not ok:
                return diff
        else:
            ok, files, err = git.changed_files(bool(staged))
            if not ok:
                return err
            if not files:
                return f"No {scope} to review."
            ok, diff = git.diff_text(bool(staged), ".")
            if not ok:
                return diff
    except Exception as error:
        return f"Tool error: cannot collect diff ({error})."
    if not (diff or "").strip() or diff.strip() == "No changes.":
        return f"No {scope} to review."
    summary = "\n".join(f"  {f['status']} {f['path']} (+{f['added']} -{f['deleted']})" for f in files) if files else f"  {path}"
    clipped = diff[:MAX_REVIEW_DIFF]
    messages = [
        {"role": "system", "content": REVIEW_SYSTEM},
        {"role": "user", "content": f"SCOPE: {scope}\n\nFILES:\n{summary}\n\nDIFF:\n{clipped}"},
    ]
    try:
        from .providers import get_provider

        resp = get_provider().chat(messages, [])
        text = (getattr(resp, "content", None) or "").strip()
    except Exception:
        return heuristic_review(summary, scope)
    if not text:
        return heuristic_review(summary, scope)
    return text
