import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time

from hazzel import ui
from hazzel import config
from hazzel.config import resolve_project_path
from hazzel.mentions import expand_mentions, strip_mentions
from hazzel.providers import get_provider
from hazzel.providers.base import Usage
from hazzel.tokens import estimate_messages, estimate_text
from hazzel.tools.apply_edits import apply_edits
from hazzel.tools.edit_file import edit_file
from hazzel.tools.fetch_url import fetch_url
from hazzel.tools.git_branch import git_branch
from hazzel.tools.git_commit import git_commit
from hazzel.tools.git_diff import git_diff
from hazzel.tools.git_status import git_status
from hazzel.tools.github_pr import github_pr
from hazzel.tools.list_files import list_files
from hazzel.tools.read_file import read_file
from hazzel.tools.review_diff import review_diff
from hazzel.tools.run_command import run_command
from hazzel.tools.search_files import missing_file_message, search_files
from hazzel.tools.write_file import write_file

SYSTEM_PROMPT = """You are Hazzel by Mukund Jha (providers supply only the model). Contact: mukundzha33@gmail.com.
Senior eng agent: think, act, verify. Smallest correct change. Direct, concise, honest.
Efficiency rules: search_files first, never re-read; batch independent calls in one block; stop when done; one verify command max. @path files are pre-attached in context; use them, never re-read them.
Package installs (pip/download): run `pip install <names>` via run_command immediately. Never edit pyproject.toml, requirements, or manifests to install something.
Scope: respect user limits strictly. Do ONLY what was asked — nothing extra, nothing unasked.
Prohibited unless explicitly requested: editing files the user didn't mention, installing/uninstalling packages, running commands, reformatting or refactoring unrelated code, creating docs/tests.
Direct orders (install/read/create/run) execute immediately in one step — no exploration first. Vague tasks may explore, then act.
Verify before claiming success.
In your responses add proper spacing and formatting
Tools: you have EXACTLY these 14 functions and no others: list_files, read_file, search_files, write_file, edit_file, apply_edits, run_command, git_status, git_diff, git_commit, git_branch, github_pr, fetch_url, review_diff. Never call or invent any other tool (no namespaces, no dots, no repobrowser, no print_tree). To list a tree use list_files; to view content use read_file. For multi-file changes prefer one apply_edits call.
Web: fetch_url is read-only — use it for docs, changelogs, and references; never fetch secrets or keys. Always pass the user's question as query so only relevant sentences come back.
Review: review_diff is read-only — call it when the user asks for a review; path takes a file (@file works), codebase=true reviews staged+unstaged together; it returns severity-ranked findings, never edits.
Goal: if a session goal is appended to the user message, steer every step toward it and briefly note progress. When the acceptance looks met, propose clearing the goal.
Git: git_status/git_diff are read-only — call first before editing or committing. Commit only when asked, via git_commit (asks approval, shows diff). Never run raw `git commit/push/reset/clean` via run_command; use the git tools. Never run raw `gh pr create/merge/comment` via run_command; use github_pr.
You are Hazzel, never ChatGPT/Claude/Gemini/DeepSeek/Grok/etc."""
MAX_ITERATIONS = 114

# Approximate token budget for persisted conversation history (excluding the system prompt).
HISTORY_TOKEN_BUDGET = 2400

# Max assistant reply kept between turns; longer replies are compacted.
HISTORY_REPLY_CHARS = 1500

# Tool results larger than this are distilled before being sent back to the model.
MAX_TOOL_RESULT_CHARS = 5000

PROVE_TIMEOUT = 30
PROVE_MARKER = "PROVE-PASS"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory. Use this for any tree/directory listing. Only list_files exists for this.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file (60 numbered lines, page with offset/limit). Use this to view file content.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "offset": {"type": "integer"}, "limit": {"type": "integer"}}, "required": ["path"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Search file contents, returns path:line:text. Always use before reading unknown code.",
            "parameters": {"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}, "regex": {"type": "boolean"}}, "required": ["pattern"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a whole file. Undoable.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Replace one unique anchor (<2k chars) in a file. Undoable.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_edits",
            "description": "Apply up to 10 unique-anchor edits across files atomically with one approval. Undoable.",
            "parameters": {"type": "object", "properties": {"edits": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}}}, "required": ["edits"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command from the project root. Read-only cmds run without approval; all else asks. Optional timeout (1-120s), cwd (project-relative dir), description. Large output is truncated with full log to tmp.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "number"}, "cwd": {"type": "string"}, "description": {"type": "string"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Show git working-tree status (branch + porcelain). Read-only.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Show git diff for unstaged or staged changes. Read-only.",
            "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}, "path": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Commit changes. Omit message or pass 'suggest' to auto-draft from diff (asks y/e/n). Shows diff and asks approval. Use instead of raw git commit.",
            "parameters": {"type": "object", "properties": {"message": {"type": "string"}, "files": {"type": "array", "items": {"type": "string"}}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "Branches + sync: current, list, log, create, switch, push, pull, sync. Writes ask approval. Never use --force.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "name": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_pr",
            "description": "GitHub PRs via gh: list, view, diff, checks (read-only) and comment, create, merge, close (ask approval). Needs gh auth login.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "number": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "method": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Read a public http(s) URL (docs, references, changelogs). Read-only, returns condensed relevant sentences up to max_chars. Always pass the user's question as query.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "max_chars": {"type": "integer"}, "query": {"type": "string"}}, "required": ["url"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_diff",
            "description": "Review git changes like a senior engineer: verdict plus severity-ranked findings with fixes. Read-only, never edits. Use staged=true for staged changes, path for one file, codebase=true for staged+unstaged together.",
            "parameters": {"type": "object", "properties": {"staged": {"type": "boolean"}, "path": {"type": "string"}, "codebase": {"type": "boolean"}}},
        },
    },
]

TOOL_NAMES = frozenset(["list_files", "read_file", "search_files", "write_file", "edit_file", "apply_edits", "run_command", "git_status", "git_diff", "git_commit", "git_branch", "github_pr", "fetch_url", "review_diff"])

PLAN_TOOL_NAMES = frozenset(["list_files", "read_file", "search_files", "git_status", "git_diff", "git_branch", "github_pr", "fetch_url", "review_diff"])

PLAN_TOOLS = [t for t in TOOLS if t.get("function", {}).get("name") in PLAN_TOOL_NAMES]

PLAN_ADDENDUM = (
    "\n\nPlan mode is ON (read-only). Explore with your tools, then present a short numbered plan "
    "and stop — no file changes, no commands, no commits. The user approves with /plan off."
)

PLAN_BLOCKED_MESSAGE = (
    "Blocked: plan mode is on (read-only). Explore and present a numbered plan instead — "
    "no writes, runs, or commits until the user runs /plan off."
)


def _active_tools():
    try:
        if config.is_plan_enabled():
            return PLAN_TOOLS
    except Exception:
        pass
    return TOOLS


def _plan_blocked(tool_name, arguments):
    if tool_name in ("write_file", "edit_file", "apply_edits", "run_command", "git_commit"):
        return True
    if tool_name == "git_branch":
        action = ""
        if isinstance(arguments, dict):
            action = str(arguments.get("action", "") or "current").lower()
        return action not in ("current", "list", "log")
    if tool_name == "github_pr":
        action = ""
        if isinstance(arguments, dict):
            action = str(arguments.get("action", "") or "list").lower()
        return action not in ("list", "view", "diff", "checks")
    return False

_TOOL_ALIASES = {
    "print_tree": "list_files",
    "printtree": "list_files",
    "tree": "list_files",
    "listfiles": "list_files",
    "ls": "list_files",
    "readdir": "list_files",
    "cat": "read_file",
    "open": "read_file",
    "show": "read_file",
    "view": "read_file",
    "read": "read_file",
    "grep": "search_files",
    "find": "search_files",
    "search": "search_files",
    "create": "write_file",
    "write": "write_file",
    "new_file": "write_file",
    "patch": "edit_file",
    "edit": "edit_file",
    "multi_edit": "apply_edits",
    "multiedit": "apply_edits",
    "bulk_edit": "apply_edits",
    "apply": "apply_edits",
    "bash": "run_command",
    "shell": "run_command",
    "exec": "run_command",
    "run": "run_command",
    "status": "git_status",
    "diff": "git_diff",
    "commit": "git_commit",
    "branch": "git_branch",
    "pr": "github_pr",
    "pull_request": "github_pr",
    "pullrequest": "github_pr",
    "fetch": "fetch_url",
    "fetch_url": "fetch_url",
    "curl": "fetch_url",
    "wget": "fetch_url",
    "browse": "fetch_url",
    "web": "fetch_url",
    "review": "review_diff",
    "review_diff": "review_diff",
    "code_review": "review_diff",
    "codereview": "review_diff",
    "critique": "review_diff",
}


def _normalize_tool_name(name):
    raw = (name or "").strip()
    if raw in TOOL_NAMES:
        return raw
    canon = raw.lower().strip()
    for sep in (".", ":", "/"):
        if sep in canon:
            canon = canon.split(sep)[-1]
    canon = re.sub(r"[^a-z0-9]+", "_", canon).strip("_")
    if canon in TOOL_NAMES:
        return canon
    return _TOOL_ALIASES.get(canon)


def _coerce_tool_args(tool_name, arguments):
    if not isinstance(arguments, dict):
        return {}
    args = dict(arguments)
    if tool_name == "list_files" and "path" not in args:
        for k in ("dir", "directory", "folder", "file", "filename", "target"):
            if args.get(k) is not None:
                args["path"] = args.pop(k)
                break
        args.setdefault("path", ".")
    elif tool_name == "read_file":
        for k in ("file", "filename", "filepath", "target"):
            if "path" not in args and args.get(k) is not None:
                args["path"] = args[k]
                break
    elif tool_name == "search_files":
        for k in ("query", "text", "term", "regex_pattern"):
            if "pattern" not in args and args.get(k) is not None:
                args["pattern"] = args[k]
                break
        args.setdefault("path", ".")
    elif tool_name == "fetch_url":
        if "url" not in args:
            for k in ("link", "href", "target", "page", "site", "path"):
                if args.get(k) is not None:
                    args["url"] = args[k]
                    break
        if "query" not in args:
            for k in ("question", "q"):
                if args.get(k) is not None:
                    args["query"] = args[k]
                    break
    elif tool_name == "review_diff":
        if "path" not in args:
            for k in ("file", "filename", "filepath", "target"):
                if args.get(k) is not None:
                    args["path"] = args[k]
                    break
        args.setdefault("path", ".")
        if "codebase" not in args and str(args.get("scope", "")).lower() in ("codebase", "all", "whole"):
            args["codebase"] = True
    elif tool_name in ("write_file", "edit_file") and "path" not in args:
        for k in ("file", "filename", "filepath", "target"):
            if args.get(k) is not None:
                args["path"] = args[k]
                break
    elif tool_name == "apply_edits":
        if "edits" not in args:
            for k in ("changes", "items", "files"):
                if isinstance(args.get(k), list):
                    args["edits"] = args[k]
                    break
        if isinstance(args.get("edits"), list):
            fixed = []
            for item in args["edits"]:
                if not isinstance(item, dict):
                    fixed.append(item)
                    continue
                item = dict(item)
                if "path" not in item:
                    for k in ("file", "filename", "filepath", "target"):
                        if item.get(k) is not None:
                            item["path"] = item[k]
                            break
                fixed.append(item)
            args["edits"] = fixed
    elif tool_name == "run_command":
        if "command" not in args:
            for k in ("cmd", "script", "bash", "shell"):
                if args.get(k) is not None:
                    args["command"] = args[k]
                    break
        if "cwd" not in args:
            for k in ("dir", "directory", "working_dir", "workdir"):
                if args.get(k) is not None:
                    args["cwd"] = args[k]
                    break
    elif tool_name == "github_pr":
        for k in ("pr", "id", "target"):
            if "number" not in args and args.get(k) is not None:
                args["number"] = args[k]
                break
        args.setdefault("action", "list")
    return args


def _extract_bad_tool(error_text):
    match = re.search(r"tool\s+['\"`]([^'\"`]+)['\"`]", error_text or "", re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r'\{"name":\s*"([^"]+)"', error_text or "")
    if match:
        return match.group(1)
    return ""


def _is_tool_validation_error(error):
    text = str(error).lower()
    return "tool" in text and any(k in text for k in ["not in", "validation", "toolusefailed", "invalidrequest", "unknown tool", "no such tool"])


def _format_contact_error(error):
    text = str(error)
    if "rate limit" in text.lower():
        return text
    return f"Unable to contact the model: {error}"


def _safe_chat(provider, task_messages, tools, retries=1):
    try:
        response = provider.chat(task_messages, tools)
    except Exception as error:
        if retries <= 0 or not _is_tool_validation_error(error):
            raise
        bad = _extract_bad_tool(str(error))
        valid = ", ".join(sorted(TOOL_NAMES))
        task_messages.append({
            "role": "user",
            "content": f"System correction: '{bad or 'that tool'}' does not exist. Valid tools are exactly: {valid}. Retry using only those (list trees with list_files), or answer directly with no tool call.",
        })
        try:
            response = provider.chat(task_messages, tools)
        except Exception as retry_error:
            if not _is_tool_validation_error(retry_error):
                raise
            task_messages.append({
                "role": "user",
                "content": f"Final correction: answer directly with NO tool calls. Plain text only, valid tools were: {valid}.",
            })
            response = provider.chat(task_messages, [])
        try:
            _record_usage(response, task_messages)
        except Exception:
            pass
        return response
    for tc in getattr(response, "tool_calls", None) or []:
        fixed = _normalize_tool_name(tc.name)
        if fixed is not None and fixed != tc.name:
            tc.name = fixed
            try:
                parsed = json.loads(tc.arguments) if tc.arguments else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            tc.arguments = json.dumps(_coerce_tool_args(fixed, parsed))
    return response


def _normalize_response_tools(response):
    for tc in getattr(response, "tool_calls", None) or []:
        fixed = _normalize_tool_name(tc.name)
        if fixed is not None and fixed != tc.name:
            tc.name = fixed
            try:
                parsed = json.loads(tc.arguments) if tc.arguments else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                parsed = {}
            tc.arguments = json.dumps(_coerce_tool_args(fixed, parsed))
    return response


def _safe_stream_chat(provider, task_messages, tools):
    try:
        ui.begin_stream()
        try:
            response = provider.stream(task_messages, tools, on_token=ui.push_stream_token)
        finally:
            try:
                ui.end_stream()
            except Exception:
                pass
    except KeyboardInterrupt:
        raise
    except Exception:
        return _safe_chat(provider, task_messages, tools)
    _normalize_response_tools(response)
    _note_reasoning(getattr(response, "reasoning", None))
    if getattr(response, "tool_calls", None):
        try:
            ui.show_loader("Working…")
        except Exception:
            pass
    return response


def _distill_result(text):
    lines = str(text).splitlines()
    cleaned = []
    blanks = 0
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            blanks += 1
            if blanks > 1:
                continue
        else:
            blanks = 0
        cleaned.append(line[:240])
        if len(cleaned) >= 80:
            break
    out = "\n".join(cleaned).strip()
    if len(out) > MAX_TOOL_RESULT_CHARS:
        head = MAX_TOOL_RESULT_CHARS - 700
        out = out[:head] + f"\n[…{len(out) - MAX_TOOL_RESULT_CHARS} chars skipped…]\n" + out[-700:]
    elif len(lines) > 80:
        out += f"\n[…{len(lines) - 80} lines skipped…]"
    return out or "(empty)"


def run_tool(tool_name, arguments):
    fixed = _normalize_tool_name(tool_name)
    if fixed is not None and fixed != tool_name:
        tool_name = fixed
        arguments = _coerce_tool_args(tool_name, arguments if isinstance(arguments, dict) else {})
    try:
        if config.is_plan_enabled() and _plan_blocked(tool_name, arguments):
            return PLAN_BLOCKED_MESSAGE
    except Exception:
        pass
    try:
        if tool_name == "list_files":
            return list_files(arguments["path"])
        if tool_name == "read_file":
            return read_file(arguments["path"], arguments.get("offset", 1) or 1, arguments.get("limit", 60))
        if tool_name == "search_files":
            return search_files(arguments["pattern"], arguments.get("path", "."), bool(arguments.get("regex", False)))
        if tool_name == "write_file":
            return write_file(arguments["path"], arguments["content"])
        if tool_name == "edit_file":
            return edit_file(arguments["path"], arguments["old_text"], arguments["new_text"])
        if tool_name == "apply_edits":
            return apply_edits(arguments["edits"])
        if tool_name == "run_command":
            cmd = arguments["command"]
            low = str(cmd).strip().lower()
            if low.startswith("git commit") or low.startswith("git push") or "reset --hard" in low or low.startswith("git clean"):
                return "Blocked: use git_commit / git_branch tools instead of raw git writes. Destructive git (reset --hard, clean, --force) is disabled."
            if "gh pr create" in low or "gh pr merge" in low or "gh pr comment" in low or "gh pr close" in low:
                return "Blocked: use github_pr tool instead of raw `gh pr` writes."
            return run_command(cmd, timeout=arguments.get("timeout"), cwd=arguments.get("cwd"), description=arguments.get("description"))
        if tool_name == "git_status":
            return git_status()
        if tool_name == "git_diff":
            return git_diff(arguments.get("staged", False), arguments.get("path", ".") or ".")
        if tool_name == "git_commit":
            return git_commit(arguments.get("message"), arguments.get("files"))
        if tool_name == "git_branch":
            return git_branch(arguments.get("action", "current") or "current", arguments.get("name", "") or "")
        if tool_name == "fetch_url":
            return fetch_url(arguments["url"], arguments.get("max_chars", 2000), arguments.get("query", ""))
        if tool_name == "review_diff":
            return review_diff(arguments.get("staged", False), arguments.get("path", ".") or ".", arguments.get("codebase", False))
        if tool_name == "github_pr":
            return github_pr(
                arguments.get("action", "list") or "list",
                arguments.get("number", "") or "",
                arguments.get("title", "") or "",
                arguments.get("body", "") or "",
                arguments.get("method", "squash") or "squash",
            )
        return f"Unknown tool: {tool_name}. Valid tools: {', '.join(sorted(TOOL_NAMES))}."
    except KeyboardInterrupt:
        raise
    except KeyError as error:
        return f"Missing required argument: {error}. Check the tool's parameters and retry with all required fields."
    except Exception as error:
        return f"Tool error: {error}. Retry, or try a smaller step."


def _build_summary(trace, response_content, user_input):
    try:
        return _build_summary_inner(trace, response_content, user_input)
    except Exception:
        return "Done."


def _build_summary_inner(trace, response_content, user_input):
    inspected = []
    created = []
    changed = []
    deleted = []
    actions = []
    verifs = []
    warnings = []
    for t in trace:
        name = t["tool"]
        detail = t["detail"]
        success = t["success"]
        result = t["result"]
        if name == "read_file" and success and not t.get("cached"):
            inspected.append(detail)
        elif name in ("list_files", "search_files", "git_status", "git_diff", "git_branch", "github_pr") and success and not t.get("cached"):
            inspected.append(detail or name)
        elif name == "write_file" and success:
            created.append(detail)
            actions.append(f"{name} {detail}".strip())
        elif name in ("edit_file", "apply_edits") and success:
            changed.append(detail)
            actions.append(f"{name} {detail}".strip())
        elif name == "git_commit" and success:
            actions.append(f"git_commit {detail}".strip())
            changed.append(detail or "commit")
        elif name == "run_command":
            actions.append(f"run_command {detail}".strip())
            if detail.strip().startswith("prove ") or any(k in detail for k in ["pytest", "test", "build", "lint", "typecheck", "ruff", "mypy", "tsc", "npm", "cargo"]):
                if t["exit_code"] is not None:
                    verifs.append(f"{detail} — {'passed' if success else 'failed'} (exit {t['exit_code']})")
                else:
                    verifs.append(f"{detail} — {'passed' if success else 'failed'}")
            if not success:
                warnings.append(f"{detail} — {result[:140].replace(chr(10), ' ')}")
            if "rm " in detail or "unlink" in detail:
                deleted.append(detail)
        elif not success:
            warnings.append(f"{name} {detail} — {result[:140].replace(chr(10), ' ')}")

    def _clean(items):
        seen = []
        for x in items:
            x = (x or "").strip()
            if not x or x in seen or x == "." or x == "/":
                continue
            seen.append(x)
        return seen

    inspected = _clean(inspected)
    created = _clean(created)
    changed = _clean(changed)

    def _fmt(items):
        return ", ".join(f"`{x}`" for x in items[:4]) if items else ""

    paras = []

    clean_input = user_input.strip().lstrip("/").strip().rstrip(".")
    is_slash = user_input.strip().startswith("/") and len(clean_input) < 3

    if inspected and not created and not changed and len(inspected) <= 3:
        paras.append(f"You asked Hazzel to read `{inspected[0]}` and re-edit it.")
        paras.append(f"Hazzel inspected {_fmt(inspected)}.")
        if response_content and "empty" in response_content.lower():
            paras.append(f"`{inspected[0]}` is currently empty.")
        else:
            snippet = response_content.strip().splitlines()[0][:180] if response_content else ""
            if snippet and len(snippet) > 12:
                paras.append(snippet)
    elif trace:
        if not is_slash and clean_input:
            paras.append(f"You asked Hazzel to {clean_input}.")
        parts = []
        if inspected:
            parts.append(f"inspected {_fmt(inspected)}")
        if created:
            parts.append(f"created {_fmt(created)}")
        if changed:
            parts.append(f"updated {_fmt(changed)}")
        if parts:
            paras.append("Hazzel " + ", ".join(parts) + ".")
        if verifs:
            paras.append("Verified via " + ", ".join(verifs[:2]) + ".")
        elif created or changed:
            paras.append("No automated verification was run in this turn.")
        if response_content and response_content.strip() and "empty" not in response_content.lower():
            snippet = response_content.strip().splitlines()[0][:200]
            if snippet and snippet not in paras and len(snippet) > 15:
                paras.append(snippet)
    else:
        if not is_slash and clean_input:
            paras.append(f"You asked: {clean_input}")
        paras.append("Hazzel answered directly — no file changes were needed.")

    if warnings:
        warn = warnings[0].replace("Command cancelled", "Cancelled").replace(" — ", " — ")
        paras.append(f"Note: `{warn[:120]}`")

    return "\n\n".join(p for p in paras if p.strip())


def _compact_reply(content):
    content = (content or "Done.").strip()
    if len(content) > HISTORY_REPLY_CHARS:
        content = content[:HISTORY_REPLY_CHARS] + "…"
    return content


def _commit_history(messages, user_input, content):
    # Only the user request and the compact final answer are kept between turns.
    # Tool calls and tool results stay inside the turn so history stays small.
    user_input = user_input.strip()[:500]
    messages.append({"role": "user", "content": user_input})
    messages.append({"role": "assistant", "content": _compact_reply(content)})

    # Drop the oldest user/assistant pairs together to keep role alternation intact.
    while len(messages) > 3 and sum(len(m.get("content") or "") for m in messages[1:]) // 4 > HISTORY_TOKEN_BUDGET:
        del messages[1:3]


_session_usage = {"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": 0}
_last_turn_usage = {"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": False}


def get_session_usage():
    return dict(_session_usage)


def get_last_turn_usage():
    return dict(_last_turn_usage)


def get_last_reasoning():
    joined = "\n\n".join(_turn_reasoning).strip()
    return joined or None


def reset_usage():
    _session_usage.update({"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": 0})
    _last_turn_usage.update({"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": False})


def _record_usage(response, task_messages):
    global _last_turn_usage
    usage = getattr(response, "usage", None)
    if usage and (usage.input_tokens or usage.output_tokens):
        delta = {"input": usage.input_tokens, "output": usage.output_tokens, "cached": usage.cached_tokens}
        estimated = False
    else:
        delta = {"input": estimate_messages(task_messages, TOOLS), "output": estimate_text(getattr(response, "content", None))}
        delta["cached"] = 0
        usage = Usage(input_tokens=delta["input"], output_tokens=delta["output"], estimated=True)
        response.usage = usage
        estimated = True
    for key in ("input", "output", "cached"):
        _session_usage[key] += delta[key]
        _last_turn_usage[key] += delta[key]
    _session_usage["calls"] += 1
    _last_turn_usage["calls"] += 1
    if estimated:
        _session_usage["estimated"] += 1
        _last_turn_usage["estimated"] = True
    return delta


# Last file the user touched, so pronouns like "delete it" resolve without an LLM call.
_LAST_TARGET = None

# In-turn working copy is distilled once it grows past this (~tokens).
TURN_TOKEN_BUDGET = 12000


def reset_conversation_state():
    reset_usage()
    global _LAST_TARGET
    _LAST_TARGET = None
    _turn_reasoning.clear()


def _note_target(target):
    global _LAST_TARGET
    if target:
        _LAST_TARGET = target


def _looks_like_path(target):
    return "." in target or "/" in target


_turn_reasoning = []


def _note_reasoning(text):
    if (text or "").strip():
        _turn_reasoning.append(text.strip())


def _update_last_target(trace):
    for t in reversed(trace or []):
        if t.get("tool") in ("read_file", "write_file", "edit_file") and t.get("detail"):
            _note_target(t["detail"])
            return
        if t.get("tool") == "run_command":
            detail = (t.get("detail") or "").strip()
            if detail.startswith("rm ") and t.get("success"):
                parts = detail[3:].strip().split()
                if parts:
                    _note_target(parts[-1].strip("'\""))
                    return


def _enforce_turn_budget(task_messages):
    while sum(len(m.get("content") or "") for m in task_messages) // 4 > TURN_TOKEN_BUDGET:
        distilled = False
        for m in task_messages:
            if m.get("role") == "tool":
                content = m.get("content") or ""
                if len(content) > 350 and "…distilled…" not in content:
                    m["content"] = content[:280] + "\n[…distilled…]"
                    distilled = True
                    break
        if not distilled:
            break


def _prove_changed_files(trace):
    files = []
    for t in trace or []:
        if t.get("tool") in ("write_file", "edit_file", "apply_edits") and t.get("success") and t.get("detail"):
            for part in str(t["detail"]).split(","):
                detail = part.strip()
                if detail and detail not in files:
                    files.append(detail)
    return files[:3]


def _prove_already_verified(trace):
    for t in trace or []:
        if t.get("tool") == "run_command" and t.get("success"):
            detail = str(t.get("detail") or "")
            if detail.strip().startswith("prove "):
                return True
            if any(k in detail for k in ["pytest", "test", "build", "lint", "typecheck", "ruff", "mypy", "tsc", "npm", "cargo"]):
                return True
    return False


def _detect_repo_harness():
    root = config.PROJECT_ROOT
    try:
        if (root / "package.json").is_file():
            return ["npm", "test", "--silent"]
        if (root / "Cargo.toml").is_file():
            return ["cargo", "test", "--quiet"]
        if (root / "go.mod").is_file():
            return ["go", "test", "./..."]
        if (root / "pytest.ini").is_file() or (root / "tests").is_dir():
            return [sys.executable, "-m", "pytest", "-q"]
    except OSError:
        pass
    return None


def _prove_env():
    env = dict(os.environ)
    root = str(config.PROJECT_ROOT)
    src = os.path.join(root, "src")
    path = root if not os.path.isdir(src) else root + os.pathsep + src
    if env.get("PYTHONPATH"):
        path = path + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = path
    return env


def _should_prove(trace, response_content):
    try:
        if not config.is_prove_enabled():
            return False
    except Exception:
        return False
    if not response_content or not response_content.strip():
        return False
    files = _prove_changed_files(trace)
    if not files:
        return False
    if not any(f.endswith(".py") for f in files) and _detect_repo_harness() is None:
        return False
    if _prove_already_verified(trace):
        return False
    return True


def _extract_prove_code(text):
    text = text or ""
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text.strip()


def _run_harness(detail, command):
    try:
        started = time.monotonic()
        proc = subprocess.run(
            command,
            cwd=str(config.PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=PROVE_TIMEOUT,
            env=_prove_env(),
        )
        elapsed = time.monotonic() - started
    except subprocess.TimeoutExpired:
        result = f"Command timed out after {PROVE_TIMEOUT} seconds"
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    except KeyboardInterrupt:
        return {"tool": "run_command", "args": {}, "detail": detail, "result": "Prove cancelled by user", "success": False, "exit_code": None}
    except Exception as error:
        result = f"Prove failed: {error}"
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    output = proc.stdout if proc.stdout else proc.stderr
    output = output or "Command completed with no output."
    if len(output) > 3000:
        output = output[:1000] + f"\n[…{len(output) - 2000} chars skipped…]\n" + output[-2000:]
    success = proc.returncode == 0
    if proc.returncode != 0:
        output = f"Command failed (exit {proc.returncode}):\n{output}"
    result = _distill_result(output)
    ui.show_tool("run_command", detail, success=success, exit_code=proc.returncode, elapsed=elapsed)
    return {"tool": "run_command", "args": {"command": " ".join(command)}, "detail": detail, "result": result, "success": success, "exit_code": proc.returncode}


def _run_prove(trace, response_content, task_messages):
    files = _prove_changed_files(trace)
    if not files:
        return None
    harness = None
    if not any(f.endswith(".py") for f in files):
        harness = _detect_repo_harness()
        if harness is None:
            return None
    detail = f"prove {' '.join(files)}".strip()
    if harness:
        cmd = list(harness)
        if cmd and os.path.basename(str(cmd[0])).startswith("python"):
            cmd = cmd[1:]
        action = f"{' '.join(cmd)}  ·  repo suite"
    else:
        action = "smoke script → /tmp  ·  happy path only"
    try:
        if not ui.confirm_prove(files, action):
            return None
    except Exception:
        return None
    ui.show_loader("Proving…")
    if harness:
        return _run_harness(detail, harness)
    code = ""
    try:
        provider = get_provider()
        prompt = (
            "Write one self-contained Python smoke script for these changed files: "
            + ", ".join(files)
            + ". Happy path only, 3-5 asserts max. Import from the project, no network, no extra deps. "
            + f"Print '{PROVE_MARKER}' on success. Reply with code only, preferably a ```python block."
        )
        prove_messages = [
            {"role": "system", "content": "You write minimal passing smoke checks. Code only."},
            {"role": "user", "content": prompt},
        ]
        resp = provider.chat(prove_messages, [])
        try:
            _record_usage(resp, task_messages + prove_messages)
        except Exception:
            pass
        code = _extract_prove_code(getattr(resp, "content", None))
    except KeyboardInterrupt:
        return {"tool": "run_command", "args": {}, "detail": detail, "result": "Prove cancelled by user", "success": False, "exit_code": None}
    except Exception as error:
        result = f"Prove generation failed: {error}"
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    if not code or len(code) < 10:
        result = "Prove generation returned empty script."
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    tmp_path = ""
    try:
        fd, tmp_path = tempfile.mkstemp(prefix="hazzel-prove-", suffix=".py")
        os.close(fd)
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code + "\n")
        prove_started = time.monotonic()
        proc = subprocess.run(
            [sys.executable, tmp_path],
            cwd=str(config.PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=PROVE_TIMEOUT,
            env=_prove_env(),
        )
        prove_elapsed = time.monotonic() - prove_started
        output = proc.stdout if proc.stdout else proc.stderr
        output = output or "Command completed with no output."
        if len(output) > 3000:
            output = output[:1000] + f"\n[…{len(output) - 2000} chars skipped…]\n" + output[-2000:]
        success = proc.returncode == 0 and PROVE_MARKER in (proc.stdout or "")
        if proc.returncode != 0:
            result = f"Command failed (exit {proc.returncode}):\n{output}"
        elif not success:
            result = f"Smoke check ran but {PROVE_MARKER} not found:\n{output}"
        else:
            result = output
        result = _distill_result(result)
        ui.show_tool("run_command", detail, success=success, exit_code=proc.returncode, elapsed=prove_elapsed)
        return {"tool": "run_command", "args": {"command": detail}, "detail": detail, "result": result, "success": success, "exit_code": proc.returncode}
    except subprocess.TimeoutExpired:
        result = f"Command timed out after {PROVE_TIMEOUT} seconds"
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    except KeyboardInterrupt:
        return {"tool": "run_command", "args": {}, "detail": detail, "result": "Prove cancelled by user", "success": False, "exit_code": None}
    except Exception as error:
        result = f"Prove failed: {error}"
        ui.show_tool("run_command", detail, success=False)
        return {"tool": "run_command", "args": {}, "detail": detail, "result": result, "success": False, "exit_code": None}
    finally:
        try:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass


def _fast_reply(messages, user_input, reply, trace):
    _commit_history(messages, user_input, reply)
    return reply, trace, _build_summary(trace, reply, user_input)


def _fast_trace(tool, detail, result, success):
    return [{"tool": tool, "args": {}, "detail": detail, "result": result, "success": success, "exit_code": None}]


def _plan_defers():
    try:
        return config.is_plan_enabled()
    except Exception:
        return False


def _fast_delete(messages, user_input, target):
    if _plan_defers():
        return None
    try:
        resolved = resolve_project_path(target)
    except ValueError as error:
        return _fast_reply(messages, user_input, str(error), [])
    if not resolved.exists():
        reply = f"No such file: {target}."
        return _fast_reply(messages, user_input, reply, _fast_trace("run_command", f"rm {target}", reply, False))
    result = run_tool("run_command", {"command": f"rm {shlex.quote(target)}"})
    success = not result.lower().startswith(("command failed", "command cancelled", "command timed out", "tool error"))
    reply = f"{target} has been removed." if success else result
    if success:
        _note_target(target)
    return _fast_reply(messages, user_input, reply, _fast_trace("run_command", f"rm {target}", result, success))


def _fast_create(messages, user_input, target):
    if _plan_defers():
        return None
    try:
        if resolve_project_path(target).exists():
            reply = f"{target} already exists."
            return _fast_reply(messages, user_input, reply, _fast_trace("write_file", target, reply, False))
    except ValueError as error:
        return _fast_reply(messages, user_input, str(error), [])
    result = run_tool("write_file", {"path": target, "content": ""})
    success = not result.lower().startswith(("tool error", "content too large"))
    reply = f"Created {target}." if success else result
    if success:
        _note_target(target)
    return _fast_reply(messages, user_input, reply, _fast_trace("write_file", target, result, success))


def _fast_read(messages, user_input, target):
    try:
        resolved = resolve_project_path(target)
    except ValueError as error:
        reply = str(error)
        return _fast_reply(messages, user_input, reply, _fast_trace("read_file", target, reply, False))
    if not resolved.exists():
        reply = missing_file_message(target)
        return _fast_reply(messages, user_input, reply, _fast_trace("read_file", target, reply, False))
    if not resolved.is_file():
        reply = "Path is not a file"
        return _fast_reply(messages, user_input, reply, _fast_trace("read_file", target, reply, False))
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        reply = "File is binary; preview not supported"
        return _fast_reply(messages, user_input, reply, _fast_trace("read_file", target, reply, False))
    lines = text.splitlines()
    total = len(lines)
    if total == 0:
        return _fast_reply(messages, user_input, f"`{target}` is empty.", _fast_trace("read_file", target, "(empty file)", True))
    shown = lines[:ui.VIEW_MAX_LINES] if len(lines) > ui.VIEW_MAX_LINES else lines
    ui.show_file_viewer(target, "\n".join(shown), total, len(shown))
    _note_target(target)
    reply = f"Showed `{target}` ({total} lines) above — ask me anything about it."
    return _fast_reply(messages, user_input, reply, _fast_trace("read_file", target, f"({total} lines shown via viewer)", True))


def _fast_list(messages, user_input, target):
    result = run_tool("list_files", {"path": target})
    if isinstance(result, list):
        result = "\n".join(result) or "(empty directory)"
    success = not str(result).lower().startswith(("path does not exist", "path is not", "path is outside"))
    return _fast_reply(messages, user_input, str(result), _fast_trace("list_files", target, str(result), success))


_PKG_RE = re.compile(r"^[A-Za-z0-9_.\-]+(\[[A-Za-z0-9_,.\-]+\])?(==[A-Za-z0-9_.\-]+)?$")
_PKG_CONNECTORS = frozenset({"and", "with", "plus", "&", "+", "package", "packages", "library", "libraries", "module", "modules"})


def _parse_package_names(raw):
    pkgs = []
    for tok in re.split(r"[\s,]+", (raw or "").strip()):
        cleaned = tok.strip("'\"").rstrip(".,!?;:)}\"'")
        if not cleaned:
            continue
        if cleaned.lower() in _PKG_CONNECTORS:
            continue
        if not _PKG_RE.match(cleaned):
            return None
        if cleaned.lower() in {"a", "an", "the", "for", "me", "it", "them", "this", "that", "two", "three", "both", "all", "everything", "dependencies", "requirements", "latest", "version"}:
            return None
        pkgs.append(cleaned)
    return pkgs or None


def _fast_install(messages, user_input, pkgs):
    if _plan_defers():
        return None
    command = "pip install " + " ".join(shlex.quote(p) for p in pkgs)
    result = run_tool("run_command", {"command": command})
    success = not str(result).lower().startswith(("command failed", "command cancelled", "command timed out", "tool error"))
    if success:
        reply = f"Installed {', '.join(pkgs)}."
    else:
        reply = str(result)
    return _fast_reply(messages, user_input, reply, _fast_trace("run_command", command, str(result), success))


def _fast_run(messages, user_input, command):
    if _plan_defers():
        return None
    result = run_tool("run_command", {"command": command})
    if isinstance(result, list):
        result = "\n".join(result) or "(empty directory)"
    success = not str(result).lower().startswith(("command failed", "command cancelled", "command timed out", "tool error"))
    return _fast_reply(messages, user_input, str(result), _fast_trace("run_command", command, str(result), success))


def try_fast_path(messages, user_input):
    # Trivial turns are handled locally with zero LLM calls. Anything ambiguous
    # returns None and falls through to the model.
    text = (user_input or "").strip()
    text = re.sub(r'@(?:"([^"]+)"|\'([^\']+)\'|`([^`]+)`|(\S+))', lambda m: (m.group(1) or m.group(2) or m.group(3) or m.group(4) or "").rstrip(".,!?;:)]"), text).strip()
    if not text or text.startswith("/"):
        return None
    low = text.lower().strip(" .!?")
    if low in ("hi", "hello", "hey", "yo", "sup", "howdy", "hiya", "greetings"):
        return _fast_reply(messages, user_input, "Hello! How can I help you today?", [])
    if low in ("thanks", "thank you", "thx"):
        return _fast_reply(messages, user_input, "You're welcome.", [])
    if len(low) <= 1:
        return _fast_reply(messages, user_input, "I'm Hazzel — tell me what to do (e.g. `read @path`, `run pytest -q`).", [])

    if re.search(r"who\s+(developed|created|built|made|designed)\s+(you|hazzel|this)(\s+(agent|app|tool|program))?\b", low) or re.search(
        r"who'?s\s+your\s+(developer|creator|maker|author|owner|father|dad)\b", low
    ) or re.search(r"\b(your\s+developer|your\s+creator|developed\s+by\s+whom)\b", low):
        return _fast_reply(messages, user_input, "I am Hazzel, developed by Mukund Jha.", [])
    if re.search(r"who\s+is\s+mukund(\s+jha)?\b", low):
        return _fast_reply(messages, user_input, "Mukund Jha is the developer of Hazzel.", [])
    if re.search(r"\b(what\s+is\s+hazzel|is\s+hazzel|tell\s+me\s+about\s+hazzel|about\s+hazzel)\b", low):
        return _fast_reply(
            messages,
            user_input,
            "Hazzel is a small terminal coding agent, not a code editor. It lives in your shell, "
            "inspects your project, edits code, and runs commands through explicit tools.",
            [],
        )
    if re.search(r"^(who\s+are\s+you|what\s+are\s+you|your\s+name|about\s+yourself|introduce\s+yourself)\b", low):
        return _fast_reply(
            messages, user_input, "I am Hazzel, a terminal coding agent developed by Mukund Jha.", []
        )
    if re.search(r"what\s+model\s+are\s+you(\s+on|\s+using|\s+running)?\b", low):
        from hazzel.config import PROVIDER_DISPLAY, get_current_display_name, get_current_provider
        model = get_current_display_name()
        provider = PROVIDER_DISPLAY.get(get_current_provider(), get_current_provider())
        return _fast_reply(
            messages,
            user_input,
            f"I am Hazzel by Mukund Jha, currently running on {model} ({provider}).",
            [],
        )

    match = re.match(r"^(?:(?:now|please)\s+)?(delete|delet|remove|rm|del)\s+(\S+?)[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        target = match.group(2)
        if target.lower() in ("it", "this", "that", "them"):
            target = _LAST_TARGET
            if not target:
                return None
        if not _looks_like_path(target):
            try:
                if not resolve_project_path(target).exists():
                    return None
            except ValueError:
                return None
        return _fast_delete(messages, user_input, target)

    match = re.match(r"^(?:(?:now|please)\s+)?create\s+(?:a\s+)?(?:new\s+)?(?:file\s+)?(?:named\s+|called\s+)?(\S+?)[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        target = match.group(1)
        if target.lower() in ("it", "this", "that") or not _looks_like_path(target):
            return None
        return _fast_create(messages, user_input, target)

    match = re.match(r"^(?:(?:now|please|get|give|show|display)\s+)?context\s+(?:of\s+|for\s+)?(\S+?)[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        if match.group(1).lower().startswith(("http://", "https://")):
            return None
        target = match.group(1)
        if target.lower() in ("it", "this", "that"):
            target = _LAST_TARGET
            if not target:
                return None
        return _fast_read(messages, user_input, target)

    match = re.match(r"^(?:(?:now|please)\s+)?(read|show|open|cat|view)\s+(?:me\s+)?(\S+?)[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        if match.group(2).lower().startswith(("http://", "https://")):
            return None
        if match.group(2).lower() == "files" and match.group(1).lower() == "show":
            return _fast_list(messages, user_input, ".")
        target = match.group(2)
        if target.lower() in ("it", "this", "that"):
            target = _LAST_TARGET
            if not target:
                return None
        return _fast_read(messages, user_input, target)

    match = re.match(r"^(?:(?:now|please)\s+)?(?:list|ls)(?:\s+files)?(?:\s+(\S+?))?[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        return _fast_list(messages, user_input, match.group(1) or ".")

    match = re.match(r"^(?:(?:now|please)\s+)?(?:download|install|pip\s+install)\s+(.+?)[.!?]*\s*$", text, re.IGNORECASE)
    if match:
        pkgs = _parse_package_names(match.group(1))
        if pkgs:
            return _fast_install(messages, user_input, pkgs)

    if re.match(r"^(?:git\s+)?status[.!?]*$", low):
        result = run_tool("git_status", {})
        return _fast_reply(messages, user_input, str(result), _fast_trace("git_status", "status", str(result), True))
    if re.match(r"^(?:git\s+)?diff(?:\s+staged)?[.!?]*$", low):
        staged = "staged" in low
        result = run_tool("git_diff", {"staged": staged})
        return _fast_reply(messages, user_input, str(result), _fast_trace("git_diff", "staged" if staged else "", str(result), True))
    if re.match(r"^(?:git\s+)?log(?:\s+\S+)?[.!?]*$", low):
        result = run_tool("git_branch", {"action": "log"})
        return _fast_reply(messages, user_input, str(result), _fast_trace("git_branch", "log", str(result), True))
    if re.match(r"^(?:git\s+)?branch[.!?]*$", low):
        result = run_tool("git_branch", {"action": "list"})
        return _fast_reply(messages, user_input, str(result), _fast_trace("git_branch", "list", str(result), True))
    if re.match(r"^(?:gh\s+)?pr\s+list[.!?]*$|^list\s+(open\s+)?(prs|pull requests)[.!?]*$", low):
        result = run_tool("github_pr", {"action": "list"})
        return _fast_reply(messages, user_input, str(result), _fast_trace("github_pr", "list", str(result), True))

    match = re.match(r"^(?:(?:now|please)\s+)?(?:run|execute)\s+(.+?)\s*$", text, re.IGNORECASE)
    if match:
        command = match.group(1).strip().rstrip(".!?")
        if command:
            first = command.split()[0].lower() if command.split() else ""
            if first in ("python", "python3", "pytest", "pip", "npm", "npx", "node", "cargo", "go", "make", "git", "ls", "ruff"):
                return _fast_run(messages, user_input, command)
    return None


def _session_goal_note():
    try:
        goal = config.get_goal()
    except Exception:
        return ""
    if not isinstance(goal, dict):
        return ""
    objective = (goal.get("objective") or "").strip()
    if not objective:
        return ""
    note = f"\n\nSession goal: {objective}."
    criteria = (goal.get("criteria") or "").strip()
    if criteria:
        note += f" Acceptance: {criteria}."
    note += " Steer toward it and briefly note progress."
    return note


def goal_run_task():
    try:
        goal = config.get_goal()
    except Exception:
        return None
    if not isinstance(goal, dict):
        return None
    objective = (goal.get("objective") or "").strip()
    if not objective:
        return None
    criteria = (goal.get("criteria") or "").strip() or "use your best judgment"
    return f"Work toward this session goal: {objective}. Acceptance: {criteria}. Start with the first concrete step."


def run(messages, user_input):
    # `messages` holds the system prompt plus compact history from previous turns.
    # Tool traffic for this turn is added to a working copy and never persisted.
    task_messages = messages + [{"role": "user", "content": user_input}]
    if _plan_defers() and task_messages and task_messages[0].get("role") == "system":
        task_messages[0] = {"role": "system", "content": (task_messages[0].get("content") or "") + PLAN_ADDENDUM}

    trace = []
    seen_reads = set()
    _turn_reasoning.clear()
    _last_turn_usage.update({"input": 0, "output": 0, "cached": 0, "calls": 0, "estimated": False})

    ui.begin_turn()

    fast = try_fast_path(messages, user_input)
    if fast is not None:
        ui.end_turn()
        return fast

    mention_context, attached, _, mention_errors = expand_mentions(user_input)
    if mention_context:
        task_messages[-1]["content"] = user_input + "\n\n" + mention_context
        if attached:
            task_messages[-1]["content"] += "\n\nAnswer the user's instruction using the attached files; do not reprint them unless asked."
        for path in attached:
            seen_reads.add(("read_file", str(path), "1", "60", ""))
            seen_reads.add(("read_file", str(path), "", "", ""))
            seen_reads.add(("list_files", str(path), "", "", ""))
            trace.append({"tool": "read_file", "args": {"path": path}, "detail": path, "result": "(attached via @mention)", "success": True, "exit_code": None})
            try:
                ui.show_tool("read_file", path, success=True)
            except Exception:
                pass
        if attached:
            _note_target(attached[0])
        if not strip_mentions(user_input) and attached and not mention_errors:
            ui.end_turn()
            tagged = ", ".join(f"`@{p}`" for p in attached)
            return _fast_reply(messages, user_input, f"Attached {tagged} — tell me what to do with it (explain, review, edit …).", trace)

    goal_note = _session_goal_note()
    if goal_note:
        task_messages[-1]["content"] += goal_note

    try:
        provider = get_provider()
        response = _safe_stream_chat(provider, task_messages, _active_tools())
        try:
            _record_usage(response, task_messages)
        except Exception:
            pass
    except KeyboardInterrupt:
        ui.end_turn()
        msg = "Cancelled."
        _commit_history(messages, user_input, msg)
        return msg, trace, _build_summary(trace, msg, user_input)
    except Exception as error:
        ui.end_turn()
        msg = _format_contact_error(error)
        summary = _build_summary([], msg, user_input)
        return msg, trace, summary

    prev_sig = None
    stall_count = 0
    nudged = False
    inspect_streak = 0
    nudged_act = False

    for _ in range(MAX_ITERATIONS):
        if not response.tool_calls:
            break

        task_messages.append({
            "role": "assistant",
            "content": response.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in response.tool_calls
            ],
        })

        round_start = len(trace)
        for tc in response.tool_calls:
            tool_name = tc.name

            try:
                if tc.arguments and len(tc.arguments) > 20000:
                    raise ValueError("tool arguments too large")
                arguments = json.loads(tc.arguments) if tc.arguments else {}

                if not isinstance(arguments, dict):
                    arguments = {}

            except (json.JSONDecodeError, ValueError):
                result = "Invalid tool arguments."

                task_messages.append({
                    "role": "tool",
                    "content": result,
                    "tool_call_id": tc.id,
                })

                trace.append({
                    "tool": tool_name,
                    "args": {},
                    "detail": "",
                    "result": result,
                    "success": False,
                    "exit_code": None,
                })

                continue

            detail = arguments.get(
                "pattern",
                arguments.get("path", arguments.get("url", arguments.get("command", arguments.get("message", arguments.get("title", arguments.get("action", "")))))),
            )
            if tool_name == "apply_edits" and isinstance(arguments, dict):
                paths = []
                for item in arguments.get("edits", []) or []:
                    if isinstance(item, dict):
                        p = item.get("path") or item.get("file") or ""
                        if p and p not in paths:
                            paths.append(p)
                detail = ", ".join(paths[:4])
            if tool_name == "github_pr" and isinstance(arguments, dict):
                sub = str(arguments.get("number", "") or "").strip() or str(arguments.get("title", "") or "").strip()
                if sub:
                    detail = f"{arguments.get('action', 'list')} {sub}".strip()

            cache_key = None
            cached = False
            elapsed = None
            try:
                if tool_name in ("read_file", "list_files", "search_files", "git_status", "git_diff", "fetch_url", "review_diff"):
                    cache_key = (tool_name, str(detail), str(arguments.get("offset", "")), str(arguments.get("limit", "")), str(arguments.get("pattern", "")))
                    if cache_key in seen_reads:
                        result = "(already in context above; do not re-read)"
                        cached = True
                    else:
                        seen_reads.add(cache_key)
                        started = time.monotonic()
                        result = run_tool(tool_name, arguments)
                        elapsed = time.monotonic() - started
                else:
                    result = run_tool(tool_name, arguments)
            except KeyboardInterrupt:
                raise
            except Exception as error:
                result = f"Tool error: {error}. Retry, or try a smaller step."

            if isinstance(result, list):
                result = "\n".join(result) or "(empty directory)"
            else:
                result = str(result)

            result = _distill_result(result)

            low = result.lower()

            success = not low.startswith((
                "unknown tool",
                "missing required",
                "tool error",
                "invalid",
                "command failed",
                "command cancelled",
                "command timed out",
                "edit cancelled",
                "edits cancelled",
                "applied nothing",
                "write cancelled",
                "commit cancelled",
                "branch cancelled",
                "pr cancelled",
                "blocked:",
                "not a git repo",
            ))

            match = re.search(r"exit code (\d+)", low)
            exit_code = int(match.group(1)) if match else None

            try:
                ui.show_tool(
                    tool_name,
                    detail,
                    success=success,
                    exit_code=exit_code,
                    cached=cached,
                    elapsed=elapsed,
                )
            except Exception:
                pass

            task_messages.append({
                "role": "tool",
                "content": result,
                "tool_call_id": tc.id,
            })

            trace.append({
                "tool": tool_name,
                "args": arguments,
                "detail": detail,
                "result": result,
                "success": success,
                "exit_code": exit_code,
                "cached": cached,
            })

        round_entries = trace[round_start:]
        sig = tuple(sorted((t.get("tool"), str(t.get("detail"))) for t in round_entries))
        progressed = any(t.get("tool") in ("write_file", "edit_file", "apply_edits", "git_commit", "git_branch") and t.get("success") for t in round_entries)
        if sig and sig == prev_sig and not progressed:
            stall_count += 1
        else:
            stall_count = 0
        prev_sig = sig
        if stall_count >= 2:
            if not nudged:
                nudged = True
                stall_count = 0
                prev_sig = None
                task_messages.append({
                    "role": "user",
                    "content": "You are repeating the same tool calls without progress. Answer now using the context gathered so far, or make a clearly different call.",
                })
            else:
                task_messages.append({
                    "role": "user",
                    "content": "Stop calling tools. Answer now with NO tool calls, using only the context gathered so far.",
                })
                try:
                    final = _safe_stream_chat(provider, task_messages, [])
                    _record_usage(final, task_messages)
                    content = (final.content or "").strip() or "Done."
                except Exception:
                    ui.end_turn()
                    msg = "Stopped: repeating the same tool calls without progress. Try a smaller step or rephrase."
                    summary = _build_summary(trace, msg, user_input)
                    _update_last_target(trace)
                    _commit_history(messages, user_input, msg)
                    return msg, trace, summary
                ui.end_turn()
                _update_last_target(trace)
                _commit_history(messages, user_input, content)
                summary = _build_summary(trace, content, user_input)
                return content, trace, summary

        only_inspect = bool(round_entries) and all(t.get("tool") in ("list_files", "read_file", "search_files", "git_status", "git_diff") for t in round_entries)
        if only_inspect:
            inspect_streak += 1
        else:
            inspect_streak = 0
        if inspect_streak >= 4 and not nudged_act:
            nudged_act = True
            inspect_streak = 0
            task_messages.append({
                "role": "user",
                "content": "You have explored enough. Take ONLY the requested action now (or answer) — no more listing, reading, or searching unless the request is genuinely ambiguous.",
            })

        try:
            ui.show_loader("Working…")
        except Exception:
            pass

        _enforce_turn_budget(task_messages)
        try:
            response = _safe_stream_chat(provider, task_messages, _active_tools())
            try:
                _record_usage(response, task_messages)
            except Exception:
                pass
        except KeyboardInterrupt:
            ui.end_turn()
            msg = "Cancelled."
            _update_last_target(trace)
            _commit_history(messages, user_input, msg)
            return msg, trace, _build_summary(trace, msg, user_input)
        except Exception as error:
            ui.end_turn()

            msg = _format_contact_error(error)
            summary = _build_summary(trace, msg, user_input)

            return msg, trace, summary

    else:
        ui.end_turn()

        msg = f"Stopped: maximum tool iterations ({MAX_ITERATIONS}) reached. Try splitting the task into smaller steps."
        summary = _build_summary(trace, msg, user_input)
        _update_last_target(trace)
        _commit_history(messages, user_input, msg)

        return msg, trace, summary

    if _should_prove(trace, response.content):
        try:
            entry = _run_prove(trace, response.content, task_messages)
        except Exception:
            entry = None
        if entry is not None:
            trace.append(entry)

    ui.end_turn()

    _update_last_target(trace)
    _commit_history(messages, user_input, response.content)

    summary = _build_summary(
        trace,
        response.content,
        user_input,
    )

    return response.content, trace, summary

