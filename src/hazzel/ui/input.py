"""Welcome header, terminal width, @mention completion, and keyboard input."""

import os
import re
import sys
import time

from rich.text import Text

from . import _state as _st
from ._state import DIM_COLOR, HAZZEL_COLOR, is_no_color


def show_welcome(model, project_root):
    _st.console.print()
    _show_header(model, project_root)
    _st.console.print()

def _hw():
    try:
        import shutil

        return max(20, int(shutil.get_terminal_size(fallback=(80, 24)).columns))
    except Exception:
        pass
    try:
        return max(20, int(_st.console.width))
    except Exception:
        return 80

def rule():
    _st.console.print(Text("─" * _hw(), style="dim"))

def _rule_ansi():
    if is_no_color():
        return "─" * _hw()
    return "\x1b[2m" + ("─" * _hw()) + "\x1b[0m"

def _show_header(display_name, project_root):
    try:
        from importlib.metadata import version as _pkg_version
        _ver = _pkg_version("hazzel")
    except Exception:
        try:
            from hazzel import __version__ as _ver
        except Exception:
            _ver = "1.4.3"
    title = Text()
    title.append("hazzel", style=HAZZEL_COLOR)
    title.append(f" {_ver}", style=DIM_COLOR)
    _st.console.print(title)
    _st.console.print(Text(_short_path(project_root), style=DIM_COLOR))

SLASH_COMMANDS = [
    {"name": "/model", "desc": "switch model / provider"},
    {"name": "/think", "desc": "deeper reasoning on/off"},
    {"name": "/plan", "desc": "read-only plan mode on/off"},
    {"name": "/goal", "desc": "objective + run · criteria"},
    {"name": "/status", "desc": "git working-tree status"},
    {"name": "/diff", "desc": "git diff preview"},
    {"name": "/review", "desc": "read-only review of uncommitted diff"},
    {"name": "/commit", "desc": "suggest + commit (approval)"},
    {"name": "/log", "desc": "recent commits"},
    {"name": "/help", "desc": "show help"},
    {"name": "/docs", "desc": "full usage guide"},
    {"name": "/clear", "desc": "clear conversation + usage + saved session"},
    {"name": "/session", "desc": "restore last saved session"},
    {"name": "/summary", "desc": "summarize last implementation"},
    {"name": "/export", "desc": "save transcript to markdown"},
    {"name": "/copy", "desc": "copy last reply [code]"},
    {"name": "/init", "desc": "generate AGENTS.md map"},
    {"name": "/skills", "desc": "pick + attach a skill"},
    {"name": "/mcp", "desc": "list + use MCP servers"},
    {"name": "/retry", "desc": "re-run last message"},
    {"name": "/jobs", "desc": "background jobs list/poll/wait/kill/clear"},
    {"name": "/usage", "desc": "show token usage"},
    {"name": "/undo", "desc": "undo last file change"},
    {"name": "/logout", "desc": "clear saved API keys"},
    {"name": "/exit", "desc": "leave Hazzel"},
]

def _short_path(path):
    try:
        from pathlib import Path

        p = Path(path)
        home = Path.home()
        if p.is_relative_to(home):
            rel = p.relative_to(home)
            if len(rel.parts) > 1:
                return f"~/{rel.parts[-1].lower()}"
            return f"~/{str(rel).lower()}"
        return p.name and f"~/{p.name.lower()}" or str(p).lower()
    except OSError:
        return str(path).lower()

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")

def _visible_len(text):
    try:
        return len(_ANSI_RE.sub("", text or ""))
    except Exception:
        return len(text or "")

def _visual_rows(lines):
    try:
        width = max(20, _hw())
    except Exception:
        width = 80
    total = 0
    for line in lines or []:
        total += max(1, (_visible_len(line) + width - 1) // width) + line.count("\n")
    return max(0, total - 1)

_MENTION_TOKEN_RE = re.compile(r'(?:^|\s)@(?:"([^"]*)$|\'([^\']*)$|([^\s"\']*)$)')

_MENTION_ROWS = 8
_MENTION_FILE_CAP = 5000
_MENTION_CACHE_TTL = 30.0
_MENTION_EXTRA_SKIP = frozenset({"site", "dist", "build", ".venv"})

_file_cache = {"root": None, "ts": 0.0, "files": []}
_MAX_TOOL_ROWS = 8

def _active_mention(buffer):
    match = _MENTION_TOKEN_RE.search(buffer or "")
    if not match:
        return None
    query = match.group(1)
    if query is None:
        query = match.group(2)
    if query is None:
        query = match.group(3)
    at = buffer.find("@", match.start(0))
    if at == -1:
        return None
    return (at, query or "")

def _all_project_files():
    from hazzel import config

    root = str(config.PROJECT_ROOT)
    now = time.monotonic()
    if _file_cache["root"] == root and now - _file_cache["ts"] < _MENTION_CACHE_TTL and _file_cache["files"]:
        return _file_cache["files"]
    from hazzel.tools.search_files import SKIP_DIRS

    skip = SKIP_DIRS | _MENTION_EXTRA_SKIP
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip and not d.endswith(".egg-info")]
        dirnames.sort()
        for name in sorted(filenames):
            files.append(os.path.relpath(os.path.join(dirpath, name), root))
            if len(files) >= _MENTION_FILE_CAP:
                break
        if len(files) >= _MENTION_FILE_CAP:
            break
    _file_cache.update({"root": root, "ts": now, "files": files})
    return files

def _fuzzy_score(query, target):
    q = query.lower()
    t = target.lower()
    if not q or len(q) > 64:
        return None
    pos = []
    ti = 0
    for ch in q:
        nxt = t.find(ch, ti)
        if nxt == -1:
            return None
        pos.append(nxt)
        ti = nxt + 1
    score = float(pos[0]) * 2.0 + len(t) * 0.1
    consec = 0
    for idx, p in enumerate(pos):
        if idx > 0 and p == pos[idx - 1] + 1:
            consec += 1
            score -= 15.0
        else:
            if idx > 0:
                score += float(p - pos[idx - 1] - 1)
        if p == 0 or t[p - 1] in "/_-.:\\ ":
            score -= 10.0
        elif target[max(0, p - 1)].islower() and target[p].isupper():
            score -= 8.0
    score -= min(consec, 8) * 2.0
    return score

def _skill_candidates(query, limit=4):
    try:
        from hazzel import skills as _skills
        names = [s["name"] for s in _skills.discover_skills()]
    except Exception:
        return []
    q = (query or "").lower()
    if not q:
        return sorted(names, key=str.lower)[:limit]
    scored = []
    for name in names:
        low = name.lower()
        if low == q:
            scored.append((0, 0.0, name))
        elif low.startswith(q):
            scored.append((1, 0.0, name))
        elif q in low:
            scored.append((2, 0.0, name))
        else:
            score = _fuzzy_score(q, low)
            if score is not None:
                scored.append((3, score, name))
    scored.sort(key=lambda item: (item[0], item[1], item[2].lower()))
    return [name for _, _, name in scored[:limit]]

def _mention_candidates(query, limit=_MENTION_ROWS):
    try:
        skill_hits = _skill_candidates(query)
    except Exception:
        skill_hits = []
    files = _all_project_files()
    q = (query or "").lower().lstrip("./")
    if not q:
        ranked = sorted(files, key=lambda p: (p.count("/"), len(p), p.lower()))
        combined = skill_hits + [p for p in ranked if p not in skill_hits]
        return combined[:limit], len(skill_hits) + len(files)
    scored = []
    has_slash = "/" in q
    for path in files:
        low = path.lower()
        if has_slash:
            if q in low:
                scored.append((0 if low.startswith(q) else 1, 0.0, len(path), low, path))
                continue
            score = _fuzzy_score(q, low)
            if score is not None:
                scored.append((4, score, len(path), low, path))
        else:
            base = os.path.basename(low)
            if base == q:
                scored.append((0, 0.0, len(path), low, path))
            elif base.startswith(q):
                scored.append((1, 0.0, len(path), low, path))
            elif q in base:
                scored.append((2, 0.0, len(path), low, path))
            elif q in low:
                scored.append((3, 0.0, len(path), low, path))
            else:
                score = _fuzzy_score(q, base)
                if score is None:
                    score = _fuzzy_score(q, low)
                    if score is not None:
                        score += 20.0
                if score is not None:
                    scored.append((4, score, len(path), low, path))
    scored.sort(key=lambda item: (item[0], item[1], item[2], item[3]))
    ranked = [item[4] for item in scored[:50]]
    combined = skill_hits + [p for p in ranked if p not in skill_hits]
    return combined[:limit], len(skill_hits) + len(ranked)

def _accept_mention(buffer, full_path):
    mention = _active_mention(buffer)
    if not mention:
        return buffer
    at, _ = mention
    token = full_path if " " not in full_path else f'"{full_path}"'
    return buffer[:at] + "@" + token + " "

MAX_PASTE_LINES = 50
MAX_PASTE_CHARS = 4000
MAX_BUFFER_CHARS = 8000
MAX_BUFFER_LINES = 100

def _clip_paste(paste):
    text = (paste or "").replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    text = "\n".join(text.split("\n")[:MAX_PASTE_LINES])
    return text[:MAX_PASTE_CHARS]

MENTION_COLOR = "\x1b[94m"
MENTION_RESET = "\x1b[0m"

def _highlight_mentions(buffer):
    if is_no_color():
        return buffer or ""

    from hazzel.mentions import MENTION_RE, TRAILING_PUNCT

    bang = (buffer or "").startswith("!")
    body = (buffer or "")[1:] if bang else (buffer or "")
    parts = []
    pos = 0
    for match in MENTION_RE.finditer(body):
        if match.start() > pos:
            parts.append(body[pos:match.start()])
        token = match.group(0)
        tail = ""
        while token and token[-1] in TRAILING_PUNCT:
            tail = token[-1] + tail
            token = token[:-1]
        if token == "@":
            parts.append(token)
        else:
            parts.append(f"{MENTION_COLOR}{token}{MENTION_RESET}")
        if tail:
            parts.append(tail)
        pos = match.end()
    parts.append(body[pos:])
    out = "".join(parts)
    if bang:
        return "\x1b[1m\x1b[97m!\x1b[0m" + out
    return out

def _filter_slash_commands(query):
    q = (query or "").lower()
    if not q.startswith("/"):
        return []
    prefixed = [c for c in SLASH_COMMANDS if c["name"].startswith(q)]
    if prefixed:
        return prefixed
    return [c for c in SLASH_COMMANDS if q.lstrip("/").lstrip() in c["name"]]

def _win_redraw(buffer):
    sys.stdout.write("\r\x1b[K❯ " + (buffer or ""))
    sys.stdout.flush()

def _win_input(prefill=""):
    try:
        import msvcrt
    except ImportError:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            raise
        rule()
        _st.console.print(f"❯ {line}")
        rule()
        _st.console.print()
        return line
    buffer = (prefill or "")[:MAX_BUFFER_CHARS]
    _win_redraw(buffer)
    while True:
        try:
            ch = msvcrt.getwch()
        except (OSError, ValueError, KeyboardInterrupt):
            raise KeyboardInterrupt
        if ch in ("\r", "\n"):
            break
        if ch == "\x03":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            raise KeyboardInterrupt
        if ch == "\x1a":
            sys.stdout.write("\r\n")
            sys.stdout.flush()
            raise EOFError
        if ch in ("\x00", "\xe0"):
            try:
                msvcrt.getwch()
            except (OSError, ValueError, KeyboardInterrupt):
                pass
            continue
        if ch == "\x1b":
            buffer = ""
            _win_redraw(buffer)
            continue
        if ch == "\x15":
            buffer = ""
            _win_redraw(buffer)
            continue
        if ch in ("\x08", "\x7f"):
            if buffer:
                buffer = buffer[:-1]
                _win_redraw(buffer)
            continue
        if ch and (ch.isprintable() or ch in (" ", "\t")) and len(buffer) < MAX_BUFFER_CHARS:
            buffer += ch
            _win_redraw(buffer)
    sys.stdout.write("\r\n")
    sys.stdout.flush()
    rule()
    _st.console.print(f"❯ {buffer}")
    rule()
    _st.console.print()
    return buffer

def get_input(messages=None, prefill=""):
    from hazzel import wincompat

    if not sys.stdin.isatty():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            raise
        rule()
        _st.console.print(f"❯ {line}")
        rule()
        _st.console.print()
        return line
    if wincompat.is_windows():
        return _win_input(prefill or "")
    import termios
    import tty
    import select

    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except OSError:
        _st.console.print("❯ ", style="bold", end="")
        try:
            return input()
        except (EOFError, KeyboardInterrupt):
            raise

    buffer = prefill or ""
    selected = 0
    rendered_nlines = 0
    rendered_lines = 0
    m_selected = 0
    m_last_query = None
    m_dismissed = None
    m_cands = []
    m_total = 0
    try:
        from hazzel import config as _cfg0

        try:
            _static_mid = _cfg0.get_current_model().split("/")[-1].lower()
        except OSError:
            _static_mid = ""
        try:
            _static_plan_bit = " · plan" if _cfg0.is_plan_enabled() else " · build"
            _static_think_bit = " · think" if _cfg0.is_think_enabled() else ""
            _static_goal = _cfg0.get_goal() or {}
            _static_gtext = (_static_goal.get("objective") or "").strip()
            if len(_static_gtext) > 28:
                _static_gtext = _static_gtext[:28] + "…"
            _static_goal_bit = f" · ⚑ {_static_gtext}" if _static_gtext else ""
        except Exception:
            _static_plan_bit = ""
            _static_goal_bit = ""
    except Exception:
        _static_mid = ""
        _static_plan_bit = ""
        _static_think_bit = ""
        _static_goal_bit = ""
    try:
        from hazzel import agent as _agent0

        _used0, _window0 = _agent0.context_usage(messages)
        from .panels import format_context_meter as _panels_format_meter
        _static_tok = _panels_format_meter(_used0, _window0)
        try:
            from hazzel.pricing import format_usd as _fmt_usd
            from hazzel.tokens import format_count as _fmt_count
            _su = _agent0.get_session_usage() or {}
            _sess_bits = ""
            if _su.get("calls"):
                _stotal = (_su.get("input") or 0) + (_su.get("output") or 0)
                _scost = _su.get("cost")
                if _scost is None and _su.get("unknown"):
                    _sess_bits = f"{_fmt_count(_stotal)} · unpriced"
                else:
                    _sess_bits = f"{_fmt_count(_stotal)} · {_fmt_usd(_scost)}"
                    if _su.get("unknown"):
                        _sess_bits += " +unpriced"
                if _su.get("estimated"):
                    _sess_bits += " ~est"
            _static_sess = _sess_bits
        except Exception:
            _static_sess = ""
    except Exception:
        _static_tok = ""
        _static_sess = ""
    try:
        tty.setraw(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.write("\x1b[?25h\x1b[?12h")
        sys.stdout.flush()
        while True:
            filtered = []
            if buffer.startswith("/"):
                filtered = _filter_slash_commands(buffer)
                if selected >= len(filtered):
                    selected = 0
            else:
                filtered = []
                selected = 0

            mention = None if buffer.startswith("/") else _active_mention(buffer)
            if mention is not None and mention[1] == m_dismissed:
                mention = None
            if mention is None:
                m_cands = []
                m_total = 0
                m_last_query = None
            elif mention[1] != m_last_query:
                m_selected = 0
                m_last_query = mention[1]
                m_cands, m_total = _mention_candidates(mention[1])

            bar = "\x1b[2m" + ("─" * _hw()) + "\x1b[0m"
            rst = "\x1b[0m"
            mid = _static_mid
            tok = _static_tok
            lines = []
            lines.append(bar)
            hbuf = _highlight_mentions(buffer)
            buf_rows = hbuf.split("\n")
            if filtered:
                prompt = f"\x1b[1m❯\x1b[0m {buf_rows[0]}"
            else:
                prompt = f"\x1b[1m❯\x1b[0m {buf_rows[0]}\x1b[5m\x1b[7m \x1b[0m"
            lines.append(prompt)
            for extra in buf_rows[1:]:
                lines.append(f"  {extra}")
            if m_cands:
                width = _hw()
                for i, cand in enumerate(m_cands):
                    disp = cand if len(cand) <= width - 6 else "…" + cand[-(width - 7):]
                    if i == m_selected:
                        lines.append(f"  \x1b[1m\x1b[97m\u276f {disp}\x1b[0m")
                    else:
                        lines.append(f"    \x1b[2m{disp}\x1b[0m")
                if m_total > len(m_cands):
                    lines.append(f"  \x1b[2m+{m_total - len(m_cands)} more — keep typing to narrow\x1b[0m")
            elif filtered:
                width = max([len(c["name"]) for c in filtered] + [8])
                total = len(filtered)
                visible = 5
                start = max(0, min(selected - visible // 2, total - visible))
                end = min(total, start + visible)
                if end - start < visible:
                    start = max(0, end - visible)
                for i in range(start, end):
                    c = filtered[i]
                    name = c["name"].ljust(width)
                    desc = c["desc"]
                    if i == selected:
                        lines.append(f"  \x1b[1m\x1b[32m\u276f\x1b[0m \x1b[1m\x1b[97m{name}\x1b[0m  \x1b[2m{desc}\x1b[0m")
                    else:
                        lines.append(f"    \x1b[2m\x1b[37m{name}\x1b[0m  \x1b[2m{desc}\x1b[0m")
                lines.append(f"  \x1b[2m({selected + 1}/{total})\x1b[0m")
            lines.append(bar)
            _plan_bit = _static_plan_bit
            _goal_bit = _static_goal_bit
            _think_bit = _static_think_bit
            try:
                _sess_bit = f" · {_static_sess}" if _static_sess else ""
            except NameError:
                _sess_bit = ""
            if tok:
                lines.append(f"  \x1b[2m{mid} · {tok}{_sess_bit}{_plan_bit}{_think_bit}{_goal_bit} · @ tag · ! bash · /exit{rst}")
            else:
                lines.append(f"  \x1b[2m{mid}{_sess_bit}{_plan_bit}{_think_bit}{_goal_bit} · @ tag · ! bash · /exit{rst}")

            nlines = _visual_rows(lines)
            out = "\r\n".join(lines)
            if rendered_lines == 0:
                sys.stdout.write(out)
            else:
                if rendered_nlines > 0:
                    sys.stdout.write(f"\x1b[{rendered_nlines}A")
                sys.stdout.write("\r\x1b[J")
                sys.stdout.write(out)
            if filtered:
                sys.stdout.write("\x1b[?25l")
            else:
                sys.stdout.write("\x1b[?25l")
            sys.stdout.flush()
            rendered_nlines = nlines
            rendered_lines = len(lines)

            ch = _read_key(fd)
            if ch == "\x03":
                buffer = ""
                selected = 0
                m_selected = 0
                m_dismissed = None
                continue
            if ch == "\x04":
                raise EOFError
            if ch == "\x16":
                paste = ""
                sys.stdout.write("\x1b[?2004l")
                sys.stdout.flush()
                while True:
                    if select.select([fd], [], [], 0.05)[0]:
                        pc = _read_key(fd)
                        if not pc:
                            break
                        if pc in ("\x03", "\x04"):
                            buffer = ""
                            selected = 0
                            break
                        if pc in ("\r", "\n"):
                            paste += "\n"
                        elif pc.isprintable() or pc in (" ", "\t"):
                            paste += pc
                        else:
                            break
                    else:
                        break
                sys.stdout.write("\x1b[?2004h")
                sys.stdout.flush()
                if paste:
                    buffer = (buffer + _clip_paste(paste))[:MAX_BUFFER_CHARS]
                    if buffer.startswith("/"):
                        selected = 0
                continue
            if ch == "\x1b":
                if select.select([fd], [], [], 0.04)[0]:
                    seq = ""
                    for _ in range(5):
                        if select.select([fd], [], [], 0.02)[0]:
                            seq += _read_key(fd)
                        else:
                            break
                    if seq == "[200~":
                        paste = ""
                        while True:
                            if select.select([fd], [], [], 0.05)[0]:
                                pc = _read_key(fd)
                                if not pc:
                                    break
                                seq2 = pc
                                if seq2 == "\x1b":
                                    if select.select([fd], [], [], 0.02)[0]:
                                        tmp = ""
                                        for _ in range(5):
                                            if select.select([fd], [], [], 0.02)[0]:
                                                tmp += _read_key(fd)
                                            else:
                                                break
                                        if tmp == "[201~":
                                            break
                                        paste += seq2 + tmp
                                    else:
                                        paste += seq2
                                else:
                                    paste += seq2
                            else:
                                break
                        paste = _clip_paste(paste)
                        if paste.strip():
                            buffer = (buffer + paste)[:MAX_BUFFER_CHARS]
                            if buffer.startswith("/"):
                                selected = 0
                        continue
                    if seq.startswith("[") or seq.startswith("O"):
                        ch3 = seq[-1] if seq else ""
                        if ch3 == "A":
                            if m_cands:
                                m_selected = (m_selected - 1) % len(m_cands)
                            elif filtered:
                                selected = (selected - 1) % len(filtered)
                            continue
                        if ch3 == "B":
                            if m_cands:
                                m_selected = (m_selected + 1) % len(m_cands)
                            elif filtered:
                                selected = (selected + 1) % len(filtered)
                            continue
                        if ch3 in ("C", "D", "H", "F"):
                            continue
                    if seq == "" or seq == "\x1b":
                        if m_cands:
                            mention_now = _active_mention(buffer)
                            m_dismissed = mention_now[1] if mention_now else None
                            m_cands = []
                        else:
                            buffer = ""
                            selected = 0
                        continue
                    ch2 = seq[0] if seq else ""
                    if ch2 == "\x1b":
                        if m_cands:
                            mention_now = _active_mention(buffer)
                            m_dismissed = mention_now[1] if mention_now else None
                            m_cands = []
                        else:
                            buffer = ""
                            selected = 0
                        continue
                else:
                    if m_cands:
                        mention_now = _active_mention(buffer)
                        m_dismissed = mention_now[1] if mention_now else None
                        m_cands = []
                    else:
                        buffer = ""
                        selected = 0
                    continue
            elif ch == "\n":
                if buffer.count("\n") < MAX_BUFFER_LINES and len(buffer) < MAX_BUFFER_CHARS:
                    buffer += "\n"
                    m_last_query = None
                continue
            elif ch == "\r":
                if m_cands:
                    buffer = _accept_mention(buffer, m_cands[m_selected])
                    m_selected = 0
                    m_dismissed = None
                    continue
                if buffer.startswith("/") and filtered:
                    buffer = filtered[selected]["name"]
                cmd = buffer.strip().lower()
                is_slash = cmd in [c["name"] for c in SLASH_COMMANDS] or cmd in ["clear", "help", "exit", "quit", "c", "h", "q"] or cmd in ["/c", "/h", "/q", ":q", ":quit"]
                if is_slash:
                    if rendered_lines > 1:
                        sys.stdout.write(f"\x1b[{rendered_nlines}A")
                        sys.stdout.write("\x1b[2K\r\x1b[J")
                    else:
                        sys.stdout.write("\x1b[2K\r\x1b[J")
                else:
                    hbuf = _highlight_mentions(buffer)
                    if rendered_lines > 1:
                        sys.stdout.write(f"\x1b[{rendered_nlines}A")
                        sys.stdout.write("\x1b[2K\r")
                        sys.stdout.write(_rule_ansi() + "\r\n")
                        sys.stdout.write(f"\x1b[1m❯\x1b[0m {hbuf}\x1b[J\r\n")
                        sys.stdout.write(_rule_ansi() + "\r\n")
                    else:
                        sys.stdout.write(_rule_ansi() + "\r\n")
                        sys.stdout.write(f"\x1b[1m❯\x1b[0m {hbuf}\r\n")
                        sys.stdout.write(_rule_ansi() + "\r\n")
                break
            elif ch in ("\x7f", "\x08"):
                if buffer:
                    buffer = buffer[:-1]
                    if buffer.startswith("/"):
                        selected = 0
                continue
            elif ch == "\x15":
                buffer = ""
                selected = 0
                continue
            elif ch == "\t" or ch == "\x09":
                if m_cands:
                    buffer = _accept_mention(buffer, m_cands[m_selected])
                    m_selected = 0
                    m_dismissed = None
                elif filtered:
                    buffer = filtered[selected]["name"]
                    selected = 0
                continue
            elif ch and ch.isprintable():
                buffer += ch
                if buffer.startswith("/"):
                    selected = 0
                continue
    except (KeyboardInterrupt, EOFError):
        try:
            sys.stdout.write("\r\n")
        except OSError:
            pass
        raise
    finally:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except OSError:
            pass
        sys.stdout.write("\x1b[?2004l")
        sys.stdout.write("\x1b[?25h\x1b[?12h")
        sys.stdout.flush()
    if buffer.startswith("/") and buffer in [c["name"] for c in SLASH_COMMANDS]:
        return buffer
    if buffer.startswith("/") and filtered:
        pass
    return buffer

MAX_DIFF_DISPLAY_LINES = 500

VIEW_MAX_LINES = 2000

def _is_tty():
    return sys.stdin.isatty() and sys.stdout.isatty()

def _read_key(fd):
    try:
        data = os.read(fd, 1)
        if not data:
            return ""
        return data.decode("utf-8", errors="ignore")
    except OSError:
        return ""
