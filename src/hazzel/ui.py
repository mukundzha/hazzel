import os
import re
import sys
import time

from rich.console import Console
from rich.containers import Renderables
from rich.text import Text

console = Console()

_loader = None

HAZZEL_COLOR = "#ec8500"
USER_COLOR = "#8ab4f8"

SUCCESS_COLOR = "#8fb08f"
ERROR_COLOR = "#c97676"

DIM_COLOR = "dim"


def show_welcome(model, project_root):
    console.print()
    _show_header(model, project_root)
    console.print()


def _hw():
    try:
        import shutil

        return max(20, int(shutil.get_terminal_size(fallback=(80, 24)).columns))
    except Exception:
        pass
    try:
        return max(20, int(console.width))
    except Exception:
        return 80


def rule():
    console.print(Text("─" * _hw(), style="dim"))


def _rule_ansi():
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
    console.print(title)
    console.print(Text(_short_path(project_root), style=DIM_COLOR))


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
    {"name": "/jobs", "desc": "background jobs list/poll/kill"},
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
    from . import config

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
        console.print(f"❯ {line}")
        rule()
        console.print()
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
    console.print(f"❯ {buffer}")
    rule()
    console.print()
    return buffer


def get_input(messages=None, prefill=""):
    from . import wincompat

    if not sys.stdin.isatty():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            raise
        rule()
        console.print(f"❯ {line}")
        rule()
        console.print()
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
        console.print("❯ ", style="bold", end="")
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
        from . import config as _cfg0

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
        _static_tok = format_context_meter(_used0, _window0)
        try:
            from .pricing import format_usd as _fmt_usd
            from .tokens import format_count as _fmt_count
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


def _live_body(text):
    from rich.spinner import Spinner  # deferred: only needed when loader shows

    parts = []
    if text:
        label = Text(text, style="dim")
        label.append("  ·  ctrl+c to cancel", style="dim italic")
        parts.append(Spinner("dots", text=label))
    parts.extend(_tool_rows)
    if not parts:
        parts.append(Text(""))
    return Renderables(parts)


def begin_turn(text="Working…"):
    global _turn_started
    _tool_rows.clear()
    _turn_started = time.monotonic()
    show_loader(text)


def show_loader(text="Working…"):
    global _loader
    if _print_mode:
        return
    if _loader is not None:
        _loader.update(_live_body(text))
        return
    from rich.live import Live  # deferred: only needed when loader shows

    try:
        _loader = Live(
            _live_body(text),
            console=console,
            refresh_per_second=12,
            transient=True,
        )
        _loader.start()
    except OSError:
        pass


def hide_loader():
    global _loader
    if _loader is None:
        return
    try:
        _loader.stop()
    except OSError:
        pass
    finally:
        _loader = None


def _pause_loader():
    was_active = _loader is not None
    if was_active:
        hide_loader()
    return was_active


def _resume_loader(was_active, text="Working…"):
    if was_active:
        show_loader(text)


_stream_buffer = ""
_stream_started = None
_stream_first_at = None
_stream_tokens = 0
_stream_last_paint = 0.0
_reason_buffer: list[str] = []
_thinking_streamed = False
_thinking_was_live = False


def begin_stream():
    global _stream_buffer, _stream_started, _stream_first_at, _stream_tokens, _stream_last_paint
    global _reason_buffer, _thinking_streamed, _thinking_was_live
    _stream_buffer = ""
    _stream_started = time.monotonic()
    _stream_first_at = None
    _stream_tokens = 0
    _stream_last_paint = 0.0
    _reason_buffer = []
    _thinking_streamed = False
    _thinking_was_live = False


def push_reasoning_token(token):
    global _reason_buffer, _thinking_streamed, _thinking_was_live, _stream_last_paint
    if not token:
        return
    _reason_buffer.append(token)
    _thinking_streamed = True
    _thinking_was_live = True
    now = time.monotonic()
    if _loader is None:
        return
    if now - _stream_last_paint < 0.1:
        return
    _stream_last_paint = now
    text = _render_reasoning("".join(_reason_buffer))
    try:
        _loader.update(_live_reasoning(text))
    except OSError:
        pass


def _live_reasoning(text):
    from rich.spinner import Spinner  # deferred: only needed when reasoning is live

    spinner = Spinner("dots", text=Text("thinking", style="dim italic"))
    if not text:
        return Renderables([spinner])
    return Renderables([spinner, Text(text, style="dim")])


def _render_reasoning(text, limit=600):
    text = text.strip()
    if not text:
        return ""
    rendered = " ".join(text.split())
    if len(rendered) > limit:
        rendered = rendered[: limit - 1].rstrip() + "…"
    return rendered


def was_thinking_streamed():
    return _thinking_was_live


def push_stream_token(token):
    global _stream_buffer, _stream_first_at, _stream_tokens, _stream_last_paint
    global _thinking_streamed
    if not token:
        return
    now = time.monotonic()
    if _stream_first_at is None:
        _stream_first_at = now
    _stream_buffer += token
    _stream_tokens += 1
    if _thinking_streamed:
        _thinking_streamed = False
        _reason_buffer[:] = []
        if _loader is not None:
            try:
                _loader.update(_live_body(f"Working… · ttft {now - (_stream_started or now):.1f}s · {_stream_tokens} tokens"))
                return
            except OSError:
                pass
    if _loader is None:
        return
    if now - _stream_last_paint < 0.4 and _stream_tokens % 25:
        return
    _stream_last_paint = now
    try:
        ttft = _stream_first_at - (_stream_started or _stream_first_at)
        _loader.update(_live_body(f"Working… · ttft {ttft:.1f}s · {_stream_tokens} tokens"))
    except OSError:
        pass


def stream_stats():
    start = _stream_started or time.monotonic()
    first = _stream_first_at
    return {
        "tokens": _stream_tokens,
        "ttft": ((first - start) if first else 0.0),
        "elapsed": time.monotonic() - start,
    }


def end_stream():
    global _stream_buffer
    buf = _stream_buffer
    _stream_buffer = ""
    return buf


_tool_rows: list[Text] = []
_turn_started = None


def end_turn():
    hide_loader()


_quiet = False


def set_quiet(value=True):
    global _quiet
    _quiet = bool(value)
    return _quiet


def is_quiet():
    return _quiet


# Print (non-interactive) mode: stdout carries only the final answer, so all
# progress UI stays silent. _auto_approve mirrors `hazzel -p -y`.
_print_mode = False
_auto_approve = False


def set_print_mode(value=True):
    global _print_mode
    _print_mode = bool(value)
    return _print_mode


def is_print_mode():
    return _print_mode


def set_auto_approve(value=True):
    global _auto_approve
    _auto_approve = bool(value)
    return _auto_approve


def show_turn_from_trace(user_command, trace, summary):
    return None


def show_turn_card(user_command, tool_rows, summary_lines, model="Hazzel 1.3.2", root="~/hazzel"):
    return None


def show_hazzel_message(message):
    hide_loader()
    if not message or not message.strip():
        return
    # Deferred import: formatter pulls rich.syntax + pygments (~30ms),
    # only needed once the first assistant message is actually rendered.
    from .formatter import print_response

    print_response(console, message)


def show_reasoning(reasoning):
    global _thinking_was_live
    hide_loader()
    if _thinking_was_live:
        _thinking_was_live = False
        return
    text = (reasoning or "").strip()
    if not text:
        return
    console.print(Text(text, style="dim"))
    console.print()


def _short_detail(detail: str, limit: int = 62) -> str:
    if not detail:
        return ""
    d = detail.strip()
    if len(d) > limit:
        return d[: limit - 1].rstrip() + "…"
    return d


def _relativize_detail(detail):
    try:
        from pathlib import Path as _Path

        from . import config as _config

        root = _config.PROJECT_ROOT.resolve()
    except Exception:
        return detail
    parts = []
    for tok in str(detail or "").split():
        raw = tok.strip("'\"")
        try:
            candidate = _Path(raw)
        except Exception:
            parts.append(tok)
            continue
        if not candidate.is_absolute():
            parts.append(tok)
            continue
        try:
            parts.append(str(candidate.resolve().relative_to(root)))
        except ValueError:
            parts.append(tok)
        except OSError:
            parts.append(tok)
    return " ".join(parts)


def format_context_plain(used, window):
    try:
        used = max(0, int(used or 0))
    except (TypeError, ValueError):
        used = 0
    try:
        window = int(window or 0)
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        window = 131072
    if window >= 1_000_000:
        short = f"{window / 1_000_000:.1f}M"
    elif window >= 1000:
        short = f"{window // 1000}k"
    else:
        short = str(window)
    return f"{used / window * 100:.1f}%/{short} (auto)"


def format_context_meter(used, window):
    try:
        used = max(0, int(used or 0))
    except (TypeError, ValueError):
        used = 0
    try:
        window = int(window or 0)
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        window = 131072
    pct = used / window * 100
    if pct < 50:
        color = "\x1b[32m"
    elif pct < 80:
        color = "\x1b[33m"
    else:
        color = "\x1b[31m"
    return f"\x1b[1m{color}{format_context_plain(used, window)}\x1b[0m\x1b[2m"


def _format_elapsed(seconds):
    if seconds is None:
        return ""
    try:
        seconds = float(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds < 0:
        return ""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    return f"{seconds:.1f}s"


_PREVIEW_MAX_LINES = 8
_PREVIEW_MAX_CHARS = 480


def _format_result_preview(result, max_lines=_PREVIEW_MAX_LINES, max_chars=_PREVIEW_MAX_CHARS):
    if not result:
        return "(no output)"
    text = str(result)
    lines = text.splitlines()
    # Drop trailing blanks so the suffix count is meaningful.
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return "(no output)"

    if len(lines) <= max_lines:
        head = "\n".join(lines)
        if len(head) <= max_chars:
            return head

    # Truncate by line count, then fold overly long lines so the preview
    # never blows out the terminal width horizontally.
    head_lines = []
    for line in lines[:max_lines]:
        line = line[: max_chars // 2]
        head_lines.append(line)
    out = "\n".join(head_lines)
    remaining = len(lines) - len(head_lines)
    return out + f"\n…{remaining} more lines"


def show_tool(tool_name, detail="", success=True, exit_code=None, cached=False,
              elapsed=None, result=None):
    if _quiet:
        return
    icon = "●" if success else "!"
    limit = 45 if exit_code is not None else 62
    text = Text()
    text.append("  ", style=DIM_COLOR)
    if cached:
        text.append(f"{icon} ", style=DIM_COLOR)
        text.append(str(tool_name).ljust(12), style=DIM_COLOR)
    else:
        text.append(f"{icon} ", style=HAZZEL_COLOR if success else ERROR_COLOR)
        text.append(str(tool_name).ljust(12), style="white" if success else ERROR_COLOR)
    short = _short_detail(_relativize_detail(detail), limit=limit)
    if short:
        text.append(f" {short}", style="#9aa4b2")
    meta = _format_elapsed(elapsed)
    if cached:
        meta = (meta + " · " if meta else "") + "cached"
    if meta:
        text.append(f"  · {meta}", style=DIM_COLOR)
    if exit_code is not None and not success:
        text.append(f"  · exit {exit_code}", style=DIM_COLOR)

    preview_rows = None
    if result is not None and not _quiet:
        preview = _format_result_preview(result)
        if preview:
            preview_rows = _split_preview_rows(preview)

    if _loader is not None:
        _tool_rows.append(text)
        while len(_tool_rows) > _MAX_TOOL_ROWS:
            _tool_rows.pop(0)
        _loader.update(_live_body(None))
    else:
        console.print(text)

    if preview_rows is not None:
        for row in preview_rows:
            if _loader is not None:
                _tool_rows.append(row)
            else:
                console.print(row)
        if _loader is not None:
            while len(_tool_rows) > _MAX_TOOL_ROWS:
                _tool_rows.pop(0)
            _loader.update(_live_body(None))


def _split_preview_rows(preview):
    rows = []
    for i, line in enumerate(preview.splitlines()):
        t = Text()
        if i == 0:
            t.append("  " + chr(0x23BF) + " ", style="#7d8799")
        else:
            t.append("  " + chr(0x2502) + " ", style="#5b6472")
        t.append(line, style="#c5cdd9")
        rows.append(t)
    return rows


def show_user_command(command):
    text = Text()
    text.append("❯ ", style="dim")
    text.append(command.strip(), style="white")
    console.print(text)


def show_history(messages):
    items = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        if msg.get("role") not in ("user", "assistant"):
            continue
        content = msg.get("content") or ""
        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict) and isinstance(part.get("text"), str):
                    parts.append(part["text"])
            content = "\n".join(parts)
        if not isinstance(content, str):
            continue
        content = content.strip()
        if not content:
            continue
        items.append((msg["role"], content))
    if not items:
        return
    if len(items) >= 2 and items[-2][0] == "user" and items[-1][0] == "assistant":
        items = items[-2:]
    else:
        items = items[-1:]
    for role, content in items:
        if role == "user":
            rule()
            text = Text()
            text.append("❯ ", style="bold")
            text.append(content, style="white")
            console.print(text)
            rule()
            console.print()
        else:
            show_hazzel_message(content)
            console.print()


def show_error(message):
    text = Text()
    text.append("  ! ", style=ERROR_COLOR)
    text.append(message, style=ERROR_COLOR)
    console.print(text)


def confirm(prompt):
    if _print_mode:
        return _auto_approve
    was_active = _pause_loader()
    try:
        answer = input(f"\n{prompt} [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return False
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip().lower()
    return clean in {"y", "yes"}


MAX_DIFF_DISPLAY_LINES = 500


def show_diff(diff):
    if _print_mode:
        return
    was_active = _pause_loader()
    try:
        rule()
        lines = (diff or "").splitlines()
        for line in lines[:MAX_DIFF_DISPLAY_LINES]:
            if line.startswith("@@"):
                console.print(Text(f"  {line}", style=USER_COLOR))
            elif line.startswith("+") and not line.startswith("+++"):
                console.print(Text(f"  {line}", style=SUCCESS_COLOR))
            elif line.startswith("-") and not line.startswith("---"):
                console.print(Text(f"  {line}", style=ERROR_COLOR))
            else:
                console.print(Text(f"  {line}", style=DIM_COLOR))
        if len(lines) > MAX_DIFF_DISPLAY_LINES:
            console.print(Text(f"  …{len(lines) - MAX_DIFF_DISPLAY_LINES} more lines capped for display", style=DIM_COLOR))
        rule()
    finally:
        _resume_loader(was_active)


def show_git_status(branch, body):
    rule()
    title = Text()
    title.append("  Git status", style="bold white")
    title.append(f"  ·  {branch or 'HEAD'}", style=DIM_COLOR)
    console.print(title)
    if not body or body.strip() in ("(clean)", "Clean."):
        console.print(Text("  Clean — nothing to commit.", style=SUCCESS_COLOR))
    else:
        from rich.table import Table  # deferred: only needed when git status has entries

        table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 1, 0, 0))
        table.add_column(overflow="fold", width=4)
        table.add_column(overflow="fold")
        for line in body.splitlines()[:40]:
            if line.startswith("## "):
                continue
            code = line[:2].strip() or "·"
            rest = line[3:] if len(line) > 3 else line
            color = SUCCESS_COLOR if "??" in line[:2] else USER_COLOR if line[:1].strip() else HAZZEL_COLOR
            table.add_row(Text(code, style=f"bold {color}"), Text(rest.strip(), style="white"))
        console.print(table)
        extra = len(body.splitlines()) - 40
        if extra > 0:
            console.print(Text(f"  …{extra} more", style=DIM_COLOR))
    rule()


def show_git_diff(body, staged=False):
    # Legacy single-shot diff view; the /diff flow uses the file browser
    # (show_git_file_list + show_git_file_diff) instead.
    rule()
    title = Text()
    title.append("  Git diff", style="bold white")
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    console.print(title)
    if not body or body.strip() in ("No changes.", "(clean)"):
        console.print(Text("  No changes.", style=DIM_COLOR))
        rule()
        return
    added, deleted = _count_diff_marks(body)
    if added or deleted:
        console.print(Text(f"  +{added} −{deleted}", style=DIM_COLOR))
    show_diff(body[:12000])
    rule()


_GIT_STATUS_ICONS = {
    "M": ("M", USER_COLOR),
    "A": ("A", SUCCESS_COLOR),
    "?": ("+", SUCCESS_COLOR),
    "D": ("D", ERROR_COLOR),
    "R": ("R", HAZZEL_COLOR),
}


def _count_diff_marks(body):
    added = deleted = 0
    for line in (body or "").splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted


def show_git_file_list(files, staged=False, branch=""):
    total_add = sum(f.get("added", 0) for f in files)
    total_del = sum(f.get("deleted", 0) for f in files)
    rule()
    title = Text()
    title.append("  Changed files", style="bold white")
    title.append(f"  ·  {len(files)}", style=DIM_COLOR)
    if files:
        title.append(f"  ·  +{total_add} −{total_del}", style=SUCCESS_COLOR)
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    if branch:
        title.append(f"  ·  {branch}", style=DIM_COLOR)
    console.print(title)
    if not files:
        console.print(Text("  No changes.", style=DIM_COLOR))
        rule()
        return
    for i, f in enumerate(files, 1):
        letter, color = _GIT_STATUS_ICONS.get(f.get("status", "M"), ("M", USER_COLOR))
        row = Text()
        row.append(f"{i:>3}  ", style=DIM_COLOR)
        row.append(letter, style=f"bold {color}")
        row.append(f"  {_short_detail(f['path'], limit=64)}", style="white")
        row.append(f"  +{f.get('added', 0)} −{f.get('deleted', 0)}", style=DIM_COLOR)
        console.print(row)
    console.print(Text(f"  Open [1-{len(files)}] · q close", style=DIM_COLOR))
    rule()


def show_git_file_diff(path, body, staged=False, position=""):
    title = Text()
    title.append(f"  ❯ {position}{path}" if position else f"  ❯ {path}", style="bold white")
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    added, deleted = _count_diff_marks(body)
    if added or deleted:
        title.append(f"  ·  +{added} −{deleted}", style=SUCCESS_COLOR)
    console.print(title)
    show_diff(body)
    console.print()


def prompt_diff_selection(count):
    was_active = _pause_loader()
    try:
        answer = input(f"  Open file [1-{count} / q]: ")
    except (EOFError, KeyboardInterrupt):
        return None
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip().lower()
    if not clean or clean in ("q", "quit", "exit", "n"):
        return None
    try:
        n = int(clean)
        if 1 <= n <= count:
            return n - 1
    except ValueError:
        pass
    return "invalid"


def show_git_commit(result):
    text = Text()
    if "cancelled" in result.lower() or "nothing" in result.lower():
        text.append("  ○ ", style=f"bold {DIM_COLOR}")
        text.append(result, style="dim")
    else:
        text.append("  ✓ ", style=f"bold {SUCCESS_COLOR}")
        text.append(result, style="bold white")
    console.print(text)
    console.print()


def show_review(markdown, files, staged=False, fallback=False):
    total_add = sum(f.get("added", 0) for f in files or [])
    total_del = sum(f.get("deleted", 0) for f in files or [])
    rule()
    title = Text()
    title.append("  Diff review", style="bold white")
    title.append(f"  ·  {len(files)} file(s)", style=DIM_COLOR)
    if files:
        title.append(f"  ·  +{total_add} −{total_del}", style=SUCCESS_COLOR)
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    if fallback:
        title.append("  ·  offline heuristics", style=DIM_COLOR)
    console.print(title)
    console.print()
    if markdown and markdown.strip():
        from .formatter import print_response

        print_response(console, markdown)
    console.print(Text("  Read-only — nothing changed. /commit when ready.", style=DIM_COLOR))
    rule()


def show_git_suggest(message, fallback=False):
    rule()
    title = Text()
    title.append("  Suggested message", style="bold white")
    if fallback:
        title.append("  ·  offline draft", style=DIM_COLOR)
    console.print(title)
    row = Text()
    row.append("  ❯ ", style=f"bold {HAZZEL_COLOR}")
    row.append(message, style="bold white")
    console.print(row)
    console.print(Text("  [y] commit · [e] edit · [n] cancel", style=DIM_COLOR))
    rule()


def prompt_suggest_action():
    was_active = _pause_loader()
    try:
        answer = input("  Accept? [y/e/n]: ")
    except (EOFError, KeyboardInterrupt):
        return "n"
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip().lower()
    if clean in ("y", "yes", ""):
        return "y"
    if clean in ("e", "edit"):
        return "e"
    return "n"


def prompt_suggest_edit(initial):
    was_active = _pause_loader()
    try:
        answer = input(f"  Message [{initial}]: ")
    except (EOFError, KeyboardInterrupt):
        return None
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip()
    return clean or initial


_LOG_TYPE_COLORS = {
    "feat": SUCCESS_COLOR,
    "fix": ERROR_COLOR,
    "perf": "yellow",
    "docs": USER_COLOR,
    "refactor": USER_COLOR,
    "test": SUCCESS_COLOR,
    "chore": DIM_COLOR,
    "build": DIM_COLOR,
    "ci": DIM_COLOR,
}

_LOG_LINE_RE = re.compile(r"^([0-9a-f]{4,40})\s+(?:\(([^)]*)\)\s+)?(.*)$")
_LOG_SUBJECT_RE = re.compile(r"^([A-Za-z]+)(\([^)]*\))?(:)\s?(.*)$")


def _style_log_refs(refs):
    row = Text()
    for i, seg in enumerate(refs.split(",")):
        seg = seg.strip()
        if not seg:
            continue
        if i:
            row.append(" · ", style=DIM_COLOR)
        if seg == "HEAD" or seg.startswith("HEAD "):
            row.append(seg.replace("->", "→"), style=f"bold {SUCCESS_COLOR}")
        elif seg.startswith("tag:"):
            row.append(seg, style="yellow")
        else:
            row.append(seg.replace("->", "→"), style="white")
    return row


def _style_log_subject(subject):
    row = Text()
    match = _LOG_SUBJECT_RE.match(subject or "")
    if match:
        color = _LOG_TYPE_COLORS.get(match.group(1).lower(), "white")
        row.append(match.group(1) + (match.group(2) or "") + match.group(3), style=f"bold {color}")
        if match.group(4):
            row.append(" " + match.group(4), style="white")
        return row
    row.append(subject or "(empty message)", style="white")
    return row


def show_git_log(body, branch=""):
    lines = [ln for ln in (body or "").splitlines() if ln.strip()][:20]
    rule()
    head = Text()
    head.append("  Recent commits", style="bold white")
    if branch:
        head.append(f"  ·  {branch}", style=DIM_COLOR)
    if lines:
        head.append(f"  ·  {len(lines)}", style=DIM_COLOR)
    console.print(head)
    if not lines:
        console.print(Text("  No commits yet.", style=DIM_COLOR))
        rule()
        return
    for line in lines:
        match = _LOG_LINE_RE.match(line.strip())
        if not match:
            console.print(Text(f"  {line.strip()}", style="dim"))
            continue
        short, refs, subject = match.group(1), (match.group(2) or "").strip(), match.group(3)
        row = Text()
        row.append("  ", style=DIM_COLOR)
        row.append(short, style=f"bold {USER_COLOR}")
        row.append("  ")
        row.append_text(_style_log_subject(subject))
        console.print(row)
        if refs:
            sub = Text()
            sub.append(" " * (len(short) + 4), style=DIM_COLOR)
            sub.append("└─ ", style=DIM_COLOR)
            sub.append_text(_style_log_refs(refs))
            console.print(sub)
    rule()


VIEW_MAX_LINES = 2000


def show_file_viewer(display_path, body, total_lines, shown_lines):
    if _print_mode:
        return
    end_turn()
    rule()
    console.print(Text(f"  {display_path}  ·  {total_lines} lines", style="dim"))
    for number, line in enumerate(body.splitlines(), 1):
        row = Text()
        row.append(f"{number:6d}  ", style="dim")
        row.append(line[:500])
        console.print(row)
    if shown_lines < total_lines:
        console.print(Text(f"  …{total_lines - shown_lines} more lines capped for display", style="dim"))
    rule()


def show_undo(restored):
    if not restored:
        console.print(Text("  Nothing to undo.", style=DIM_COLOR))
        console.print()
        return
    for key, action in restored:
        text = Text()
        text.append("  ✓ ", style=SUCCESS_COLOR)
        text.append(f"{action} ", style="white")
        text.append(_short_detail(key), style=DIM_COLOR)
        console.print(text)
    console.print()


def prompt_goal_criteria():
    was_active = _pause_loader()
    try:
        answer = input("  Done looks like what? [Enter to skip]: ")
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        _resume_loader(was_active)
    return _ANSI_RE.sub("", answer or "").strip()


def show_model_selected(display_name, provider_display):
    text = Text()
    text.append("  ✓ ", style=SUCCESS_COLOR)
    text.append(display_name, style="white")
    text.append(f" ({provider_display})", style=DIM_COLOR)
    console.print(text)
    console.print()


def show_cleared():
    text = Text()
    text.append("  ○ ", style=DIM_COLOR)
    text.append("Conversation cleared", style="dim")
    console.print(text)
    console.print()


_HELP_INTRO = (
    "Hazzel — inspects, edits, and runs your code, right from your terminal."
)

_HELP_SECTIONS = [
    ("Shortcuts", [
        ("/", "commands · live filter", "Esc", "clear input"),
        ("Tab", "accept highlighted item", "Ctrl+U", "clear input"),
        ("↑/↓", "navigate commands", "Ctrl+V", "paste"),
        ("Ctrl+C", "quit"),
    ]),
    ("Commands", [
        ("/model", "switch model & provider"),
        ("/think", "deeper reasoning on/off"),
        ("/plan", "read-only plan, approve first"),
        ("/goal", "objective + acceptance"),
        ("/help", "this overview"),
        ("/docs", "full usage guide"),
        ("/clear", "reset conversation + usage"),
        ("/summary", "summarize last implementation"),
        ("/export", "save transcript [file.md]"),
        ("/copy", "copy last reply [code]"),
        ("/init", "generate AGENTS.md map"),
        ("/skills", "pick + attach a skill"),
        ("/mcp", "list + use MCP servers"),
        ("/retry", "re-run last message"),
        ("/jobs", "background jobs [id|kill id]"),
        ("/usage", "show token usage"),
        ("/undo", "undo last file change"),
        ("/logout", "clear saved API keys"),
        ("/exit", "quit"),
    ]),
    ("Git", [
        ("/status", "working-tree status"),
        ("/diff", "changed files + full diff [--staged]"),
        ("/review", "read-only review of the uncommitted diff"),
        ("/commit", "suggest message + approval"),
        ("/log", "recent commits"),
    ]),
]


_HELP_FOOT = "Models  ·  Groq · OpenAI · Mistral · Anthropic · Gemini · DeepSeek · OpenRouter · Ollama  —  /model to switch"
_STAR_LINE = "If Hazzel helps, star us: github.com/mukundzha/hazzel"


def _help_table(rows):
    from rich.table import Table  # deferred: only needed when help is shown

    ncols = max((len(row) for row in rows), default=2)
    table = Table(
        show_header=False,
        box=None,
        pad_edge=False,
        padding=(0, 3, 0, 0),
    )
    for _ in range(ncols):
        table.add_column(overflow="fold")
    for row in rows:
        cells = []
        for j in range(ncols):
            cell = row[j] if j < len(row) else ""
            cells.append(Text(cell, style=("white" if j % 2 == 0 else "dim")))
        table.add_row(*cells)
    return table


def show_help():
    _print_help_inline()


def _doc_line(line):
    text = Text()
    for i, part in enumerate(re.split(r"(`[^`]+`)", line)):
        if not part:
            continue
        if part.startswith("`") and part.endswith("`") and len(part) > 2:
            text.append(part[1:-1], style="white")
            continue
        pos = 0
        for m in re.finditer(r"/[a-z]+|@\S+", part):
            if m.start() > pos:
                text.append(part[pos:m.start()], style="dim" if i == 0 and m.start() == 0 else "white")
            tok = m.group(0)
            text.append(tok, style="white" if tok.startswith("/") else USER_COLOR)
            pos = m.end()
        text.append(part[pos:], style="white" if pos else ("dim" if line.startswith("/") else "white"))
    return text


def show_docs():
    from .docs import get_sections

    sections = get_sections()
    rule()
    head = Text()
    head.append("  Hazzel docs", style="white")
    head.append(f"  ·  {len(sections)} sections", style=DIM_COLOR)
    console.print(head)
    rule()
    for i, (title, lines) in enumerate(sections):
        console.print()
        sec = Text()
        sec.append(f"  {i + 1:02d}  ", style=DIM_COLOR)
        sec.append(title, style="white")
        console.print(sec)
        for line in lines:
            row = Text()
            row.append("       ", style=DIM_COLOR)
            row.append_text(_doc_line(line))
            console.print(row)
    console.print()
    rule()


def _print_help_inline():
    console.print()
    console.print(Text(_HELP_INTRO, style="white"))
    for title, rows in _HELP_SECTIONS:
        console.print()
        console.print(Text(title.lower(), style="dim"))
        console.print(_help_table(rows))
    console.print()
    console.print(Text(_HELP_FOOT, style="dim"))
    console.print(Text(f"  {_STAR_LINE}", style="dim"))
    console.print()


def _show_help_tab():
    fd = sys.stdin.fileno()
    try:
        import termios
        import tty
        import select
        old = termios.tcgetattr(fd)
        sys.stdout.write("\x1b[?1049h\x1b[H\x1b[2J\x1b[?25l")
        sys.stdout.flush()
        try:
            tty.setraw(fd)
            attrs = termios.tcgetattr(fd)
            attrs[1] |= termios.OPOST | termios.ONLCR
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIFLUSH)
            console.print()
            console.print(Text(_HELP_INTRO, style="white"))
            for title, rows in _HELP_SECTIONS:
                console.print()
                console.print(Text(title.lower(), style="dim"))
                console.print(_help_table(rows))
            console.print()
            console.print(Text(_HELP_FOOT, style="dim"))
            console.print()
            console.print(Text("esc to cancel", style="dim"))
            console.print()
            sys.stdout.flush()
            while True:
                ch = _read_key(fd)
                if not ch:
                    continue
                if ch in ("\x03", "q", "Q"):
                    break
                if ch == "\x1b":
                    if select.select([fd], [], [], 0.05)[0]:
                        ch2 = _read_key(fd)
                        if ch2 == "\x1b":
                            break
                        if ch2 in ("[", "O"):
                            while select.select([fd], [], [], 0.03)[0]:
                                _read_key(fd)
                    else:
                        break
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except OSError:
                pass
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
    except (OSError, ImportError):
        pass


def show_usage(session, last=None, context=None):
    if sys.stdin.isatty():
        _show_usage_tab(session, last, context)
    else:
        _print_usage_inline(session, last, context)


def _usage_body(session, last=None, context=None):
    from .pricing import format_usd
    from .tokens import format_count
    sent = int(session.get("input") or 0)
    received = int(session.get("output") or 0)
    cached = int(session.get("cached") or 0)
    calls = int(session.get("calls") or 0)
    total = sent + received

    header = Text()
    header.append("usage", style="white")
    header.append("  ·  tokens used this conversation", style="dim")
    yield header
    yield Text("")

    if not calls:
        yield Text("  No usage yet — ask Hazzel to read, edit, or run something.", style="dim")
        return

    hero = Text()
    hero.append("  ", style="dim")
    hero.append(f"{total:,}", style="white")
    hero.append(f"  tokens · {calls} call{'s' if calls != 1 else ''}", style="dim")
    yield hero
    cost_line = Text()
    cost_line.append("  cost  ", style="dim")
    if session.get("unknown"):
        cost_line.append(f"{format_usd(session.get('cost'))} across priced calls", style="white")
        cost_line.append(f" · {session['unknown']} call{'s' if session['unknown'] != 1 else ''} unknown pricing", style="dim")
    else:
        cost_line.append(format_usd(session.get("cost")), style="white")
    yield cost_line
    if context:
        try:
            ctx = Text()
            ctx.append("  context  ", style="dim")
            ctx.append(format_context_plain(context[0], context[1]), style="white")
            yield ctx
        except Exception:
            pass
    yield Text("")

    from rich.table import Table  # deferred: only needed when usage body renders

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim", width=10)
    table.add_column(justify="right", style="white", width=10)
    table.add_column(justify="left", style="dim")

    table.add_row("↑ sent", format_count(sent), "to the model")
    table.add_row("↓ received", format_count(received), "generated back")
    if cached:
        table.add_row("◇ cached", format_count(cached), "reused · cheaper")
    yield table
    if last and last.get("calls"):
        last_total = (last.get("input") or 0) + (last.get("output") or 0)
        suffix = " · estimated" if last.get("estimated") else ""
        last_line = Text()
        last_line.append("  last turn  ", style="dim")
        last_line.append(f"{format_count(last_total)} tokens{suffix}", style="white")
        yield Text("")
        yield last_line
    elif session.get("estimated"):
        yield Text("  ~ estimated, not billed", style="dim")


def _print_usage_inline(session, last=None, context=None):
    console.print()
    for line in _usage_body(session, last, context):
        console.print(line)
    console.print()
    foot = Text()
    foot.append(" esc ", style="reverse")
    foot.append("  dismiss", style="dim")
    console.print(foot)
    console.print()


def _show_usage_tab(session, last=None, context=None):
    fd = sys.stdin.fileno()
    try:
        import termios
        import tty
        import select
        old = termios.tcgetattr(fd)
        sys.stdout.write("\x1b[?1049h\x1b[H\x1b[2J\x1b[?25l")
        sys.stdout.flush()
        try:
            tty.setraw(fd)
            attrs = termios.tcgetattr(fd)
            attrs[1] |= termios.OPOST | termios.ONLCR
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIFLUSH)
            console.print()
            for line in _usage_body(session, last, context):
                console.print(line)
            console.print()
            foot = Text()
            foot.append(" esc ", style="reverse")
            foot.append("  dismiss", style="dim")
            console.print(foot)
            console.print()
            sys.stdout.flush()
            while True:
                ch = _read_key(fd)
                if not ch:
                    continue
                if ch in ("\x03", "q", "Q"):
                    break
                if ch == "\x1b":
                    if select.select([fd], [], [], 0.05)[0]:
                        ch2 = _read_key(fd)
                        if ch2 == "\x1b":
                            break
                        if ch2 in ("[", "O"):
                            while select.select([fd], [], [], 0.03)[0]:
                                _read_key(fd)
                    else:
                        break
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except OSError:
                pass
            sys.stdout.write("\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()
    except (OSError, ImportError):
        _print_usage_inline(session, last, context)


def show_turn_usage(session):
    if not session or not session.get("calls"):
        return
    from .pricing import format_usd
    from .tokens import format_count
    total = session.get("input", 0) + session.get("output", 0)
    line = Text()
    line.append("  ", style="dim")
    line.append(f"{format_count(total)} tokens", style="dim")
    cost = session.get("cost")
    if cost is None and session.get("unknown"):
        line.append("  ·  unpriced", style="dim")
    else:
        line.append(f"  ·  {format_usd(cost)} session", style="dim")
        if session.get("unknown"):
            line.append("  ·  +unpriced", style="dim")
    if session.get("estimated"):
        line.append("  ·  ~est", style="dim")
    console.print(line)


def show_budget_warning(lines):
    if isinstance(lines, str):
        lines = [lines]
    for line in lines or []:
        warn = Text()
        warn.append("  budget  ", style="yellow")
        warn.append(str(line), style="yellow")
        console.print(warn)


def show_usage_range(name, totals):
    from .pricing import format_usd
    from .tokens import format_count
    console.print()
    head = Text()
    head.append(f"usage · {name}", style="white")
    console.print(head)
    console.print()
    if not totals or not totals.get("calls"):
        console.print(Text("  Nothing logged in this window yet.", style="dim"))
        console.print()
        return
    total = totals.get("input", 0) + totals.get("output", 0)
    console.print(Text(f"  {format_count(total)} tokens · {totals['calls']} calls · {totals.get('sessions', 0)} sessions", style="white"))
    cost = Text()
    cost.append("  cost  ", style="dim")
    cost.append(format_usd(totals.get("cost")), style="white")
    if totals.get("unknown"):
        cost.append(f" · {totals['unknown']} calls unknown pricing", style="dim")
    console.print(cost)
    console.print()


def show_by_model(groups):
    from .pricing import format_usd
    from .tokens import format_count
    console.print()
    head = Text()
    head.append("usage · by model", style="white")
    console.print(head)
    console.print()
    if not groups:
        console.print(Text("  Nothing logged yet.", style="dim"))
        console.print()
        return
    from rich.table import Table  # deferred: only needed when model usage table renders

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="left", style="white")
    table.add_column(justify="right", style="dim", width=10)
    table.add_column(justify="right", style="white", width=10)
    table.add_column(justify="right", style="dim", width=12)
    for (provider, model), agg in sorted(groups.items(), key=lambda kv: kv[1].get("cost", 0), reverse=True):
        total = agg.get("input", 0) + agg.get("output", 0)
        cost = format_usd(agg.get("cost")) if not agg.get("unknown") else f"{format_usd(agg.get('cost'))} +?"
        table.add_row(f"{provider}/{model}", format_count(total), f"{agg.get('calls', 0)} calls", cost)
    console.print(table)
    console.print()


def show_summary(summary, trace=None):
    if not summary:
        show_error("No implementation yet — run a task first.")
        console.print("  Try asking Hazzel to inspect, create, or edit files.", style="dim")
        console.print()
        return
    rule()
    title = Text()
    title.append("  summary", style="white")
    title.append("  ·  last implementation", style="dim")
    console.print(title)
    console.print()
    if trace:
        for t in trace:
            if not t.get("success"):
                continue
            name = t.get("tool", "")
            detail = t.get("detail") or ""
            line = Text()
            line.append("    – ", style="dim")
            line.append(name, style="white")
            if detail:
                line.append(f"  {detail}", style="dim")
            console.print(line)
        console.print()
    from .formatter import print_response  # deferred: pygments chain (~30ms)

    print_response(console, summary)
    console.print()


def show_star_nudge():
    console.print(Text("  If Hazzel helps, star us: github.com/mukundzha/hazzel", style="dim"))
    console.print()


def show_copied(msg="Copied to clipboard."):
    console.print()
    line = Text()
    line.append("  ", style="dim")
    line.append(msg, style="white")
    console.print(line)
    console.print()


def show_export(path):
    console.print()
    line = Text()
    line.append("  Exported to ", style="dim")
    line.append(str(path), style="white")
    console.print(line)
    console.print()


def show_skills(skills):
    rule()
    title = Text()
    title.append("  skills", style="white")
    title.append(f"  ·  {len(skills or [])} installed", style=DIM_COLOR)
    console.print(title)
    if not skills:
        console.print(Text("  No skills installed.", style=DIM_COLOR))
        console.print(Text("  Add one at .hazzel/skills/<name>/SKILL.md (frontmatter: name, description).", style=DIM_COLOR))
    else:
        for s in skills:
            row = Text()
            row.append("  ❯ ", style=DIM_COLOR)
            row.append(s.get("name", ""), style="white")
            row.append(f"  ·  {s.get('source', '')}", style=DIM_COLOR)
            console.print(row)
            desc = (s.get("description") or "no description").strip()
            if desc:
                console.print(Text(f"     {desc[:140]}", style=DIM_COLOR))
        console.print(Text("  /skills to pick · /skills <name> to preview", style=DIM_COLOR))
    rule()


def show_skill_detail(name, body):
    rule()
    title = Text()
    title.append(f"  skill: {name}", style="white")
    console.print(title)
    for line in (body or "").splitlines()[:60]:
        console.print(Text(f"  {line[:160]}", style="white" if line.strip() else DIM_COLOR))
    if len((body or "").splitlines()) > 60:
        console.print(Text(f"  …{len(body.splitlines()) - 60} more lines", style=DIM_COLOR))
    rule()


def show_logout():
    text = Text()
    text.append("  ○ ", style=DIM_COLOR)
    text.append("Saved API keys cleared", style="dim")
    console.print(text)
    console.print("  Run /model to set a new key.", style="dim")
    console.print()


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


def select_model(catalog, current_id=None):
    idx = 0
    for i, m in enumerate(catalog):
        if m["id"] == current_id:
            idx = i
            break
    if sys.stdin.isatty():
        try:
            import termios
            import tty
            import select
            max_len = max(len(m["display_name"]) for m in catalog)
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            selected = idx
            rendered = 0
            try:
                tty.setraw(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
                sys.stdout.write("\x1b[?25l")
                sys.stdout.flush()
                while True:
                    title = "  \x1b[2mSelect model\x1b[0m"
                    lines = []
                    lines.append("")
                    lines.append(title)
                    lines.append("")
                    visible = 5
                    total = len(catalog)
                    start = max(0, min(selected - visible // 2, total - visible))
                    end = min(total, start + visible)
                    if end - start < visible:
                        start = max(0, end - visible)
                    for idx in range(start, end):
                        m = catalog[idx]
                        mid = m["id"]
                        prov = f"[{m['provider'].lower()}]"
                        is_cur = m["id"] == current_id
                        is_sel = idx == selected
                        base = f"{mid} {prov}"
                        if is_cur:
                            base += " · current"
                        if is_sel:
                            base += " ✓" if is_cur else ""
                            lines.append(f"  \x1b[1m\x1b[97m❯ {base}\x1b[0m")
                        else:
                            lines.append(f"    \x1b[2m{base}\x1b[0m")
                    lines.append("")
                    lines.append(f"  \x1b[2m({selected + 1}/{total})\x1b[0m")
                    lines.append("")
                    cur_name = catalog[selected]["display_name"]
                    lines.append(f"  \x1b[2mModel Name: {cur_name}\x1b[0m")
                    lines.append("")
                    lines.append("  \x1b[2m↑↓ navigate · Enter confirm · Esc cancel\x1b[0m")
                    lines.append("")
                    out = "\r\n".join(lines)
                    redraw = "\r\n".join("\x1b[2K\r" + line for line in lines)
                    nlines = out.count("\r\n")
                    if rendered == 0:
                        sys.stdout.write(out)
                    else:
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write(redraw)
                    sys.stdout.flush()
                    rendered = nlines
                    ch = _read_key(fd)
                    if ch == "\x03":
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write("\x1b[J")
                        return None
                    if ch == "\x1b":
                        if select.select([fd], [], [], 0.04)[0]:
                            ch2 = _read_key(fd)
                            if ch2 in ("[", "O"):
                                if select.select([fd], [], [], 0.02)[0]:
                                    ch3 = _read_key(fd)
                                    if ch3 == "A":
                                        selected = (selected - 1) % len(catalog)
                                        continue
                                    if ch3 == "B":
                                        selected = (selected + 1) % len(catalog)
                                        continue
                            elif ch2 == "\x1b":
                                sys.stdout.write(f"\x1b[{rendered}A")
                                sys.stdout.write("\x1b[J")
                                return None
                        else:
                            sys.stdout.write(f"\x1b[{rendered}A")
                            sys.stdout.write("\x1b[J")
                            return None
                    elif ch in ("\r", "\n"):
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write("\x1b[J")
                        return catalog[selected]
                    elif ch in ("k", "K"):
                        selected = (selected - 1) % len(catalog)
                        continue
                    elif ch in ("j", "J"):
                        selected = (selected + 1) % len(catalog)
                        continue
                    elif ch.isdigit() and ch != "0":
                        n = int(ch) - 1
                        if 0 <= n < len(catalog):
                            selected = n
                            continue
                        if ch == "8" and len(catalog) >= 8:
                            selected = 7
                            continue
            except (KeyboardInterrupt, EOFError):
                try:
                    sys.stdout.write(f"\x1b[{rendered}A")
                    sys.stdout.write("\x1b[J")
                except OSError:
                    sys.stdout.write("\r\n")
                return None
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except OSError:
                    pass
                sys.stdout.write("\x1b[?25h\x1b[?12h")
                sys.stdout.flush()
        except (OSError, ImportError):
            pass
    console.print()
    console.print("  Select model", style="dim")
    console.print()
    max_len = max(len(m["display_name"]) for m in catalog)
    for i, m in enumerate(catalog):
        pad = m["display_name"].ljust(max_len)
        text = Text()
        text.append("  ")
        if i == idx:
            text.append("❯ ", style="white")
            text.append(f"{i+1}. ", style="dim")
            text.append(pad, style="white")
        else:
            text.append("  ")
            text.append(f"{i+1}. ", style="dim")
            text.append(pad, style="white")
        text.append(f"  ({m['provider_display']})", style="dim")
        console.print(text)
    console.print()
    console.print("  Enter number · Esc cancel", style="dim")
    console.print()
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if not raw:
        return None
    try:
        n = int(raw) - 1
        if 0 <= n < len(catalog):
            return catalog[n]
    except ValueError:
        for m in catalog:
            if m["display_name"].lower() == raw.lower() or m["id"] == raw:
                return m
    return None


def select_skill(skills):
    skills = list(skills or [])
    if not skills:
        console.print()
        console.print(Text("  No skills installed.", style=DIM_COLOR))
        console.print(Text("  Add one at .hazzel/skills/<name>/SKILL.md (frontmatter: name, description).", style=DIM_COLOR))
        console.print()
        return None
    if sys.stdin.isatty():
        try:
            import termios
            import tty
            import select
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            selected = 0
            rendered = 0
            try:
                tty.setraw(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
                sys.stdout.write("\x1b[?25l")
                sys.stdout.flush()
                while True:
                    lines = []
                    lines.append("")
                    lines.append("  \x1b[2mSelect skill\x1b[0m")
                    lines.append("")
                    visible = 8
                    total = len(skills)
                    start = max(0, min(selected - visible // 2, total - visible))
                    end = min(total, start + visible)
                    if end - start < visible:
                        start = max(0, end - visible)
                    for idx in range(start, end):
                        name = skills[idx].get("name", "")
                        if idx == selected:
                            lines.append(f"  \x1b[1m\x1b[97m❯ {name}\x1b[0m")
                        else:
                            lines.append(f"    \x1b[2m{name}\x1b[0m")
                    lines.append("")
                    lines.append(f"  \x1b[2m({selected + 1}/{total})\x1b[0m")
                    lines.append("")
                    lines.append("  \x1b[2m↑↓ navigate · Enter select · Esc cancel\x1b[0m")
                    lines.append("")
                    out = "\r\n".join(lines)
                    redraw = "\r\n".join("\x1b[2K\r" + line for line in lines)
                    nlines = out.count("\r\n")
                    if rendered == 0:
                        sys.stdout.write(out)
                    else:
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write(redraw)
                    sys.stdout.flush()
                    rendered = nlines
                    ch = _read_key(fd)
                    if ch == "\x03":
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write("\x1b[J")
                        return None
                    if ch == "\x1b":
                        if select.select([fd], [], [], 0.04)[0]:
                            ch2 = _read_key(fd)
                            if ch2 in ("[", "O"):
                                if select.select([fd], [], [], 0.02)[0]:
                                    ch3 = _read_key(fd)
                                    if ch3 == "A":
                                        selected = (selected - 1) % len(skills)
                                        continue
                                    if ch3 == "B":
                                        selected = (selected + 1) % len(skills)
                                        continue
                            elif ch2 == "\x1b":
                                sys.stdout.write(f"\x1b[{rendered}A")
                                sys.stdout.write("\x1b[J")
                                return None
                        else:
                            sys.stdout.write(f"\x1b[{rendered}A")
                            sys.stdout.write("\x1b[J")
                            return None
                    elif ch in ("\r", "\n"):
                        sys.stdout.write(f"\x1b[{rendered}A")
                        sys.stdout.write("\x1b[J")
                        return skills[selected]
                    elif ch in ("k", "K"):
                        selected = (selected - 1) % len(skills)
                        continue
                    elif ch in ("j", "J"):
                        selected = (selected + 1) % len(skills)
                        continue
                    elif ch.isdigit() and ch != "0":
                        n = int(ch) - 1
                        if 0 <= n < len(skills):
                            selected = n
                            continue
            except (KeyboardInterrupt, EOFError):
                try:
                    sys.stdout.write(f"\x1b[{rendered}A")
                    sys.stdout.write("\x1b[J")
                except OSError:
                    sys.stdout.write("\r\n")
                return None
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except OSError:
                    pass
                sys.stdout.write("\x1b[?25h\x1b[?12h")
                sys.stdout.flush()
        except (OSError, ImportError):
            pass
    console.print()
    console.print(Text("  Select skill", style="dim"))
    console.print()
    for i, s in enumerate(skills):
        text = Text()
        text.append("  ")
        if i == 0:
            text.append("❯ ", style=f"bold {HAZZEL_COLOR}")
        else:
            text.append("  ", style=DIM_COLOR)
        text.append(f"{i + 1}. ", style="dim")
        text.append(s.get("name", ""), style="bold bright_white")
        console.print(text)
    console.print()
    console.print(Text("  Enter number · empty cancel", style="dim"))
    console.print()
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    if not raw:
        return None
    try:
        n = int(raw) - 1
        if 0 <= n < len(skills):
            return skills[n]
    except ValueError:
        for s in skills:
            if s.get("name", "").lower() == raw.lower():
                return s
    return None


def _mask_key(key):
    if not key or len(key) <= 8:
        return "••••"
    return "•" * 8 + key[-4:]


def prompt_api_key(existing=None):
    if existing and existing.strip():
        console.print(f"  API Key: {_mask_key(existing.strip())} (press Enter to keep)", style="dim")
        console.print("  API Key: ", end="")
    else:
        console.print("  API Key: ", end="")
    sys.stdout.flush()
    if sys.stdin.isatty():
        try:
            import termios
            import tty
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            key = ""
            try:
                tty.setraw(fd)
                termios.tcflush(fd, termios.TCIFLUSH)
                while True:
                    ch = _read_key(fd)
                    if ch in ("\r", "\n"):
                        sys.stdout.write("\r\n")
                        break
                    if ch == "\x03":
                        raise KeyboardInterrupt
                    if ch in ("\x7f", "\x08"):
                        if key:
                            key = key[:-1]
                            sys.stdout.write("\b \b")
                            sys.stdout.flush()
                        continue
                    if ch == "\x1b":
                        continue
                    if ch == "\x15":
                        while key:
                            key = key[:-1]
                            sys.stdout.write("\b \b")
                        sys.stdout.flush()
                        continue
                    if ch and ch.isprintable():
                        key += ch
                        sys.stdout.write("•")
                        sys.stdout.flush()
            except KeyboardInterrupt:
                sys.stdout.write("\r\n")
                return None
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except OSError:
                    pass
                sys.stdout.write("\x1b[?25h\x1b[?12h")
                sys.stdout.flush()
            return key
        except (OSError, ImportError):
            pass
    try:
        import getpass
        val = getpass.getpass("")
        console.print()
        return val
    except (EOFError, KeyboardInterrupt):
        console.print()
        return None
    except OSError:
        try:
            val = input()
            return val
        except (EOFError, KeyboardInterrupt):
            return None
        except OSError:
            return ""
