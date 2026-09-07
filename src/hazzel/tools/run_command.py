import os
import shlex
import signal
import subprocess

from .. import safety
from .. import ui
from ..config import PROJECT_ROOT, resolve_project_path

_SHELL_OPS = {";", "&&", "||", "|"}


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


def run_command(command, preapproved=False):

    if not preapproved:
        if not ui.confirm(f"Hazzel wants to run: {command}\nAllow?"):
            return "Command cancelled by user"

    _checkpoint_rm_targets(command)

    proc = None
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
            return "Command timed out after 30 seconds — split it into a smaller step or narrow its scope."
        result_stdout, result_stderr, returncode = out, err, proc.returncode
    except KeyboardInterrupt:
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                proc.wait(timeout=5)
            except OSError:
                pass
        return "Command cancelled by user"

    output = result_stdout if result_stdout else result_stderr
    output = output or "Command completed with no output."

    if len(output) > 3000:
        output = output[:1000] + f"\n[…{len(output) - 2000} chars skipped…]\n" + output[-2000:]

    if returncode != 0:
        return f"Command failed (exit {returncode}):\n{output}"

    return output

