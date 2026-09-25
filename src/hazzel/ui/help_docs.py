"""Help overview and full docs panels."""

import re
import sys

from rich.text import Text

from . import _state as _st
from ._state import DIM_COLOR, USER_COLOR
from . import input as _ui_input

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
        ("/jobs", "background jobs [id|wait id|kill id|clear]"),
        ("/usage", "show token usage"),
        ("/undo", "undo last change, keeps your edits [preview]"),
        ("/redo", "reapply undone change [preview]"),
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
    from hazzel.docs import get_sections

    sections = get_sections()
    _ui_input.rule()
    head = Text()
    head.append("  Hazzel docs", style="white")
    head.append(f"  ·  {len(sections)} sections", style=DIM_COLOR)
    _st.console.print(head)
    _ui_input.rule()
    for i, (title, lines) in enumerate(sections):
        _st.console.print()
        sec = Text()
        sec.append(f"  {i + 1:02d}  ", style=DIM_COLOR)
        sec.append(title, style="white")
        _st.console.print(sec)
        for line in lines:
            row = Text()
            row.append("       ", style=DIM_COLOR)
            row.append_text(_doc_line(line))
            _st.console.print(row)
    _st.console.print()
    _ui_input.rule()


def _print_help_inline():
    _st.console.print()
    _st.console.print(Text(_HELP_INTRO, style="white"))
    for title, rows in _HELP_SECTIONS:
        _st.console.print()
        _st.console.print(Text(title.lower(), style="dim"))
        _st.console.print(_help_table(rows))
    _st.console.print()
    _st.console.print(Text(_HELP_FOOT, style="dim"))
    _st.console.print(Text(f"  {_STAR_LINE}", style="dim"))
    _st.console.print()


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
            _st.console.print()
            _st.console.print(Text(_HELP_INTRO, style="white"))
            for title, rows in _HELP_SECTIONS:
                _st.console.print()
                _st.console.print(Text(title.lower(), style="dim"))
                _st.console.print(_help_table(rows))
            _st.console.print()
            _st.console.print(Text(_HELP_FOOT, style="dim"))
            _st.console.print()
            _st.console.print(Text("esc to cancel", style="dim"))
            _st.console.print()
            sys.stdout.flush()
            while True:
                ch = _ui_input._read_key(fd)
                if not ch:
                    continue
                if ch in ("\x03", "q", "Q"):
                    break
                if ch == "\x1b":
                    if select.select([fd], [], [], 0.05)[0]:
                        ch2 = _ui_input._read_key(fd)
                        if ch2 == "\x1b":
                            break
                        if ch2 in ("[", "O"):
                            while select.select([fd], [], [], 0.03)[0]:
                                _ui_input._read_key(fd)
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
