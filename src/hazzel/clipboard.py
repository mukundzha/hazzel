import re
import shutil
import subprocess

_CODE_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)


def extract_last_code_block(text):
    blocks = _CODE_RE.findall(text or "")
    if not blocks:
        return None
    return blocks[-1].strip()


def copy_text(text):
    if not (text or "").strip():
        return False, "Nothing to copy yet — run a task first."
    for cmd in (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]):
        if not shutil.which(cmd[0]):
            continue
        try:
            subprocess.run(cmd, input=text.encode("utf-8"), timeout=5, check=True)
            return True, "Copied to clipboard."
        except (subprocess.SubprocessError, OSError):
            continue
    return False, "No clipboard tool found (pbcopy, wl-copy, xclip, or xsel)."
