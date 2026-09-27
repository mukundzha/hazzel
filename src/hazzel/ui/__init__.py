"""Terminal UI — split from a single 2.6k-line ui.py, zero behavior change.

Map (each module owns one concern, shared mutable state lives in _state):

- _state.py .... console (HazzelConsole), colors, spinner/stream/turn flags
- input.py ..... welcome header, terminal width + rule helpers, path shortening,
                SLASH_COMMANDS + @mention completion + fuzzy match,
                prompt_toolkit input loop + Windows fallback
- stream.py .... spinner, streaming tokens, turn lifecycle, quiet/print flags
- messages.py .. tool rows, context meter, history, confirm, assistant text
- git/ ......... diff, status, log, commit flow, file viewer, review
- help_docs.py . /help + /docs, prompts
- usage.py ..... usage panels, summary, clipboard, export, budget
- selectors.py . model/skill selectors, api keys, logout, skills

``from hazzel import ui`` keeps working — this package re-exports every
public name the old module had.

Submodules load on first attribute access. ``rich`` costs ~150ms to import
and the whole package exists to draw with it, so `hazzel --version` and
`hazzel -p` never pay for a terminal renderer they don't draw on.
"""

# ruff: noqa: F401 — re-export shim, every import is part of the ui API.
import importlib as _importlib
import sys as _sys
from types import ModuleType as _ModuleType

# public name -> submodule that defines it
_EXPORTS = {
    "DIM_COLOR": "_state", "ERROR_COLOR": "_state", "HAZZEL_COLOR": "_state",
    "SUCCESS_COLOR": "_state", "USER_COLOR": "_state", "HazzelConsole": "_state",
    "is_no_color": "_state",

    "MAX_BUFFER_CHARS": "input", "MAX_BUFFER_LINES": "input",
    "MAX_DIFF_DISPLAY_LINES": "input", "MAX_PASTE_CHARS": "input",
    "MAX_PASTE_LINES": "input", "MENTION_COLOR": "input", "MENTION_RESET": "input",
    "SLASH_COMMANDS": "input", "VIEW_MAX_LINES": "input", "_accept_mention": "input",
    "_active_mention": "input", "_all_project_files": "input", "_clip_paste": "input",
    "_file_cache": "input", "_filter_slash_commands": "input", "_fuzzy_score": "input",
    "_highlight_mentions": "input", "_hw": "input", "_is_tty": "input",
    "_mention_candidates": "input", "_read_key": "input", "_rule_ansi": "input",
    "_short_path": "input", "_show_header": "input", "_skill_candidates": "input",
    "_visible_len": "input", "_visual_rows": "input", "_win_input": "input",
    "_win_redraw": "input", "get_input": "input", "rule": "input", "show_welcome": "input",

    "_GIT_STATUS_ICONS": "git", "_LOG_LINE_RE": "git", "_LOG_SUBJECT_RE": "git",
    "_LOG_TYPE_COLORS": "git", "_count_diff_marks": "git", "_style_log_refs": "git",
    "_style_log_subject": "git", "prompt_diff_selection": "git",
    "prompt_suggest_action": "git", "prompt_suggest_edit": "git", "show_diff": "git",
    "show_file_viewer": "git", "show_git_commit": "git", "show_git_diff": "git",
    "show_git_file_diff": "git", "show_git_file_list": "git", "show_git_log": "git",
    "show_git_status": "git", "show_git_suggest": "git", "show_review": "git",

    "_HELP_FOOT": "help_docs", "_HELP_INTRO": "help_docs", "_HELP_SECTIONS": "help_docs",
    "_STAR_LINE": "help_docs", "_doc_line": "help_docs", "_help_table": "help_docs",
    "_print_help_inline": "help_docs", "_show_help_tab": "help_docs",
    "show_docs": "help_docs", "show_help": "help_docs",

    "_format_elapsed": "messages", "_format_result_preview": "messages",
    "_PREVIEW_MAX_CHARS": "messages", "_PREVIEW_MAX_LINES": "messages",
    "_relativize_detail": "messages", "_short_detail": "messages",
    "_split_preview_rows": "messages", "confirm": "messages", "format_context_meter": "messages",
    "format_context_plain": "messages", "prompt_goal_criteria": "messages",
    "show_cleared": "messages", "show_copied": "messages", "show_error": "messages",
    "show_export": "messages", "show_hazzel_message": "messages", "show_history": "messages",
    "show_model_selected": "messages", "show_reasoning": "messages", "show_summary": "messages",
    "show_tool": "messages", "show_undo": "messages", "show_redo": "messages",
    "show_undo_preview": "messages", "show_user_command": "messages",

    "_mask_key": "selectors", "prompt_api_key": "selectors", "select_model": "selectors",
    "select_skill": "selectors", "show_logout": "selectors", "show_skill_detail": "selectors",
    "show_skills": "selectors",

    "_print_usage_inline": "usage", "_show_usage_tab": "usage", "_usage_body": "usage",
    "show_budget_warning": "usage", "show_by_model": "usage", "show_turn_usage": "usage",
    "show_usage": "usage", "show_usage_range": "usage",

    "_live_body": "stream", "_live_reasoning": "stream", "_pause_loader": "stream",
    "_render_reasoning": "stream", "_resume_loader": "stream", "begin_stream": "stream",
    "begin_turn": "stream", "end_stream": "stream", "end_turn": "stream",
    "hide_loader": "stream", "is_print_mode": "stream", "is_quiet": "stream",
    "push_reasoning_token": "stream", "push_stream_token": "stream",
    "set_auto_approve": "stream", "set_print_mode": "stream", "set_quiet": "stream",
    "show_loader": "stream", "stream_stats": "stream", "was_thinking_streamed": "stream",
}

_LOADED = set()

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


def _load(module_name):
    if module_name not in _LOADED:
        _LOADED.add(module_name)
        _importlib.import_module(f".{module_name}", __name__)
    return _sys.modules[f"{__name__}.{module_name}"]


def __getattr__(name: str):
    if name in _STATE_NAMES:
        return getattr(_load("_state"), name)
    origin = _EXPORTS.get(name)
    if origin is not None:
        value = getattr(_load(origin), name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_EXPORTS) | _STATE_NAMES)


class _UIModule(_ModuleType):
    """Module subclass so `ui.<state> = X` forwards to _state (live)."""

    def __setattr__(self, name, value):
        if name in _STATE_NAMES:
            setattr(_load("_state"), name, value)
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
    "show_redo",
    "show_undo_preview",
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
