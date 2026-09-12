import shlex
import subprocess

from .. import safety
from .. import ui
from .. import wincompat
from ..config import PROJECT_ROOT, resolve_project_path

_SHELL_OPS = {";", "&&", "||", "|"}

_SAFE_BINARIES = frozenset({"ls", "pwd", "echo", "cat", "head", "tail", "wc", "file", "uname", "whoami", "date", "basename", "dirname", "realpath", "printf", "true"})
_SAFE_WINDOWS_BINARIES = frozenset({"dir", "type", "cls", "ver", "echo"})
_SAFE_GIT_SUBCOMMANDS = frozenset({"status", "diff", "log"})


def is_safe_command(command):
    text = (command or "").strip()
    if not text:
        return False
    if "\n" in text or "\r" in text:
        return False
    for marker in (";", "&&", "||", "|", "`", "$(", ">", "<"):
        if marker in text:
            return False
    try:
        tokens = shlex.split(text)
    except ValueError:
        return False
    if not tokens:
        return False
    first = tokens[0].rsplit("/", 1)[-1]
    if first in _SAFE_BINARIES:
        return True
    if wincompat.is_windows() and first.lower() in _SAFE_WINDOWS_BINARIES:
        return True
    if first == "git" and len(tokens) >= 2 and tokens[1] in _SAFE_GIT_SUBCOMMANDS:
        return True
    return False


def _checkpoint_rm_targets(command):
    try:
        tokens = shlex.split(command)
    except ValueError:
        return
    if not tokens or tokens[0] != "rm":
        return
    for token in tokens[1:]:
        if token in _SHELL_OPS or token.startswith("-"):
            if token in _SHELL_OPS:
                break
            continue
        try:
            if any(c in token for c in "*?["):
                for match in sorted(PROJECT_ROOT.glob(token)):
                    if match.is_file():
                        try:
                            safety.checkpoint(match.resolve())
                        except ValueError:
                            continue
                continue
            safety.checkpoint(resolve_project_path(token))
        except ValueError:
            continue


DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_OUTPUT_CHARS = 8000
TAIL_CHARS = 4000


def _coerce_timeout(value):
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT
    if timeout != timeout:
        return DEFAULT_TIMEOUT
    if timeout < 1:
        return 1
    if timeout > MAX_TIMEOUT:
        return MAX_TIMEOUT
    return timeout


def _resolve_cwd(cwd):
    if not cwd:
        return PROJECT_ROOT
    try:
        resolved = resolve_project_path(cwd)
    except ValueError as error:
        raise ValueError(str(error))
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"cwd is not a directory: {cwd}")
    return resolved


def _spill_to_tmp(output):
    import tempfile
    try:
        with tempfile.NamedTemporaryFile(mode="w", prefix="hazzel-bash-", suffix=".log", delete=False, encoding="utf-8") as tmp:
            tmp.write(output)
            return tmp.name
    except OSError:
        return ""


def run_command(command, timeout=None, cwd=None, description=None, preapproved=False):
    text = (command or "").strip()
    if not text:
        return "Command is required."
    secs = DEFAULT_TIMEOUT if timeout is None else _coerce_timeout(timeout)
    try:
        workdir = _resolve_cwd(cwd)
    except ValueError as error:
        return str(error)
    if not preapproved and not is_safe_command(text):
        prompt = f"Hazzel wants to run: {text}"
        if description:
            prompt += f"\n{description}"
        prompt += "\nAllow?"
        if not ui.confirm(prompt):
            return "Command cancelled by user"
    _checkpoint_rm_targets(text)
    proc = None
    try:
        proc = subprocess.Popen(
            text,
            shell=True,
            cwd=workdir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            **wincompat.popen_kwargs(),
        )
        try:
            out, err = proc.communicate(timeout=secs)
        except subprocess.TimeoutExpired:
            wincompat.kill_proc(proc)
            proc.wait()
            label = int(secs) if float(secs).is_integer() else secs
            return f"Command timed out after {label} seconds — retry with a larger timeout (max {MAX_TIMEOUT}) or narrow its scope."
        result_stdout, result_stderr, returncode = out, err, proc.returncode
    except KeyboardInterrupt:
        if proc is not None:
            wincompat.kill_proc(proc)
            try:
                proc.wait(timeout=5)
            except OSError:
                pass
        return "Command cancelled by user"
    output = result_stdout if (result_stdout or "").strip() else (result_stderr or "")
    output = output or "Command completed with no output."
    if len(output) > MAX_OUTPUT_CHARS:
        path = _spill_to_tmp(output)
        tail = output[-TAIL_CHARS:]
        note = f"\n[Showing last {len(tail)} of {len(output)} chars."
        if path:
            note += f" Full output: {path}"
        note += "]"
        output = tail + note
    if returncode != 0:
        return f"Command failed (exit {returncode}):\n{output}"
    return output

