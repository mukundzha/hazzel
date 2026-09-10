from __future__ import annotations

import json
import re
import subprocess

from . import git
from .config import PROJECT_ROOT

GH_TIMEOUT = 30
MAX_PR_BODY_CHARS = 12000
MAX_PR_LIST = 20

_NUMBER_RE = re.compile(r"^#?(\d+)$")


def _run_gh(args: list[str], timeout: int = GH_TIMEOUT) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "gh CLI is not installed. Install it (https://cli.github.com), then run `gh auth login`."
    except subprocess.TimeoutExpired:
        return False, f"gh {' '.join(args[:3])} timed out after {timeout}s."
    except OSError as e:
        return False, f"gh failed: {e}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = err or out or f"gh exited {proc.returncode}"
        low = msg.lower()
        if "not authenticated" in low or "auth" in low and "login" in low:
            return False, "gh is not authenticated — run `gh auth login` first, then retry."
        if "not a git repository" in low:
            return False, "Not a git repo here — run `git init` first, then retry."
        if "no pull requests" in low or "no open pull requests" in low:
            return True, "No open pull requests."
        return False, msg
    return True, out or "(empty)"


def _require_repo() -> str | None:
    if not git.is_repo():
        return "Not a git repo here — run `git init` first, then retry."
    return None


def is_available() -> bool:
    ok, _ = _run_gh(["--version"], timeout=10)
    return ok


def auth_ok() -> tuple[bool, str]:
    return _run_gh(["auth", "status"], timeout=10)


def parse_number(raw: str | int) -> int | None:
    m = _NUMBER_RE.match(str(raw or "").strip())
    if not m:
        return None
    try:
        n = int(m.group(1))
    except ValueError:
        return None
    return n if n > 0 else None


def pr_list(limit: int = 10) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    limit = max(1, min(limit, MAX_PR_LIST))
    ok, out = _run_gh([
        "pr", "list", "--limit", str(limit),
        "--json", "number,title,headRefName,author,statusCheckRollup",
        "--template",
        "{{range .}}{{tablerow .number .title .headRefName .author.login}}{{end}}",
    ])
    if not ok:
        if "no open pull requests" in out.lower() or out.strip() == "(empty)":
            return True, "No open pull requests."
        return False, out
    if not out.strip() or out.strip() == "(empty)":
        return True, "No open pull requests."
    return True, out.strip()


def pr_view(number: str | int) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    n = parse_number(number)
    if n is None:
        return False, f"Invalid PR number: {number!r}. Use e.g. /pr view 12."
    ok, out = _run_gh(["pr", "view", str(n), "--comments"])
    if not ok:
        return False, out
    if len(out) > MAX_PR_BODY_CHARS:
        out = out[: MAX_PR_BODY_CHARS - 400] + f"\n[…{len(out) - MAX_PR_BODY_CHARS} chars skipped…]"
    return True, out


def pr_diff(number: str | int) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    n = parse_number(number)
    if n is None:
        return False, f"Invalid PR number: {number!r}. Use e.g. /pr diff 12."
    ok, out = _run_gh(["pr", "diff", str(n)])
    if not ok:
        return False, out
    if len(out) > git.MAX_FILE_DIFF_CHARS:
        out = out[: git.MAX_FILE_DIFF_CHARS] + "\n[…diff truncated…]"
    return True, out or "No changes."


def pr_checks(number: str | int | None = None) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    args = ["pr", "checks"]
    if number is not None and str(number).strip():
        n = parse_number(number)
        if n is None:
            return False, f"Invalid PR number: {number!r}."
        args.append(str(n))
    ok, out = _run_gh(args)
    if not ok:
        return False, out
    return True, out


def pr_create(title: str, body: str = "") -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    title = (title or "").strip()
    if not title:
        return False, "PR title is required."
    if len(title) > 200:
        return False, "PR title too long (>200 chars)."
    if len(body or "") > MAX_PR_BODY_CHARS:
        body = body[:MAX_PR_BODY_CHARS]
    branch = git.branch_current()
    if not branch:
        return False, "Detached HEAD — checkout a branch first."
    if branch in ("main", "master"):
        return False, f"On {branch} — create a feature branch first (/branch create <name>)."
    ok, dirty = _run_gh(["--version"], timeout=10)
    if not ok:
        return False, dirty
    args = ["pr", "create", "--title", title]
    if body.strip():
        args += ["--body", body.strip()]
    ok, out = _run_gh(args, timeout=60)
    if not ok:
        low = out.lower()
        if "already exists" in low or "already a pull request" in low:
            return False, out + "\nTip: /pr view to open the existing PR."
        if "no commits" in low or "nothing to" in low:
            return False, out + "\nTip: push a branch with commits first (/push)."
        return False, out
    url = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("https://"):
            url = line
            break
    return True, url or out.splitlines()[0] if out else f"Opened PR: {title}"


def pr_close(number: str | int) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    n = parse_number(number)
    if n is None:
        return False, f"Invalid PR number: {number!r}. Use e.g. /pr close 12."
    ok, out = _run_gh(["pr", "close", str(n)], timeout=60)
    if not ok:
        return False, out
    return True, out.splitlines()[0] if out else f"Closed #{n}."


def pr_merge(number: str | int | None = None, method: str = "squash") -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    method = (method or "squash").strip().lower().lstrip("-")
    if method not in ("merge", "squash", "rebase"):
        return False, f"Invalid merge method: {method!r}. Use merge, squash, or rebase."
    args = ["pr", "merge", f"--{method}"]
    if number is not None and str(number).strip():
        n = parse_number(number)
        if n is None:
            return False, f"Invalid PR number: {number!r}."
        args.append(str(n))
    ok, out = _run_gh(args, timeout=60)
    if not ok:
        return False, out
    return True, out.splitlines()[0] if out else f"Merged ({method})."


def pr_comment(number: str | int, body: str) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    n = parse_number(number)
    if n is None:
        return False, f"Invalid PR number: {number!r}."
    body = (body or "").strip()
    if not body:
        return False, "Comment body is required."
    if len(body) > MAX_PR_BODY_CHARS:
        return False, "Comment too long (>12000 chars)."
    ok, out = _run_gh(["pr", "comment", str(n), "--body", body], timeout=60)
    if not ok:
        return False, out
    return True, out.splitlines()[0] if out else "Commented."


def suggest_pr_draft(diff: str, status: str) -> tuple[str, str]:
    from .git_suggest import heuristic_message

    title = heuristic_message(status, diff)
    title = title.replace("chore:", "feat:").strip()[:100] or "feat: update branch"
    lines = []
    for line in (status or "").splitlines():
        line = line.strip()
        if line and not line.startswith("##"):
            lines.append(line[2:].strip() if len(line) > 2 else line)
    summary = f"Changes {len(lines)} file(s)." if lines else "See diff."
    body = f"## Summary\n{summary}\n"
    return title, body


def fetch_pr_json(number: str | int) -> tuple[bool, dict]:
    n = parse_number(number)
    if n is None:
        return False, {}
    try:
        proc = subprocess.run(
            ["gh", "pr", "view", str(n), "--json", "number,title,body,headRefName,baseRefName,author,url,state"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=GH_TIMEOUT,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False, {}
    if proc.returncode != 0:
        return False, {}
    try:
        return True, json.loads(proc.stdout or "{}")
    except (json.JSONDecodeError, ValueError):
        return False, {}
