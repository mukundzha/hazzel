"""Terminal UI — split from a single 2.6k-line ui.py, zero behavior change.

Map (each module owns one concern, shared mutable state lives in _state):

- _state.py .... console (HazzelConsole), colors, spinner/stream/turn flags
- input.py ..... welcome header, terminal width + rule helpers, path shortening,
                SLASH_COMMANDS + @mention completion + fuzzy match,
                prompt_toolkit input loop + Windows fallback
- stream.py .... spinner, streaming tokens, turn lifecycle, quiet/print flags
- panels.py .... turn cards, tool rows, context meter, history, confirm, diff,
                git panels, review, log, viewer, undo, prompts, /help + /docs,
                usage panels, summary, clipboard, export, selectors, skills,
                api keys, logout

``from hazzel import ui`` keeps working — this package re-exports every
public name the old module had.
"""

# ruff: noqa: F401 — re-export shim, every import is part of the ui API.
import sys as _sys
from types import ModuleType as _ModuleType

from . import _state as _st
from ._state import (
    DIM_COLOR,
    ERROR_COLOR,
    HAZZEL_COLOR,
    SUCCESS_COLOR,
    USER_COLOR,
    HazzelConsole,
    is_no_color,
)
from .input import (
    MAX_BUFFER_CHARS,
    MAX_BUFFER_LINES,
    MAX_DIFF_DISPLAY_LINES,
    MAX_PASTE_CHARS,
    MAX_PASTE_LINES,
    MENTION_COLOR,
    MENTION_RESET,
    SLASH_COMMANDS,
    VIEW_MAX_LINES,
    _accept_mention,
    _active_mention,
    _all_project_files,
    _clip_paste,
    _file_cache,
    _filter_slash_commands,
    _fuzzy_score,
    _highlight_mentions,
    _hw,
    _is_tty,
    _mention_candidates,
    _read_key,
    _rule_ansi,
    _short_path,
    _show_header,
    _skill_candidates,
    _visible_len,
    _visual_rows,
    _win_input,
    _win_redraw,
    get_input,
    rule,
    show_welcome,
)
from .git import (
    _GIT_STATUS_ICONS,
    _LOG_LINE_RE,
    _LOG_SUBJECT_RE,
    _LOG_TYPE_COLORS,
    _count_diff_marks,
    _style_log_refs,
    _style_log_subject,
    prompt_diff_selection,
    prompt_suggest_action,
    prompt_suggest_edit,
    show_diff,
    show_file_viewer,
    show_git_commit,
    show_git_diff,
    show_git_file_diff,
    show_git_file_list,
    show_git_log,
    show_git_status,
    show_git_suggest,
    show_review,
)
from .help_docs import (
    _HELP_FOOT,
    _HELP_INTRO,
    _HELP_SECTIONS,
    _STAR_LINE,
    _doc_line,
    _help_table,
    _print_help_inline,
    _show_help_tab,
    show_docs,
    show_help,
)
from .messages import (
    _format_elapsed,
    _format_result_preview,
    _PREVIEW_MAX_CHARS,
    _PREVIEW_MAX_LINES,
    _relativize_detail,
    _short_detail,
    _split_preview_rows,
    confirm,
    format_context_meter,
    format_context_plain,
    prompt_goal_criteria,
    show_cleared,
    show_copied,
    show_error,
    show_export,
    show_hazzel_message,
    show_history,
    show_model_selected,
    show_reasoning,
    show_summary,
    show_tool,
    show_undo,
    show_user_command,
)
from .selectors import (
    _mask_key,
    prompt_api_key,
    select_model,
    select_skill,
    show_logout,
    show_skill_detail,
    show_skills,
)
from .usage import (
    _print_usage_inline,
    _show_usage_tab,
    _usage_body,
    show_budget_warning,
    show_by_model,
    show_turn_usage,
    show_usage,
    show_usage_range,
)
from .stream import (
    _live_body,
    _live_reasoning,
    _pause_loader,
    _render_reasoning,
    _resume_loader,
    begin_stream,
    begin_turn,
    end_stream,
    end_turn,
    hide_loader,
    is_print_mode,
    is_quiet,
    push_reasoning_token,
    push_stream_token,
    set_auto_approve,
    set_print_mode,
    set_quiet,
    show_loader,
    stream_stats,
    was_thinking_streamed,
)

# Mutable globals live in _state. They are NOT copied into this package's
# __dict__ (that would go stale); instead attribute access is proxied so
# `ui.console = X`, `ui._quiet`, `ui._loader`, etc. keep working for old
# call sites and tests that monkeypatch `hazzel.ui`.
_STATE_NAMES = frozenset(
    {
        "console",
        "_loader",
        "_stream_buffer",
        "_stream_started",
        "_stream_first_at",
        "_stream_tokens",
        "_stream_last_paint",
        "_reason_buffer",
        "_thinking_streamed",
        "_thinking_was_live",
        "_tool_rows",
        "_turn_started",
        "_quiet",
        "_print_mode",
        "_auto_approve",
    }
)


def __getattr__(name: str):
    if name in _STATE_NAMES:
        return getattr(_st, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + list(_STATE_NAMES))


class _UIModule(_ModuleType):
    """Module subclass so `ui.<state> = X` forwards to _state (live)."""

    def __setattr__(self, name, value):
        if name in _STATE_NAMES:
            setattr(_st, name, value)
        super().__setattr__(name, value)


_sys.modules[__name__].__class__ = _UIModule

__all__ = [
    "DIM_COLOR",
    "ERROR_COLOR",
    "HAZZEL_COLOR",
    "SUCCESS_COLOR",
    "USER_COLOR",
    "HazzelConsole",
    "console",
    "is_no_color",
    "show_welcome",
    "rule",
    "get_input",
    "begin_turn",
    "show_loader",
    "hide_loader",
    "begin_stream",
    "push_reasoning_token",
    "push_stream_token",
    "stream_stats",
    "end_stream",
    "end_turn",
    "set_quiet",
    "is_quiet",
    "set_print_mode",
    "is_print_mode",
    "set_auto_approve",
    "was_thinking_streamed",
    "show_hazzel_message",
    "show_reasoning",
    "format_context_plain",
    "format_context_meter",
    "show_tool",
    "show_user_command",
    "show_history",
    "show_error",
    "confirm",
    "show_diff",
    "show_git_status",
    "show_git_diff",
    "show_git_file_list",
    "show_git_file_diff",
    "prompt_diff_selection",
    "show_git_commit",
    "show_review",
    "show_git_suggest",
    "prompt_suggest_action",
    "prompt_suggest_edit",
    "show_git_log",
    "show_file_viewer",
    "show_undo",
    "prompt_goal_criteria",
    "show_model_selected",
    "show_cleared",
    "show_help",
    "show_docs",
    "show_usage",
    "show_turn_usage",
    "show_budget_warning",
    "show_usage_range",
    "show_by_model",
    "show_summary",
    "show_copied",
    "show_export",
    "show_skills",
    "show_skill_detail",
    "show_logout",
    "select_model",
    "select_skill",
    "prompt_api_key",
]
