"""Backward-compat shim — moved into messages/git/help_docs/usage/selectors.

Import from those modules directly. This file re-exports everything so
``from hazzel.ui.panels import show_tool`` keeps working.
"""

# ruff: noqa: F401 — re-export shim.
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
