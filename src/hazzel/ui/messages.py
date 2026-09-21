"""Assistant messages, tool rows, context meter, history, confirm/prompts."""


from rich.text import Text

from . import _state as _st
from ._state import DIM_COLOR, ERROR_COLOR, HAZZEL_COLOR, SUCCESS_COLOR, is_no_color
from . import input as _ui_input
from . import stream as _ui_stream

def show_turn_from_trace(user_command, trace, summary):
    return None


def show_turn_card(user_command, tool_rows, summary_lines, model="Hazzel 1.3.2", root="~/hazzel"):
    return None


def show_hazzel_message(message):
    _ui_stream.hide_loader()
    if not message or not message.strip():
        return
    # Deferred import: formatter pulls rich.syntax + pygments (~30ms),
    # only needed once the first assistant message is actually rendered.
    from hazzel.formatter import print_response

    print_response(_st.console, message)


def show_reasoning(reasoning):
    _ui_stream.hide_loader()
    if _st._thinking_was_live:
        _st._thinking_was_live = False
        return
    text = (reasoning or "").strip()
    if not text:
        return
    _st.console.print(Text(text, style="dim"))
    _st.console.print()


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

        from hazzel import config as _config

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
    if is_no_color():
        return format_context_plain(used, window)
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


def _push_tool_row(row, refresh=True):
    _st._tool_rows.append(row)
    while len(_st._tool_rows) > _ui_input._MAX_TOOL_ROWS:
        _st._tool_rows.pop(0)
    if refresh and _st._loader is not None:
        _st._loader.update(_ui_stream._live_body(None))


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
    if _st._quiet:
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
    if result is not None and not _st._quiet:
        preview = _format_result_preview(result)
        if preview:
            preview_rows = _split_preview_rows(preview)

    if _st._loader is not None:
        _push_tool_row(text)
    else:
        _st.console.print(text)

    if preview_rows is not None:
        for row in preview_rows:
            if _st._loader is not None:
                _push_tool_row(row, refresh=False)
            else:
                _st.console.print(row)
        if _st._loader is not None:
            _st._loader.update(_ui_stream._live_body(None))


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
    _st.console.print(text)


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
            _ui_input.rule()
            text = Text()
            text.append("❯ ", style="bold")
            text.append(content, style="white")
            _st.console.print(text)
            _ui_input.rule()
            _st.console.print()
        else:
            show_hazzel_message(content)
            _st.console.print()


def show_error(message):
    text = Text()
    text.append("  ! ", style=ERROR_COLOR)
    text.append(message, style=ERROR_COLOR)
    _st.console.print(text)


def confirm(prompt):
    if _st._print_mode:
        return _st._auto_approve
    was_active = _ui_stream._pause_loader()
    try:
        answer = input(f"\n{prompt} [y/N]: ")
    except (EOFError, KeyboardInterrupt):
        return False
    finally:
        _ui_stream._resume_loader(was_active)
    clean = _ui_input._ANSI_RE.sub("", answer or "").strip().lower()
    return clean in {"y", "yes"}


def show_undo(restored):
    if not restored:
        _st.console.print(Text("  Nothing to undo.", style=DIM_COLOR))
        _st.console.print()
        return
    for key, action in restored:
        text = Text()
        text.append("  ✓ ", style=SUCCESS_COLOR)
        text.append(f"{action} ", style="white")
        text.append(_short_detail(key), style=DIM_COLOR)
        _st.console.print(text)
    _st.console.print()


def prompt_goal_criteria():
    was_active = _ui_stream._pause_loader()
    try:
        answer = input("  Done looks like what? [Enter to skip]: ")
    except (EOFError, KeyboardInterrupt):
        return ""
    finally:
        _ui_stream._resume_loader(was_active)
    return _ui_input._ANSI_RE.sub("", answer or "").strip()


def show_model_selected(display_name, provider_display):
    text = Text()
    text.append("  ✓ ", style=SUCCESS_COLOR)
    text.append(display_name, style="white")
    text.append(f" ({provider_display})", style=DIM_COLOR)
    _st.console.print(text)
    _st.console.print()


def show_cleared():
    text = Text()
    text.append("  ○ ", style=DIM_COLOR)
    text.append("Conversation cleared", style="dim")
    _st.console.print(text)
    _st.console.print()


def show_summary(summary, trace=None):
    if not summary:
        show_error("No implementation yet — run a task first.")
        _st.console.print("  Try asking Hazzel to inspect, create, or edit files.", style="dim")
        _st.console.print()
        return
    _ui_input.rule()
    title = Text()
    title.append("  summary", style="white")
    title.append("  ·  last implementation", style="dim")
    _st.console.print(title)
    _st.console.print()
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
            _st.console.print(line)
        _st.console.print()
    from hazzel.formatter import print_response  # deferred: pygments chain (~30ms)

    print_response(_st.console, summary)
    _st.console.print()


def show_copied(msg="Copied to clipboard."):
    _st.console.print()
    line = Text()
    line.append("  ", style="dim")
    line.append(msg, style="white")
    _st.console.print(line)
    _st.console.print()


def show_export(path):
    _st.console.print()
    line = Text()
    line.append("  Exported to ", style="dim")
    line.append(str(path), style="white")
    _st.console.print(line)
    _st.console.print()
