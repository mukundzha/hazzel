import os
import re
import sys
import textwrap
import time

from rich.console import Console
from rich.containers import Renderables
from rich.align import Align
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from .formatter import print_response

console = Console()

_loader = None

HAZZEL_COLOR = "#FA0002"
USER_COLOR = "#8ab4f8"

TOOL_COLOR = "#c4c7c5"
SUCCESS_COLOR = "#9ece6a"
ERROR_COLOR = "#f7768e"

DIM_COLOR = "dim"


def show_welcome(model, project_root):
    console.print()
    _show_header(model, project_root)
    console.print()


def _hw():
    try:
        return max(30, int(console.width))
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
            _ver = "1.3.2"
    title = Text()
    title.append("Hazzel", style=f"bold {HAZZEL_COLOR}")
    title.append(f" {_ver}", style=DIM_COLOR)
    console.print(title)
    path = Text()
    path.append(_short_path(project_root), style=DIM_COLOR)
    console.print(path)


SLASH_COMMANDS = [
    {"name": "/model", "desc": "switch model / provider"},
    {"name": "/prove", "desc": "ephemeral smoke check on/off"},
    {"name": "/plan", "desc": "read-only plan mode on/off"},
    {"name": "/goal", "desc": "objective + run · criteria"},
    {"name": "/status", "desc": "git working-tree status"},
    {"name": "/diff", "desc": "git diff preview"},
    {"name": "/commit", "desc": "suggest + commit (approval)"},
    {"name": "/review", "desc": "senior-level code review"},
    {"name": "/branch", "desc": "list / switch branches"},
    {"name": "/push", "desc": "push branch to remote"},
    {"name": "/pull", "desc": "pull remote changes"},
    {"name": "/sync", "desc": "pull then push"},
    {"name": "/log", "desc": "recent commits"},
    {"name": "/pr", "desc": "list / view / create PRs"},
    {"name": "/help", "desc": "show help"},
    {"name": "/docs", "desc": "full usage guide"},
    {"name": "/clear", "desc": "clear conversation + usage"},
    {"name": "/summary", "desc": "summarize last implementation"},
    {"name": "/export", "desc": "save transcript to markdown"},
    {"name": "/copy", "desc": "copy last reply [code]"},
    {"name": "/init", "desc": "generate AGENTS.md map"},
    {"name": "/retry", "desc": "re-run last message"},
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
_MENTION_CACHE_TTL = 10.0

_file_cache = {"root": None, "ts": 0.0, "files": []}


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

    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.endswith(".egg-info")]
        dirnames.sort()
        for name in sorted(filenames):
            files.append(os.path.relpath(os.path.join(dirpath, name), root))
            if len(files) >= _MENTION_FILE_CAP:
                break
        if len(files) >= _MENTION_FILE_CAP:
            break
    _file_cache.update({"root": root, "ts": now, "files": files})
    return files


def _mention_candidates(query, limit=_MENTION_ROWS):
    files = _all_project_files()
    q = (query or "").lower().lstrip("./")
    if not q:
        ranked = sorted(files, key=lambda p: (p.count("/"), len(p), p.lower()))
        return ranked[:limit], len(files)
    scored = []
    has_slash = "/" in q
    for path in files:
        low = path.lower()
        if has_slash:
            if q in low:
                scored.append((0 if low.startswith(q) else 1, len(path), low, path))
        else:
            base = os.path.basename(low)
            if base == q:
                scored.append((0, len(path), low, path))
            elif base.startswith(q):
                scored.append((1, len(path), low, path))
            elif q in base:
                scored.append((2, len(path), low, path))
            elif q in low:
                scored.append((3, len(path), low, path))
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    ranked = [item[3] for item in scored[:50]]
    return ranked[:limit], len(ranked)


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


MENTION_COLOR = "\x1b[1;94m"
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


def get_input(messages=None):
    from . import wincompat

    if not sys.stdin.isatty() or wincompat.is_windows():
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            raise
        rule()
        console.print(f"❯ {line}")
        rule()
        console.print()
        return line
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

    buffer = ""
    selected = 0
    rendered_nlines = 0
    rendered_lines = 0
    m_selected = 0
    m_last_query = None
    m_dismissed = None
    m_cands = []
    m_total = 0
    try:
        tty.setraw(fd)
        termios.tcflush(fd, termios.TCIFLUSH)
        sys.stdout.write("\x1b[?2004h")
        sys.stdout.write("\x1b[?25h\x1b[?12h")
        sys.stdout.flush()
        while True:
            filtered = []
            if buffer.startswith("/"):
                q = buffer.lower()
                filtered = [c for c in SLASH_COMMANDS if c["name"].startswith(q)]
                if not filtered:
                    filtered = [c for c in SLASH_COMMANDS if q in c["name"]]
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
            else:
                if mention[1] != m_last_query:
                    m_selected = 0
                    m_last_query = mention[1]
                m_cands, m_total = _mention_candidates(mention[1])

            bar = "\x1b[2m" + ("─" * _hw()) + "\x1b[0m"
            rst = "\x1b[0m"
            try:
                from . import config

                mid = config.get_current_model().split("/")[-1].lower()
            except OSError:
                mid = ""
            try:
                from hazzel import agent as _agent
                from .tokens import format_count as _fmt

                _used, _window = _agent.context_usage(messages)
                tok = format_context_meter(_used, _window)
            except Exception:
                try:
                    _u = _agent.get_session_usage()
                    _total = (_u.get("input") or 0) + (_u.get("output") or 0)
                    tok = f"{_fmt(_total)} tokens" if _u.get("calls") else "0 tokens"
                except Exception:
                    tok = ""
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
                        lines.append(f"  \x1b[1m\x1b[97m\u276f\x1b[0m \x1b[1m\x1b[97m{name}\x1b[0m  \x1b[2m{desc}\x1b[0m")
                    else:
                        lines.append(f"    \x1b[2m{name}  {desc}\x1b[0m")
                lines.append(f"  \x1b[2m({selected + 1}/{total})\x1b[0m")
            lines.append(bar)
            try:
                from . import config as _cfg

                _plan_bit = " · plan" if _cfg.is_plan_enabled() else " · build"
                _goal = _cfg.get_goal() or {}
                _gtext = (_goal.get("objective") or "").strip()
                if len(_gtext) > 28:
                    _gtext = _gtext[:28] + "…"
                _goal_bit = f" · ⚑ {_gtext}" if _gtext else ""
            except Exception:
                _plan_bit = ""
                _goal_bit = ""
            if tok:
                lines.append(f"  \x1b[2m{mid} · {tok}{_plan_bit}{_goal_bit} · @ tag · ! bash · /exit{rst}")
            else:
                lines.append(f"  \x1b[2m{mid}{_plan_bit}{_goal_bit} · @ tag · ! bash · /exit{rst}")

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
    if _loader is not None:
        _loader.update(_live_body(text))
        return
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


def begin_stream():
    global _stream_buffer, _stream_started, _stream_first_at, _stream_tokens, _stream_last_paint
    _stream_buffer = ""
    _stream_started = time.monotonic()
    _stream_first_at = None
    _stream_tokens = 0
    _stream_last_paint = 0.0


def push_stream_token(token):
    global _stream_buffer, _stream_first_at, _stream_tokens, _stream_last_paint
    if not token:
        return
    now = time.monotonic()
    if _stream_first_at is None:
        _stream_first_at = now
    _stream_buffer += token
    _stream_tokens += 1
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


_loader = None
_tool_rows: list[Text] = []
_turn_started = None


def end_turn():
    hide_loader()


def _read_expand_key():
    fd = sys.stdin.fileno()
    try:
        import select
        import termios
        import tty
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            termios.tcflush(fd, termios.TCIFLUSH)
            ready, _, _ = select.select([fd], [], [], 30)
            if not ready:
                return False
            return _read_key(fd) in ("\r", "\n")
        finally:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
            except OSError:
                pass
    except (OSError, ImportError):
        return False


_quiet = False


def set_quiet(value=True):
    global _quiet
    _quiet = bool(value)
    return _quiet


def is_quiet():
    return _quiet


def show_turn_from_trace(user_command, trace, summary):
    rows = []
    for t in trace or []:
        if t.get("cached"):
            continue
        detail = str(t.get("detail") or "")
        if len(detail) > 42:
            detail = detail[:41].rstrip() + "…"
        rows.append((t.get("tool", ""), detail, bool(t.get("success"))))
    rows = rows[:8]
    lines = []
    for line in str(summary or "").splitlines():
        line = line.strip()
        if line:
            lines.append(line)
        if len(lines) >= 4:
            break
    if not lines:
        lines = ["Done."]
    try:
        from . import config as _config
        model = _config.get_current_display_name()
        root = _short_path(_config.PROJECT_ROOT)
    except Exception:
        model = "Hazzel 1.3.2"
        root = "~/hazzel"
    show_turn_card(user_command, rows, lines, model=model, root=root)


def show_turn_card(user_command, tool_rows, summary_lines, model="Hazzel 1.3.2", root="~/hazzel"):
    body = Text()
    body.append(f"{model}\n", style=f"bold {HAZZEL_COLOR}")
    body.append(f"{root}\n\n", style=DIM_COLOR)
    body.append("❯ ", style="dim")
    body.append(f"{user_command}\n\n", style="white")
    for name, detail, success in tool_rows or []:
        icon = "●" if success else "✗"
        color = SUCCESS_COLOR if success else ERROR_COLOR
        body.append(f"  {icon} ", style=f"bold {color}")
        body.append(f"{str(name).ljust(12)}", style="bold")
        if detail:
            body.append(f" {detail}\n", style=DIM_COLOR)
        else:
            body.append("\n")
    if tool_rows:
        body.append("\n")
    body.append("─" * 38 + "\n", style="dim")
    for line in summary_lines or []:
        body.append(f"{line}\n", style="white")
    body.append("\n")
    body.append("❯ ", style="dim")
    body.append("█", style="white")
    console.print(Panel(body, title=f"{model} ── {root}", border_style="dim", padding=(1, 2)))


def show_hazzel_message(message):
    hide_loader()
    if not message or not message.strip():
        return
    print_response(console, message)


def show_reasoning(reasoning):
    text = (reasoning or "").strip()
    if not text:
        return
    if not sys.stdin.isatty():
        console.print(Text(text, style="dim"))
        console.print()
        return
    console.print(Text(f"  … thinking ({len(text.splitlines())} lines) — Enter to expand, any other key to skip", style="dim"))
    if _read_expand_key():
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


def show_tool(tool_name, detail="", success=True, exit_code=None, cached=False, elapsed=None):
    if _quiet:
        return
    icon = "●" if success else "✗"
    color = SUCCESS_COLOR if success else ERROR_COLOR
    limit = 45 if exit_code is not None else 62
    text = Text()
    text.append("  ", style=DIM_COLOR)
    if cached:
        text.append(f"{icon} ", style=DIM_COLOR)
        text.append(str(tool_name).ljust(12), style=DIM_COLOR)
    else:
        text.append(f"{icon} ", style=f"bold {color}")
        text.append(str(tool_name).ljust(12), style="bold")
    short = _short_detail(_relativize_detail(detail), limit=limit)
    if short:
        text.append(f" {short}", style=DIM_COLOR)
    meta = _format_elapsed(elapsed)
    if cached:
        meta = (meta + " · " if meta else "") + "cached"
    if meta:
        text.append(f"  · {meta}", style=DIM_COLOR)
    if exit_code is not None and not success:
        text.append(f"  · exit {exit_code}", style=DIM_COLOR)
    if _loader is not None:
        _tool_rows.clear()
        _tool_rows.append(text)
        _loader.update(_live_body(None))
    else:
        console.print(text)


def show_user_command(command):
    bar = Text("─" * _hw(), style="dim")
    console.print(bar)
    text = Text()
    text.append("❯ ", style="dim")
    text.append(command.strip(), style="white")
    console.print(text)
    console.print(bar)


def show_error(message):
    text = Text()
    text.append("  ✗ ", style=f"bold {ERROR_COLOR}")
    text.append(message, style=ERROR_COLOR)
    console.print(text)


def confirm(prompt):
    was_active = _pause_loader()
    try:
        answer = input(f"\n{prompt} [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return False
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip().lower()
    return clean == "y"


def confirm_prove(files, action):
    was_active = _pause_loader()
    try:
        console.print()
        head = Text()
        head.append("  ◈ Prove", style="bold white")
        head.append(f"  ·  {action}", style=DIM_COLOR)
        console.print(head)
        for f in (files or [])[:5]:
            row = Text()
            row.append("  ❯ ", style=f"bold {HAZZEL_COLOR}")
            row.append(str(f), style="white")
            console.print(row)
        extra = len(files or []) - 5
        if extra > 0:
            console.print(Text(f"  …{extra} more", style=DIM_COLOR))
        answer = input("  Run? [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return False
    finally:
        _resume_loader(was_active)
    clean = _ANSI_RE.sub("", answer or "").strip().lower()
    return clean in ("y", "yes")


def show_diff(diff):
    was_active = _pause_loader()
    try:
        rule()
        for line in diff.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                console.print(Text(f"  {line}", style=SUCCESS_COLOR))
            elif line.startswith("-") and not line.startswith("---"):
                console.print(Text(f"  {line}", style=ERROR_COLOR))
            else:
                console.print(Text(f"  {line}", style=DIM_COLOR))
        rule()
    finally:
        _resume_loader(was_active)


VIEW_MAX_LINES = 2000


def show_file_viewer(display_path, body, total_lines, shown_lines):
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
        text.append("  ✓ ", style=f"bold {SUCCESS_COLOR}")
        text.append(f"{action} ", style="bold white")
        text.append(_short_detail(key), style=DIM_COLOR)
        console.print(text)
    console.print()


def show_git_status(branch, body):
    rule()
    title = Text()
    title.append("  Git status", style="bold white")
    title.append(f"  ·  {branch or 'HEAD'}", style=DIM_COLOR)
    console.print(title)
    if not body or body.strip() in ("(clean)", "Clean."):
        console.print(Text("  Clean — nothing to commit.", style=SUCCESS_COLOR))
    else:
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
    rule()
    title = Text()
    title.append("  Git diff", style="bold white")
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    console.print(title)
    if not body or body.strip() in ("No changes.", "(clean)"):
        console.print(Text("  No changes.", style=DIM_COLOR))
    else:
        show_diff(body[:12000])
    rule()


def show_git_file_list(files, staged=False, branch=""):
    from rich.panel import Panel

    total_add = sum(f.get("added", 0) for f in files)
    total_del = sum(f.get("deleted", 0) for f in files)
    rule()
    title = Text()
    title.append(f"  Changed files  ·  {len(files)}", style="bold white")
    title.append(f"  ·  +{total_add} −{total_del}", style=SUCCESS_COLOR)
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    if branch:
        title.append(f"  ·  {branch}", style=DIM_COLOR)
    console.print(title)
    if not files:
        console.print(Text("  No changes.", style=DIM_COLOR))
        rule()
        return
    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 1, 0, 0))
    table.add_column(overflow="fold", width=4, justify="right")
    table.add_column(overflow="fold", width=3)
    table.add_column(overflow="fold", ratio=1)
    table.add_column(overflow="fold", justify="right", width=8)
    table.add_column(overflow="fold", justify="right", width=8)
    icons = {"M": ("M", USER_COLOR), "A": ("A", SUCCESS_COLOR), "?": ("+", SUCCESS_COLOR),
             "D": ("D", ERROR_COLOR), "R": ("R", HAZZEL_COLOR)}
    for i, f in enumerate(files, 1):
        letter, color = icons.get(f.get("status", "M"), ("M", USER_COLOR))
        table.add_row(
            Text(str(i), style=DIM_COLOR),
            Text(letter, style=f"bold {color}"),
            Text(f["path"], style="white"),
            Text(f"+{f.get('added', 0)}", style=SUCCESS_COLOR),
            Text(f"−{f.get('deleted', 0)}", style=ERROR_COLOR),
        )
    console.print(Panel(table, border_style="dim", padding=(0, 1)))
    console.print(Text("  Enter number to open · q = close", style=DIM_COLOR))
    rule()


def show_git_file_diff(path, body, staged=False, position=""):
    title = Text()
    title.append(f"  ❯ {position}{path}" if position else f"  ❯ {path}", style="bold white")
    title.append("  ·  staged" if staged else "  ·  unstaged", style=DIM_COLOR)
    console.print(title)
    show_diff(body)
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


def show_git_branches(current, body):
    rule()
    title = Text()
    title.append("  Branches", style="bold white")
    if current:
        title.append(f"  ·  on {current}", style=DIM_COLOR)
    console.print(title)
    for line in (body or "").splitlines():
        mark = line[:2]
        name = line[2:].strip()
        row = Text()
        if mark.strip() == "*":
            row.append("  ❯ ", style=f"bold {HAZZEL_COLOR}")
            row.append(name, style="bold white")
        else:
            row.append("    ", style=DIM_COLOR)
            row.append(name, style="dim")
        console.print(row)
    rule()


def show_git_log(body):
    rule()
    console.print(Text("  Recent commits", style="bold white"))
    for line in (body or "").splitlines()[:20]:
        parts = line.split(" ", 1)
        row = Text()
        row.append("  ", style=DIM_COLOR)
        row.append(parts[0] if parts else "", style=f"bold {USER_COLOR}")
        if len(parts) > 1:
            row.append(f"  {parts[1]}", style="white")
        console.print(row)
    rule()


def show_pr_list(body):
    rule()
    console.print(Text("  Pull requests  ·  open", style="bold white"))
    if not body or body.strip().lower() in ("no open pull requests.", "(clean)", "(empty)"):
        console.print(Text("  No open pull requests.", style=DIM_COLOR))
        rule()
        return
    table = Table(show_header=False, box=None, pad_edge=False, padding=(0, 1, 0, 0))
    table.add_column(overflow="fold", width=6, justify="right")
    table.add_column(overflow="fold", ratio=1)
    table.add_column(overflow="fold", width=20)
    for line in body.splitlines()[:20]:
        parts = line.split("\t")
        row = Text()
        num = parts[0].strip() if parts else ""
        title = parts[1].strip() if len(parts) > 1 else line.strip()
        branch = parts[2].strip() if len(parts) > 2 else ""
        table.add_row(
            Text(f"#{num}", style=f"bold {USER_COLOR}"),
            Text(title[:80], style="white"),
            Text(branch[:20], style=DIM_COLOR),
        )
    console.print(table)
    extra = len(body.splitlines()) - 20
    if extra > 0:
        console.print(Text(f"  …{extra} more", style=DIM_COLOR))
    console.print(Text("  /pr view <n> · /pr diff <n> · /pr checks <n>", style=DIM_COLOR))
    rule()


def show_pr_view(body):
    rule()
    console.print(Text("  Pull request", style="bold white"))
    if not body or body.strip() in ("(empty)", "(clean)"):
        console.print(Text("  Not found.", style=DIM_COLOR))
    else:
        for line in body.splitlines()[:80]:
            console.print(Text(f"  {line[:160]}", style="white" if line.strip() else DIM_COLOR))
        if len(body.splitlines()) > 80:
            console.print(Text(f"  …{len(body.splitlines()) - 80} more lines", style=DIM_COLOR))
    rule()


def show_pr_checks(body):
    rule()
    console.print(Text("  PR checks", style="bold white"))
    if not body or body.strip() in ("(empty)", "(clean)", "No checks reported."):
        console.print(Text("  No checks reported.", style=DIM_COLOR))
    else:
        for line in body.splitlines()[:30]:
            low = line.lower()
            if "pass" in low or "success" in low:
                color = SUCCESS_COLOR
            elif "fail" in low:
                color = ERROR_COLOR
            else:
                color = "white"
            console.print(Text(f"  {line[:140]}", style=color))
    rule()


def show_pr_result(result):
    text = Text()
    low = (result or "").lower()
    if any(k in low for k in ("cancelled", "nothing", "not a git", "not installed", "not authenticated", "tool error", "invalid")):
        text.append("  ○ ", style=f"bold {DIM_COLOR}")
        text.append(result, style="dim")
    else:
        text.append("  ✓ ", style=f"bold {SUCCESS_COLOR}")
        first = (result or "").strip().splitlines()[0][:160] if (result or "").strip() else "Done."
        text.append(first, style="bold white")
        rest = (result or "").strip().splitlines()[1:3]
        for line in rest:
            if line.strip().startswith("https://"):
                console.print(text)
                console.print(Text(f"  {line.strip()}", style=f"{USER_COLOR} underline"))
                console.print()
                return
    console.print(text)
    console.print()


def show_pr_suggest(title, body="", fallback=False):
    rule()
    title_row = Text()
    title_row.append("  Suggested PR", style="bold white")
    if fallback:
        title_row.append("  ·  offline draft", style=DIM_COLOR)
    console.print(title_row)
    row = Text()
    row.append("  ❯ ", style=f"bold {HAZZEL_COLOR}")
    row.append(title, style="bold white")
    console.print(row)
    if (body or "").strip():
        console.print(Text(f"  {(body or '').strip().splitlines()[0][:120]}", style=DIM_COLOR))
    console.print(Text("  [y] create · [e] edit · [n] cancel", style=DIM_COLOR))
    rule()


_REVIEW_SEVERITIES = ("Critical", "Major", "Minor", "Nit")

_REVIEW_SEV_STYLE = {
    "Critical": f"bold {ERROR_COLOR}",
    "Major": "bold yellow",
    "Minor": "yellow",
    "Nit": DIM_COLOR,
}


def _parse_review(text):
    verdict = ""
    sections = []
    good = ""
    current = None
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if low.startswith("verdict:"):
            verdict = line[len("verdict:"):].strip()
            current = None
        elif low.startswith("good:"):
            good = line[len("good:"):].strip()
            current = "good"
        elif low.startswith("findings:"):
            current = None
        else:
            sev = None
            for name in _REVIEW_SEVERITIES:
                if low.startswith(f"[{name.lower()}]"):
                    sev = name
                    rest = line[len(name) + 2:].strip()
                    break
            if sev is not None:
                current = []
                sections.append((sev, current))
                if rest:
                    current.append(rest)
            elif current == "good":
                good += " " + line
            elif isinstance(current, list):
                current.append(line)
    return verdict, sections, good


_REVIEW_FILE_RE = re.compile(r"[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+:\d+")
_REVIEW_CODE_RE = re.compile(r"`[^`]+`")


def _styled_spans(line, base):
    row = Text()
    marks = []
    for match in _REVIEW_FILE_RE.finditer(line):
        marks.append((match.start(), match.end(), f"bold {USER_COLOR}"))
    for match in _REVIEW_CODE_RE.finditer(line):
        marks.append((match.start(), match.end(), "bold white"))
    prefix = re.match(r"\s*(\d+\.\s*)?", line)
    off = prefix.end() if prefix else 0
    if line[off:off + 4].lower() == "fix:":
        marks.append((off, off + 4, f"bold {SUCCESS_COLOR}"))
    marks.sort()
    pos = 0
    for start, end, style in marks:
        if start > pos:
            row.append(line[pos:start], style=base)
        row.append(line[start:end], style=style)
        pos = max(pos, end)
    row.append(line[pos:], style=base)
    return row


def _term_width():
    try:
        return max(40, _hw())
    except Exception:
        return 80


def _render_finding(line, num, dim=False):
    base = DIM_COLOR if dim else "white"
    rows = textwrap.wrap(
        line,
        width=_term_width(),
        initial_indent=f"    {num}. ",
        subsequent_indent="       ",
        break_long_words=False,
        break_on_hyphens=False,
    ) or [f"    {num}. "]
    out = []
    for i, row_text in enumerate(rows):
        text = _styled_spans(row_text, base)
        if i > 0:
            plain = Text("       ", style=DIM_COLOR)
            plain.append_text(text)
            text = plain
        out.append(text)
    return out


def _render_wrapped(line, indent="    ", dim=True):
    base = DIM_COLOR if dim else "white"
    rows = textwrap.wrap(
        line,
        width=_term_width(),
        initial_indent=indent,
        subsequent_indent=indent,
        break_long_words=False,
        break_on_hyphens=False,
    ) or [indent.rstrip()]
    return [_styled_spans(row_text, base) for row_text in rows]


def show_review(result, scope=""):
    verdict, sections, good = _parse_review(result or "")
    if not verdict and not sections:
        console.print(Text(result or "(empty review)", style="white"))
        console.print()
        return
    total = sum(len(lines) for _, lines in sections)
    head = Text()
    head.append("  Code review", style="bold white")
    if scope:
        head.append(f"  ·  {scope}", style=DIM_COLOR)
    if total:
        head.append(f"  ·  {total} finding{'s' if total != 1 else ''}", style=DIM_COLOR)
    reason = ""
    if verdict:
        status, sep, extra = verdict.partition("—")
        if not sep:
            status, sep, extra = verdict.partition(" - ")
        bad = "request changes" in status.lower()
        color = ERROR_COLOR if bad else SUCCESS_COLOR
        head.append("  ·  ", style=DIM_COLOR)
        head.append("✗ " if bad else "✓ ", style=f"bold {color}")
        head.append(status.strip(), style=f"bold {color}")
        reason = extra.strip()
    console.print(head)
    if reason:
        for row in _render_wrapped(reason, indent="      ", dim=False):
            console.print(row)
    rule()
    for sev, lines in sections:
        console.print()
        console.print(Text(f"  [{sev}]", style=_REVIEW_SEV_STYLE[sev]))
        for num, line in enumerate(lines, 1):
            for row in _render_finding(line, num, dim=(sev == "Nit")):
                console.print(row)
    if good:
        console.print()
        console.print(Text("  ✓ Good", style=f"bold {SUCCESS_COLOR}"))
        for row in _render_wrapped(good):
            console.print(row)
    console.print()
    if total:
        next_step = "  Fix findings, re-run /review, then /commit."
    else:
        next_step = "  Clean — /commit when ready."
    console.print(Text(next_step, style=DIM_COLOR))
    rule()


def show_model_selected(display_name, provider_display):
    text = Text()
    text.append("  ✓ ", style=f"bold {SUCCESS_COLOR}")
    text.append(display_name, style="bold white")
    text.append(f" ({provider_display})", style=DIM_COLOR)
    console.print(text)
    console.print()


def show_cleared():
    text = Text()
    text.append("  ○ ", style=f"bold {DIM_COLOR}")
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
        ("/prove", "smoke check on/off"),
        ("/plan", "read-only plan, approve first"),
        ("/goal", "objective + acceptance"),
        ("/help", "this overview"),
        ("/docs", "full usage guide"),
        ("/clear", "reset conversation + usage"),
        ("/summary", "summarize last implementation"),
        ("/export", "save transcript [file.md]"),
        ("/copy", "copy last reply [code]"),
        ("/init", "generate AGENTS.md map"),
        ("/retry", "re-run last message"),
        ("/usage", "show token usage"),
        ("/undo", "undo last file change"),
        ("/logout", "clear saved API keys"),
        ("/exit", "quit"),
    ]),
    ("Git", [
        ("/status", "working-tree status"),
        ("/diff", "changed files + full diff [--staged]"),
        ("/commit", "suggest message + approval"),
        ("/review", "senior review [@file|codebase] [--staged]"),
        ("/branch", "list / create / switch"),
        ("/push", "push branch to remote"),
        ("/pull", "pull remote changes"),
        ("/sync", "pull then push"),
        ("/log", "recent commits"),
        ("/pr", "list / view / checks / create / merge / close"),
    ]),
]


_HELP_FOOT = "Models  ·  Groq · OpenAI · Mistral · Anthropic · Gemini · DeepSeek · OpenRouter · Ollama  —  /model to switch"
_STAR_LINE = "If Hazzel helps, star us: github.com/mukundzha/hazzel"


def _help_table(rows):
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
            cells.append(Text(cell, style=("bold white" if j % 2 == 0 else "dim")))
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
            text.append(part[1:-1], style="bold white")
            continue
        pos = 0
        for m in re.finditer(r"/[a-z]+|@\S+", part):
            if m.start() > pos:
                text.append(part[pos:m.start()], style="dim" if i == 0 and m.start() == 0 else "white")
            tok = m.group(0)
            text.append(tok, style=f"bold {HAZZEL_COLOR}" if tok.startswith("/") else f"bold {USER_COLOR}")
            pos = m.end()
        text.append(part[pos:], style="white" if pos else ("dim" if line.startswith("/") else "white"))
    return text


def show_docs():
    from .docs import get_sections

    sections = get_sections()
    rule()
    head = Text()
    head.append("  Hazzel docs", style="bold white")
    head.append(f"  ·  {len(sections)} sections", style=DIM_COLOR)
    console.print(head)
    rule()
    for i, (title, lines) in enumerate(sections):
        console.print()
        sec = Text()
        sec.append(f"  {i + 1:02d}  ", style=DIM_COLOR)
        sec.append(title, style="bold white")
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
    console.print(Text(_HELP_INTRO, style="bold white"))
    for title, rows in _HELP_SECTIONS:
        console.print()
        console.print(Text(title, style="bold white"))
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
            console.print(Text(_HELP_INTRO, style="bold white"))
            for title, rows in _HELP_SECTIONS:
                console.print()
                console.print(Text(title, style="bold white"))
                console.print(_help_table(rows))
            console.print()
            console.print(Text(_HELP_FOOT, style="dim"))
            console.print()
            console.print(Text("Esc to cancel", style="dim"))
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
    from .tokens import format_count
    sent = int(session.get("input") or 0)
    received = int(session.get("output") or 0)
    cached = int(session.get("cached") or 0)
    calls = int(session.get("calls") or 0)
    total = sent + received

    header = Text()
    header.append("◈ ", style=f"bold {HAZZEL_COLOR}")
    header.append("USAGE", style="bold white")
    header.append("   tokens used this conversation", style="dim")
    yield header
    yield Text("")

    if not calls:
        yield Panel(
            Align.center(Text("No usage yet\nAsk Hazzel to read, edit, or run something.", style="dim", justify="center")),
            border_style="dim",
            padding=(1, 4),
        )
        return

    hero = Text(justify="center")
    hero.append(f"{total:,}", style="bold white")
    hero.append(f"  tokens · {calls} call{'s' if calls != 1 else ''}", style="dim")
    yield Panel(Align.center(hero), border_style="dim", padding=(1, 4))
    if context:
        try:
            ctx = Text(justify="center")
            ctx.append("◈ context  ", style="dim")
            ctx.append(format_context_plain(context[0], context[1]), style="bold white")
            yield ctx
            yield Text("")
        except Exception:
            pass

    table = Table.grid(padding=(0, 2))
    table.add_column(justify="right", style="dim", width=10)
    table.add_column(justify="right", style="bold white", width=10)
    table.add_column(justify="left", style="dim")

    table.add_row("↑ sent", format_count(sent), "to the model")
    table.add_row("↓ received", format_count(received), "generated back")
    if cached:
        table.add_row("◇ cached", format_count(cached), "reused · cheaper")
    yield Align.center(table)
    if last and last.get("calls"):
        last_total = (last.get("input") or 0) + (last.get("output") or 0)
        suffix = " · estimated" if last.get("estimated") else ""
        last_line = Text()
        last_line.append("—  last turn  ", style="dim")
        last_line.append(f"{format_count(last_total)} tokens{suffix}", style="white")
        yield Text("")
        yield Align.center(last_line)
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
    from .tokens import format_count
    total = session.get("input", 0) + session.get("output", 0)
    suffix = " ~" if session.get("estimated") else ""
    console.print(Text(f"  {format_count(total)}{suffix} tokens used", style="dim"))


def show_summary(summary, trace=None):
    if not summary:
        show_error("No implementation yet — run a task first.")
        console.print("  Try asking Hazzel to inspect, create, or edit files.", style="dim")
        console.print()
        return
    rule()
    title = Text()
    title.append("  Summary", style="bold white")
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
            line.append("    • ", style="dim")
            line.append(name, style="bold")
            if detail:
                line.append(f"  {detail}", style="dim")
            console.print(line)
        console.print()
    print_response(console, summary)
    console.print()


def show_star_nudge():
    console.print(Text("  If Hazzel helps, star us: github.com/mukundzha/hazzel", style="dim"))
    console.print()


def show_copied(msg="Copied to clipboard."):
    console.print()
    line = Text()
    line.append("  ", style="dim")
    line.append(msg, style="bold white")
    console.print(line)
    console.print()


def show_export(path):
    console.print()
    line = Text()
    line.append("  Exported to ", style="dim")
    line.append(str(path), style="bold white")
    console.print(line)
    console.print()


def show_logout():
    text = Text()
    text.append("  ○ ", style=f"bold {DIM_COLOR}")
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
            text.append("❯ ", style=f"bold {HAZZEL_COLOR}")
            text.append(f"{i+1}. ", style="dim")
            text.append(pad, style="bold bright_white")
        else:
            text.append("  ")
            text.append(f"{i+1}. ", style="dim")
            text.append(pad, style="bold bright_white")
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
