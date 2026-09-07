import os
import re

from hazzel.config import resolve_project_path
from hazzel.tools.search_files import missing_file_message

MENTION_RE = re.compile(r'(?:^|(?<=\s))@(?:"([^"]+)"|\'([^\']+)\'|`([^`]+)`|(\S+))')

MAX_MENTION_FILES = 5
MAX_MENTION_CHARS = 3000
TRAILING_PUNCT = ".,!?;:)]"


def parse_mentions(text):
    seen = []
    for match in MENTION_RE.finditer(text or ""):
        raw = match.group(1) or match.group(2) or match.group(3) or match.group(4) or ""
        raw = raw.strip().rstrip(TRAILING_PUNCT)
        if not raw or raw == "@":
            continue
        if raw not in seen:
            seen.append(raw)
    return seen[:MAX_MENTION_FILES]


def _read_capped(resolved):
    try:
        data = resolved.read_bytes()
    except OSError:
        return None, "unreadable"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, "binary"
    lines = text.splitlines()
    numbered = [f"{i + 1:6d}| {line[:240]}" for i, line in enumerate(lines)]
    body = "\n".join(numbered)[:MAX_MENTION_CHARS]
    more = ""
    if len("\n".join(numbered)) > MAX_MENTION_CHARS or len(lines) > 80:
        more = f"\n[…{len(lines)} lines total; use read_file offset for more…]"
    return (body + more) or "(empty file)", None


def expand_mentions(text):
    targets = parse_mentions(text)
    if not targets:
        return "", [], {}, []
    blocks = []
    contents = {}
    ok = []
    errors = []
    for target in targets:
        try:
            resolved = resolve_project_path(target)
        except ValueError as error:
            errors.append(f"@{target}: {error}")
            continue
        if not resolved.exists():
            errors.append(f"@{target}: {missing_file_message(target)}")
            continue
        if resolved.is_dir():
            from hazzel.tools.list_files import list_files
            result = list_files(target)
            if isinstance(result, list):
                result = "\n".join(result) or "(empty directory)"
            blocks.append(f'<file path="{target}">\n{result}\n</file>')
            contents[target] = str(result)
            ok.append(target)
            continue
        try:
            if not resolved.is_file():
                errors.append(f"@{target}: not a file")
                continue
        except OSError:
            errors.append(f"@{target}: unreadable")
            continue
        if os.path.getsize(resolved) > 2_000_000:
            errors.append(f"@{target}: file too large, use search_files instead")
            continue
        body, err = _read_capped(resolved)
        if err:
            errors.append(f"@{target}: {err} file, skipped")
            continue
        blocks.append(f'<file path="{target}">\n{body}\n</file>')
        contents[target] = body
        ok.append(target)
    context = ""
    if blocks:
        context = "<attached_files>\n" + "\n".join(blocks) + "\n</attached_files>"
    if errors:
        context += ("\n" if context else "") + "<mention_errors>\n" + "\n".join(errors) + "\n</mention_errors>"
    return context, ok, contents, errors


def strip_mentions(text):
    return MENTION_RE.sub("", text or "").strip()
