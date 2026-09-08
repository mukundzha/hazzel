from __future__ import annotations

import re
import subprocess
from pathlib import Path

from .config import PROJECT_ROOT, resolve_project_path

GIT_TIMEOUT = 10
MAX_DIFF_CHARS = 12000
MAX_LOG_ENTRIES = 20
MAX_FILE_DIFF_CHARS = 60000
MAX_FILE_DIFF_LINES = 2500

_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")

_commit_undo: list[str | None] = []


def _run_git(args: list[str], timeout: int = GIT_TIMEOUT) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, "git is not installed."
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out after {timeout}s."
    except OSError as e:
        return False, f"git failed: {e}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        msg = err or out or f"git exited {proc.returncode}"
        return False, msg
    return True, out or "(clean)"


def is_repo() -> bool:
    ok, out = _run_git(["rev-parse", "--is-inside-work-tree"])
    return ok and out.strip() == "true"


def _require_repo() -> str | None:
    if not is_repo():
        return "Not a git repo here — run `git init` first, then retry."
    return None


def status_porcelain() -> tuple[bool, str, str]:
    err = _require_repo()
    if err:
        return False, err, ""
    ok, out = _run_git(["status", "--porcelain=v1", "-b"])
    if not ok:
        return False, out, ""
    ok_b, branch = _run_git(["branch", "--show-current"])
    branch = branch.strip() if ok_b else ""
    if not branch:
        for line in out.splitlines():
            if line.startswith("## "):
                branch = line[3:].split("...")[0].strip()
                break
    return True, out.strip() or "(clean)", branch


def diff_text(staged: bool = False, path: str = ".") -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    args = ["diff", "--no-color"]
    if staged:
        args.append("--staged")
    args += ["--", path if path else "."]
    ok, out = _run_git(args)
    if not ok:
        return False, out
    if out == "(clean)":
        return True, "No changes."
    if len(out) > MAX_DIFF_CHARS:
        out = out[: MAX_DIFF_CHARS - 400] + f"\n[…{len(out) - MAX_DIFF_CHARS} chars skipped…]"
    return True, out


def diff_numstat(staged: bool = False) -> dict[str, tuple[int, int]]:
    args = ["diff", "--numstat", "--no-color"]
    if staged:
        args.append("--staged")
    ok, out = _run_git(args)
    if not ok or out in ("(clean)", ""):
        return {}
    counts: dict[str, tuple[int, int]] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        try:
            added = 0 if parts[0] == "-" else int(parts[0])
            deleted = 0 if parts[1] == "-" else int(parts[1])
        except ValueError:
            added, deleted = 0, 0
        counts[parts[2].strip()] = (added, deleted)
    return counts


def changed_files(staged: bool = False) -> tuple[bool, list[dict], str]:
    err = _require_repo()
    if err:
        return False, [], err
    args = ["diff", "--name-status", "--no-color"]
    if staged:
        args.append("--staged")
    ok, out = _run_git(args)
    if not ok:
        return False, [], out
    counts = diff_numstat(staged)
    files: list[dict] = []
    seen: set[str] = set()
    for line in (out if out not in ("(clean)", "") else "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0].strip() if parts else ""
        if code.startswith("R") and len(parts) >= 3:
            path = f"{parts[1]} → {parts[2]}"
            key = parts[2].strip()
            status = "R"
        else:
            path = parts[1].strip() if len(parts) > 1 else line.strip()
            key = path
            status = code[:1] or "M"
        added, deleted = counts.get(key, counts.get(path, (0, 0)))
        files.append({"path": path, "key": key, "status": status, "added": added, "deleted": deleted})
        seen.add(key)
    if not staged:
        ok_s, status_out, _ = status_porcelain()
        if ok_s:
            for line in status_out.splitlines():
                if len(line) < 4 or line.startswith("##"):
                    continue
                if line[:2].strip() != "??":
                    continue
                path = line[3:].strip().strip('"')
                if not path or path in seen:
                    continue
                added = 0
                try:
                    p = Path(PROJECT_ROOT) / path
                    if p.is_file():
                        with p.open("r", encoding="utf-8", errors="replace") as fh:
                            for _ in range(MAX_FILE_DIFF_LINES):
                                if fh.readline() == "":
                                    break
                                added += 1
                except OSError:
                    pass
                files.append({"path": path, "key": path, "status": "?", "added": added, "deleted": 0})
    files.sort(key=lambda f: f["path"].lower())
    return True, files, ""


def diff_file(path: str, staged: bool = False) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    key = (path or "").strip()
    if not key or key.startswith("-"):
        return False, f"Invalid path: {path!r}."
    args = ["diff", "--no-color", "--no-ext-diff"]
    if staged:
        args.append("--staged")
    args += ["--", key]
    ok, out = _run_git(args, timeout=15)
    if not ok:
        return False, out
    if out and out != "(clean)":
        lines = out.splitlines()
        if len(lines) > MAX_FILE_DIFF_LINES or len(out) > MAX_FILE_DIFF_CHARS:
            kept = lines[:MAX_FILE_DIFF_LINES]
            text = "\n".join(kept)
            if len(text) > MAX_FILE_DIFF_CHARS:
                text = text[:MAX_FILE_DIFF_CHARS]
            text += f"\n[…{max(len(lines) - MAX_FILE_DIFF_LINES, 0)} more lines in this file…]"
            return True, text
        return True, out
    try:
        p = (Path(PROJECT_ROOT) / key).resolve()
        p.relative_to(Path(PROJECT_ROOT).resolve())
    except (ValueError, OSError):
        return True, "No changes."
    try:
        if not p.is_file():
            return True, "No changes."
        content = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, UnicodeDecodeError):
        return True, "Binary or unreadable file."
    if not content:
        return True, "Empty untracked file."
    shown = content[:MAX_FILE_DIFF_LINES]
    body = "\n".join(f"+{line}" for line in shown)
    if len(content) > MAX_FILE_DIFF_LINES:
        body += f"\n[…{len(content) - MAX_FILE_DIFF_LINES} more lines in this file…]"
    return True, f"--- /dev/null\n+++ b/{key}\n{body}"


def log_entries(limit: int = 10) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    limit = max(1, min(limit, MAX_LOG_ENTRIES))
    ok, out = _run_git(["log", f"-{limit}", "--oneline", "--decorate"])
    if not ok:
        return False, out
    return True, out


def branch_current() -> str:
    ok, out = _run_git(["branch", "--show-current"])
    return out.strip() if ok and out.strip() and out != "(clean)" else ""


def branch_list() -> tuple[bool, str, str]:
    err = _require_repo()
    if err:
        return False, err, ""
    ok, out = _run_git(["branch", "--list"])
    if not ok:
        return False, out, ""
    return True, out.strip() or "(no branches)", branch_current()


def _resolve_files(files: list[str] | None) -> tuple[list[str], str | None]:
    if not files:
        return [], None
    resolved: list[str] = []
    root = Path(PROJECT_ROOT).resolve()
    for f in files:
        try:
            p = resolve_project_path(f)
        except ValueError as e:
            return [], str(e)
        try:
            rel = str(p.resolve().relative_to(root))
        except ValueError:
            return [], f"Path is outside the project root: {f}."
        resolved.append(rel)
    return resolved, None


def commit(message: str, files: list[str] | None = None) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    message = (message or "").strip()
    if not message:
        return False, "Commit message is required."
    if len(message) > 500:
        return False, "Commit message too long (>500 chars)."
    targets, ferr = _resolve_files(files)
    if ferr:
        return False, ferr
    ok, head = _run_git(["rev-parse", "HEAD"])
    prior = head.strip() if ok else None
    if targets:
        ok, out = _run_git(["add", "--", *targets])
        if not ok:
            return False, out
    else:
        ok, out = _run_git(["add", "-A"])
        if not ok:
            return False, out
    ok, out = _run_git(["commit", "-m", message])
    if not ok:
        if "nothing to commit" in out.lower():
            return False, "Nothing to commit — working tree clean."
        return False, out
    _commit_undo.append(prior)
    del _commit_undo[: max(0, len(_commit_undo) - 20)]
    short = ""
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("["):
            short = line
            break
    return True, short or out.splitlines()[0] if out else "Committed."


def pop_commit_undo() -> str | None:
    if not _commit_undo:
        return None
    return _commit_undo.pop()


def create_branch(name: str) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    name = (name or "").strip()
    if not name or not _BRANCH_RE.match(name) or ".." in name:
        return False, f"Invalid branch name: {name!r}. Use letters, digits, . _ / -."
    ok, out = _run_git(["checkout", "-b", name])
    return (True, f"Switched to new branch '{name}'.") if ok else (False, out)


def switch_branch(name: str) -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    name = (name or "").strip()
    if not name:
        return False, "Branch name is required."
    ok, dirty = _run_git(["status", "--porcelain=v1"])
    if not ok:
        return False, dirty
    if dirty.strip() and dirty.strip() != "(clean)":
        return False, "Working tree has changes — commit or stash first, then switch."
    ok, out = _run_git(["checkout", name])
    return (True, f"Switched to '{name}'.") if ok else (False, out)


def push() -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    branch = branch_current()
    if not branch:
        return False, "Detached HEAD — checkout a branch first."
    ok, upstream = _run_git(["rev-parse", "--abbrev-ref", "@{u}"])
    if ok and upstream and upstream != "(clean)":
        ok, out = _run_git(["push"], timeout=60)
    else:
        ok, out = _run_git(["push", "-u", "origin", branch], timeout=60)
    if not ok:
        return False, out
    return True, _summarize_push(out, branch)


def _summarize_push(out: str, branch: str) -> str:
    for line in out.splitlines():
        low = line.strip().lower()
        if "everything up-to-date" in low or "up to date" in low:
            return f"{branch} is already up to date."
    return f"Pushed {branch}."


def pull() -> tuple[bool, str]:
    err = _require_repo()
    if err:
        return False, err
    ok, dirty = _run_git(["status", "--porcelain=v1"])
    if not ok:
        return False, dirty
    if dirty.strip() and dirty.strip() != "(clean)":
        return False, "Working tree has changes — commit or stash first, then pull."
    ok, out = _run_git(["pull"], timeout=60)
    if not ok:
        return False, out
    if "already up to date" in out.lower():
        return True, "Already up to date."
    return True, out.splitlines()[0] if out else "Pulled."


def sync() -> tuple[bool, str]:
    ok, out = pull()
    if not ok:
        return False, out
    return push()
