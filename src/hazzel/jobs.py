"""Background shell jobs — stdlib only.

Long commands (`pytest -q`, dev servers, builds) can run detached so the
agent keeps working while they run::

    run_command(command="pytest -q", background=True)  # -> job id
    jobs(action="poll", job_id=1)                      # tail of output
    jobs(action="list")                                # every job + state
    jobs(action="kill", job_id=1)                      # stop one

Jobs are per-process (in-memory) with a full log per job spilled to
``/tmp/hazzel-job-*.log``. Stdout and stderr are merged in the log so a
single reader thread preserves ordering. Remaining jobs are killed on
exit (best effort) to avoid orphaned process groups.
"""

from __future__ import annotations

import atexit
import subprocess
import tempfile
import threading
import time
from pathlib import Path

MAX_JOBS = 32
MAX_MEM_LINES = 2000
TAIL_LINES_DEFAULT = 40
TAIL_LINES_MAX = 200
TAIL_CHARS = 4000
WAIT_TIMEOUT_DEFAULT = 30
WAIT_TIMEOUT_MAX = 120
WAIT_POLL_INTERVAL = 0.2


_lock = threading.Lock()
_jobs: dict[int, "_Job"] = {}
_next_id = 1


def _now() -> float:
    return time.monotonic()


def _fmt_elapsed(seconds: float) -> str:
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return "?s"
    if seconds < 0:
        seconds = 0
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    if mins < 60:
        return f"{mins}m{secs:02d}s"
    hours, mins = divmod(mins, 60)
    return f"{hours}h{mins:02d}m"


class _Job:
    """One detached process plus its captured output."""

    def __init__(self, job_id: int, command: str, cwd: Path, description: str):
        self.job_id = job_id
        self.command = command
        self.cwd = cwd
        self.description = description
        self.started = _now()
        self.ended: float | None = None
        self.exit_code: int | None = None
        self.killed = False
        self._lines: list[str] = []
        self._lines_lock = threading.Lock()
        self.log_path = ""
        self.proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None

    def status(self) -> str:
        if self.proc is not None and self.proc.poll() is None:
            return "running"
        if self.killed:
            return "killed"
        return "done"

    def elapsed(self) -> float:
        end = self.ended if self.ended is not None else _now()
        return max(0.0, end - self.started)

    def append(self, line: str) -> None:
        with self._lines_lock:
            self._lines.append(line)
            if len(self._lines) > MAX_MEM_LINES:
                del self._lines[: len(self._lines) - MAX_MEM_LINES]

    def tail(self, limit: int = TAIL_LINES_DEFAULT) -> str:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = TAIL_LINES_DEFAULT
        limit = max(1, min(TAIL_LINES_MAX, limit))
        with self._lines_lock:
            lines = list(self._lines[-limit:])
        out = "".join(lines)
        if len(out) > TAIL_CHARS:
            out = out[-TAIL_CHARS:]
        return out


def split_background_marker(text: str) -> tuple[str, bool]:
    """Split a trailing ``&`` background marker: ``("sleep 5 &",)`` -> ``("sleep 5", True)``.

    A trailing ``&&`` is a shell operator, not a marker. Quoted ampersands
    mid-command are untouched — only the last non-space character matters.
    """
    stripped = (text or "").rstrip()
    if stripped.endswith("&") and not stripped.endswith("&&"):
        return stripped[:-1].rstrip(), True
    return text, False


def _parse_id(value) -> int | None:
    try:
        job_id = int(str(value).strip().lstrip("#"))
    except (TypeError, ValueError):
        return None
    return job_id if job_id > 0 else None


def _short(command: str, limit: int = 60) -> str:
    command = " ".join((command or "").split())
    if len(command) > limit:
        return command[: limit - 1].rstrip() + "…"
    return command


def _prune_locked() -> None:
    """Evict oldest finished jobs so the registry stays bounded."""
    if len(_jobs) < MAX_JOBS:
        return
    done = sorted(
        (j for j in _jobs.values() if j.status() != "running"),
        key=lambda j: j.ended or 0.0,
    )
    for job in done:
        if len(_jobs) < MAX_JOBS:
            break
        _jobs.pop(job.job_id, None)


def _read_loop(job: _Job) -> None:
    proc = job.proc
    log_file = None
    try:
        try:
            log_file = open(job.log_path, "a", encoding="utf-8", errors="replace")
        except OSError:
            log_file = None
        try:
            assert proc is not None and proc.stdout is not None
            for line in proc.stdout:
                job.append(line)
                if log_file is not None:
                    try:
                        log_file.write(line)
                        log_file.flush()
                    except OSError:
                        pass
        except Exception:
            pass
        finally:
            try:
                if proc is not None:
                    proc.wait()
            except Exception:
                pass
            job.ended = _now()
            try:
                job.exit_code = proc.returncode if proc is not None else None
            except Exception:
                job.exit_code = None
            if log_file is not None:
                try:
                    log_file.close()
                except OSError:
                    pass
    except Exception:
        pass


def start(command: str, cwd, description: str = "") -> str:
    """Spawn ``command`` detached. Returns a human-readable receipt with the job id."""
    from . import wincompat as _win

    text = (command or "").strip()
    if not text:
        return "Command is required."
    base = Path(cwd) if cwd is not None else Path.cwd()
    try:
        log_fd, log_name = tempfile.mkstemp(prefix="hazzel-job-", suffix=".log")
    except OSError as error:
        return f"Tool error: could not create job log ({error})."
    try:
        import os

        os.close(log_fd)
    except OSError:
        pass
    with _lock:
        _prune_locked()
        running = sum(1 for j in _jobs.values() if j.status() == "running")
        if len(_jobs) >= MAX_JOBS and running >= MAX_JOBS:
            try:
                Path(log_name).unlink()
            except OSError:
                pass
            return f"Too many background jobs ({MAX_JOBS} running). Kill one with jobs(action=kill, job_id=…) first."
        global _next_id
        job_id = _next_id
        _next_id += 1
        job = _Job(job_id, text, base, (description or "").strip()[:200])
        job.log_path = log_name
        try:
            job.proc = subprocess.Popen(
                text,
                shell=True,
                cwd=str(base),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                **_win.popen_kwargs(),
            )
        except (OSError, ValueError) as error:
            _jobs.pop(job_id, None)
            try:
                Path(log_name).unlink()
            except OSError:
                pass
            return f"Tool error: could not start background job ({error})."
        _jobs[job_id] = job
        reader = threading.Thread(target=_read_loop, args=(job,), daemon=True)
        job._reader = reader
        reader.start()
    short = _short(text)
    hint = f"jobs(action=poll, job_id={job_id})"
    return (
        f"Started background job {job_id}: {short}\n"
        f"Poll with {hint} (or /jobs {job_id}); wait blocks until done; kill with jobs(action=kill, job_id={job_id}).\n"
        f"Full log: {log_name}"
    )


def poll(job_id, limit: int = TAIL_LINES_DEFAULT) -> str:
    with _lock:
        job = _jobs.get(_parse_id(job_id) or -1)
    if job is None:
        return f"No background job {_parse_id(job_id) or job_id}. Use jobs(action=list) to see jobs."
    state = job.status()
    short = _short(job.command)
    tail = job.tail(limit).rstrip()
    if state == "running":
        head = f"Job {job.job_id} · running {_fmt_elapsed(job.elapsed())} · {short}"
    elif state == "killed":
        head = f"Job {job.job_id} · killed after {_fmt_elapsed(job.elapsed())} · {short}"
    else:
        head = f"Job {job.job_id} · done exit {job.exit_code} in {_fmt_elapsed(job.elapsed())} · {short}"
    body = tail if tail else "(no output yet)"
    if len(body) >= TAIL_CHARS:
        body += f"\n[…tail capped at {TAIL_CHARS} chars…]"
    return f"{head}\n{body}\nFull log: {job.log_path}"


def _coerce_timeout(value) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return float(WAIT_TIMEOUT_DEFAULT)
    if timeout != timeout:  # NaN
        return float(WAIT_TIMEOUT_DEFAULT)
    if timeout < 1:
        return 1.0
    if timeout > WAIT_TIMEOUT_MAX:
        return float(WAIT_TIMEOUT_MAX)
    return timeout


def wait(job_id, limit: int = TAIL_LINES_DEFAULT, timeout=None) -> str:
    """Block until a job finishes or ``timeout`` seconds pass.

    Read-only: never touches the process. Returns the same receipt as
    :func:`poll` so callers can use one code path for both.
    """
    if _parse_id(job_id) is None:
        return "Usage: jobs(action=wait, job_id=<n>). Use jobs(action=list) to see jobs."
    secs = _coerce_timeout(WAIT_TIMEOUT_DEFAULT if timeout is None else timeout)
    deadline = _now() + secs
    with _lock:
        job = _jobs.get(_parse_id(job_id) or -1)
    while job is not None and job.status() == "running" and _now() < deadline:
        time.sleep(WAIT_POLL_INTERVAL)
        with _lock:
            job = _jobs.get(_parse_id(job_id) or -1)
    out = poll(job_id, limit)
    if job is not None and job.status() == "running":
        label = int(secs) if float(secs).is_integer() else secs
        out += f"\n[still running after {label}s — wait again or poll for the tail.]"
    return out


def _delete_log(path: str) -> None:
    try:
        if path:
            Path(path).unlink()
    except OSError:
        pass


def clear() -> str:
    """Drop finished jobs from the registry and delete their logs.

    Running jobs are never touched. Returns a short receipt.
    """
    with _lock:
        finished = [j for j in _jobs.values() if j.status() != "running"]
        running = len(_jobs) - len(finished)
        for job in finished:
            _jobs.pop(job.job_id, None)
    for job in finished:
        _delete_log(job.log_path)
    if not finished and not running:
        return "No background jobs. Start one with run_command(background=true) or `!command &`."
    if not finished:
        return f"No finished jobs to clear. {running} running."
    noun = "job" if len(finished) == 1 else "jobs"
    tail = f" {running} running." if running else ""
    return f"Cleared {len(finished)} finished {noun}.{tail}"


def list_jobs() -> str:
    with _lock:
        ordered = sorted(_jobs.values(), key=lambda j: j.job_id)
    if not ordered:
        return "No background jobs. Start one with run_command(background=true) or `!command &`."
    rows = [f"Background jobs ({len(ordered)}):"]
    for job in ordered:
        state = job.status()
        if state == "running":
            mark = f"running {_fmt_elapsed(job.elapsed())}"
        elif state == "killed":
            mark = f"killed in {_fmt_elapsed(job.elapsed())}"
        else:
            mark = f"done exit {job.exit_code} in {_fmt_elapsed(job.elapsed())}"
        rows.append(f"- {job.job_id} · {mark} · {_short(job.command)}")
    rows.append("Poll with jobs(action=poll, job_id=…) or /jobs <id>; wait blocks until done; clear drops finished.")
    return "\n".join(rows)


def kill(job_id) -> str:
    from . import wincompat as _win

    with _lock:
        job = _jobs.get(_parse_id(job_id) or -1)
    if job is None:
        return f"No background job {_parse_id(job_id) or job_id}. Use jobs(action=list) to see jobs."
    proc = job.proc
    if proc is None or proc.poll() is not None:
        code = job.exit_code
        return f"Job {job.job_id} already finished (exit {code})."
    _win.kill_proc(proc)
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    job.killed = True
    if job.ended is None:
        job.ended = _now()
    try:
        job.exit_code = proc.returncode
    except Exception:
        pass
    return f"Killed background job {job.job_id}: {_short(job.command)}."


def jobs_tool(action: str = "list", job_id=None, limit: int = TAIL_LINES_DEFAULT, timeout=None) -> str:
    act = (action or "list").strip().lower()
    if act in ("ls", "show"):
        act = "list"
    if act in ("get", "log", "output", "tail"):
        act = "poll"
    if act in ("stop", "cancel"):
        act = "kill"
    if act == "watch":
        act = "wait"
    if act in ("clean", "purge"):
        act = "clear"
    if act == "list":
        return list_jobs()
    if act == "poll":
        if _parse_id(job_id) is None:
            return "Usage: jobs(action=poll, job_id=<n>). Use jobs(action=list) to see jobs."
        return poll(job_id, limit)
    if act == "wait":
        return wait(job_id, limit, timeout)
    if act == "clear":
        return clear()
    if act == "kill":
        if _parse_id(job_id) is None:
            return "Usage: jobs(action=kill, job_id=<n>). Use jobs(action=list) to see jobs."
        return kill(job_id)
    return "Usage: jobs(action=list|poll|wait|clear|kill, job_id=<n>)."


def reset() -> None:
    """Kill everything and clear the registry. Tests only."""
    with _lock:
        current = list(_jobs.values())
        _jobs.clear()
        global _next_id
        _next_id = 1
    from . import wincompat as _win

    for job in current:
        try:
            proc = job.proc
            if proc is not None and proc.poll() is None:
                _win.kill_proc(proc)
        except Exception:
            continue


def shutdown() -> None:
    with _lock:
        current = [j for j in _jobs.values() if j.status() == "running"]
    if not current:
        return
    from . import wincompat as _win

    for job in current:
        try:
            proc = job.proc
            if proc is not None and proc.poll() is None:
                _win.kill_proc(proc)
        except Exception:
            continue


try:
    atexit.register(shutdown)
except Exception:
    pass
