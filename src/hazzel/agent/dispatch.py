import re
import time

from hazzel import config
from hazzel import jobs as _bgjobs
from hazzel import skills as _skills
from hazzel import mcp as _mcp
from hazzel.tools.apply_edits import apply_edits
from hazzel.tools.edit_file import edit_file
from hazzel.tools.fetch_url import fetch_url
from hazzel.tools.git_commit import git_commit
from hazzel.tools.git_diff import git_diff
from hazzel.tools.git_status import git_status
from hazzel.tools.web_search import web_search
from hazzel.tools.list_files import list_files
from hazzel.tools.read_file import read_file
from hazzel.tools.run_command import run_command
from hazzel.tools.search_files import search_files
from hazzel.tools.write_file import write_file

from .toolspec import (
    MAX_TOOL_RESULT_CHARS,
    PARALLEL_SAFE,
    PLAN_BLOCKED_MESSAGE,
    PLAN_TOOLS,
    PRINT_BLOCKED_MESSAGE,
    TOOL_NAMES,
    TOOLS,
)


# Print (non-interactive) approvals. None = interactive REPL session.
# False = `hazzel -p` without -y: mutating tools are blocked, model sees read-only tools.
# True = `hazzel -p -y`: mutating tools run with approvals pre-granted.
_print_approve = None


def set_print_approvals(approve):
    global _print_approve
    _print_approve = None if approve is None else bool(approve)
    return _print_approve


def is_print_readonly():
    return _print_approve is False


def _active_tools():
    try:
        if is_print_readonly():
            return PLAN_TOOLS
        if config.is_plan_enabled():
            return PLAN_TOOLS
    except Exception:
        pass
    return TOOLS


def _plan_blocked(tool_name, arguments):
    if tool_name in ("write_file", "edit_file", "apply_edits", "run_command", "git_commit"):
        return True
    if tool_name == "jobs":
        # list/poll/wait are read-only; kill stops a process, clear drops state.
        try:
            action = str((arguments or {}).get("action") or "list").strip().lower()
        except Exception:
            action = "list"
        return action in ("kill", "stop", "cancel", "clear", "clean", "purge")
    if tool_name == "mcp":
        # Discovery is read-only; calls may run third-party code.
        try:
            action = str((arguments or {}).get("action") or "list").strip().lower()
        except Exception:
            action = "list"
        return action == "call"
    return False


def _is_parallel_safe(tool_name, arguments):
    return tool_name in PARALLEL_SAFE


def _tool_detail(tool_name, arguments):
    detail = arguments.get(
        "pattern",
        arguments.get("path", arguments.get("url", arguments.get("command", arguments.get("message", "")))),
    )
    if tool_name == "apply_edits" and isinstance(arguments, dict):
        paths = []
        for item in arguments.get("edits", []) or []:
            if isinstance(item, dict):
                p = item.get("path") or item.get("file") or ""
                if p and p not in paths:
                    paths.append(p)
        detail = ", ".join(paths[:4])
    if tool_name == "web_search" and isinstance(arguments, dict):
        detail = str(arguments.get("query", "") or "").strip()[:80]
    if tool_name == "fetch_url" and isinstance(arguments, dict):
        targets = arguments.get("urls") or []
        if isinstance(targets, list) and targets:
            detail = ", ".join(str(t) for t in targets[:2])
    if tool_name == "skill" and isinstance(arguments, dict):
        detail = str(arguments.get("name", "") or "").strip()
    if tool_name == "mcp" and isinstance(arguments, dict):
        action = str(arguments.get("action", "") or "list").strip() or "list"
        server = str(arguments.get("server", "") or "").strip()
        tool = str(arguments.get("tool", "") or "").strip()
        detail = action
        if server:
            detail += f" {server}"
            if tool:
                detail += f"/{tool}"
    if tool_name == "run_command" and isinstance(arguments, dict):
        bg = arguments.get("background")
        if bg is True or str(bg or "").strip().lower() in ("1", "true", "yes", "on"):
            detail = f"{detail} &"
    if tool_name == "jobs" and isinstance(arguments, dict):
        action = str(arguments.get("action", "") or "list").strip() or "list"
        job_id = arguments.get("job_id", "")
        detail = action
        if str(job_id or "").strip():
            detail += f" {job_id}"
    return detail


def _tool_cache_key(tool_name, arguments, detail):
    if tool_name in ("read_file", "list_files", "search_files", "git_status", "git_diff", "web_search", "fetch_url", "skill"):
        return (tool_name, str(detail), str(arguments.get("offset", "")), str(arguments.get("limit", "")), str(arguments.get("pattern", "")))
    if tool_name == "mcp":
        # Discovery is cacheable; calls may have side effects — never cache.
        try:
            action = str((arguments or {}).get("action") or "list").strip().lower()
        except Exception:
            return None
        if action != "list":
            return None
        return (tool_name, str(detail), "", "", "")
    if tool_name == "jobs":
        # Output changes as jobs run — never cache.
        return None
    return None


def _run_one_tool(tool_name, arguments):
    started = time.monotonic()
    try:
        result = run_tool(tool_name, arguments)
    except KeyboardInterrupt:
        raise
    except Exception as error:
        return f"Tool error: {error}. Retry, or try a smaller step.", time.monotonic() - started
    if isinstance(result, list):
        result = "\n".join(result) or "(empty directory)"
    else:
        result = str(result)
    return result, time.monotonic() - started


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


def _finalize_result(result):
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
        "blocked:",
        "not a git repo",
    ))
    match = re.search(r"exit code (\d+)", low)
    exit_code = int(match.group(1)) if match else None
    return result, success, exit_code

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
    "fetch": "fetch_url",
    "fetch_url": "fetch_url",
    "fetch_urls": "fetch_url",
    "curl": "fetch_url",
    "wget": "fetch_url",
    "browse": "fetch_url",
    "web": "fetch_url",
    "web_search": "web_search",
    "websearch": "web_search",
    "search_web": "web_search",
    "google": "web_search",
    "ddg": "web_search",
    "skills": "skill",
    "load_skill": "skill",
    "loadskill": "skill",
    "job": "jobs",
    "jobs_list": "jobs",
    "bg_jobs": "jobs",
    "mcp_list": "mcp",
    "mcplist": "mcp",
    "list_mcp": "mcp",
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
    elif tool_name == "web_search":
        if "query" not in args:
            for k in ("q", "question", "text", "term", "pattern"):
                if args.get(k) is not None:
                    args["query"] = args[k]
                    break
    elif tool_name == "fetch_url":
        if "url" not in args and "urls" not in args:
            for k in ("link", "href", "target", "page", "site", "path"):
                if args.get(k) is not None:
                    args["url"] = args[k]
                    break
        if "query" not in args:
            for k in ("question", "q"):
                if args.get(k) is not None:
                    args["query"] = args[k]
                    break
    elif tool_name == "skill":
        if "name" not in args:
            for k in ("skill", "skill_name", "target"):
                if args.get(k) is not None:
                    args["name"] = args[k]
                    break
        args.setdefault("name", "")
    elif tool_name == "git_diff":
        if not isinstance(args.get("staged"), bool):
            args["staged"] = str(args.get("staged", "")).lower() in ("1", "true", "yes", "staged")
        if not isinstance(args.get("path"), str) or not args.get("path"):
            args["path"] = "."
    elif tool_name == "git_commit":
        if not isinstance(args.get("message"), str):
            args["message"] = ""
        if "files" in args and not isinstance(args.get("files"), (list, str)):
            args["files"] = None
    elif tool_name == "mcp":
        if "action" not in args:
            for k in ("op", "cmd", "verb"):
                if args.get(k) is not None:
                    args["action"] = args[k]
                    break
        args.setdefault("action", "list")
        if "server" not in args:
            for k in ("server_name", "name", "target"):
                if args.get(k) is not None:
                    args["server"] = args[k]
                    break
        args.setdefault("server", "")
        if "tool" not in args:
            for k in ("tool_name",):
                if args.get(k) is not None:
                    args["tool"] = args[k]
                    break
        args.setdefault("tool", "")
        if "arguments" not in args:
            for k in ("args", "params", "input", "parameters"):
                if isinstance(args.get(k), dict):
                    args["arguments"] = args[k]
                    break
        if not isinstance(args.get("arguments"), dict):
            args["arguments"] = {}
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
        if "background" not in args:
            for k in ("bg", "detach", "detached", "async_", "run_in_background"):
                if args.get(k) is not None:
                    args["background"] = args[k]
                    break
        bg = args.get("background", False)
        if isinstance(bg, str):
            args["background"] = bg.strip().lower() in ("1", "true", "yes", "on", "background", "bg")
        elif bg is None:
            args["background"] = False
        else:
            args["background"] = bool(bg)
    elif tool_name == "jobs":
        if "action" not in args:
            for k in ("op", "cmd", "verb"):
                if args.get(k) is not None:
                    args["action"] = args[k]
                    break
        args.setdefault("action", "list")
        if "job_id" not in args:
            for k in ("id", "job", "jid"):
                if args.get(k) is not None:
                    args["job_id"] = args[k]
                    break
        args.setdefault("job_id", None)
        try:
            args["limit"] = int(args.get("limit", 40))
        except (TypeError, ValueError):
            args["limit"] = 40
        try:
            args["timeout"] = float(args.get("timeout", 30))
        except (TypeError, ValueError):
            args["timeout"] = 30
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


def run_tool(tool_name, arguments):
    fixed = _normalize_tool_name(tool_name)
    if fixed is not None and fixed != tool_name:
        tool_name = fixed
        arguments = _coerce_tool_args(tool_name, arguments if isinstance(arguments, dict) else {})
    try:
        if config.is_plan_enabled() and _plan_blocked(tool_name, arguments):
            return PLAN_BLOCKED_MESSAGE
        if is_print_readonly() and _plan_blocked(tool_name, arguments):
            return PRINT_BLOCKED_MESSAGE
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
            if low.startswith("git commit") or "reset --hard" in low or low.startswith("git clean"):
                return "Blocked: use git_commit instead of raw git writes. Destructive git (reset --hard, clean) is disabled."
            return run_command(cmd, timeout=arguments.get("timeout"), cwd=arguments.get("cwd"), description=arguments.get("description"), background=arguments.get("background", False))
        if tool_name == "jobs":
            action = arguments.get("action", "list")
            if not isinstance(action, str) or not action.strip():
                action = "list"
            return _bgjobs.jobs_tool(action, arguments.get("job_id"), arguments.get("limit", 40), arguments.get("timeout", 30))
        if tool_name == "git_status":
            return git_status()
        if tool_name == "git_diff":
            return git_diff(arguments.get("staged", False), arguments.get("path", ".") or ".")
        if tool_name == "git_commit":
            return git_commit(arguments.get("message"), arguments.get("files"))
        if tool_name == "web_search":
            query = arguments.get("query", "")
            if not query:
                for k in ("q", "question", "text", "term", "pattern"):
                    if arguments.get(k):
                        query = arguments[k]
                        break
            return web_search(query, arguments.get("count", 5))
        if tool_name == "fetch_url":
            return fetch_url(arguments.get("url", ""), arguments.get("max_chars", 2000), arguments.get("query", ""), urls=arguments.get("urls"))
        if tool_name == "skill":
            return _skills.skill_tool(arguments.get("name", "") or "")
        if tool_name == "mcp":
            action = arguments.get("action", "list")
            if not isinstance(action, str) or not action.strip():
                action = "list"
            server = arguments.get("server", "")
            if not isinstance(server, str):
                server = ""
            tool = arguments.get("tool", "")
            if not isinstance(tool, str):
                tool = ""
            call_args = arguments.get("arguments", {})
            if not isinstance(call_args, dict):
                call_args = {}
            return _mcp.mcp_tool(action, server, tool, call_args)
        return f"Unknown tool: {tool_name}. Valid tools: {', '.join(sorted(TOOL_NAMES))}."
    except KeyboardInterrupt:
        raise
    except KeyError as error:
        return f"Missing required argument: {error}. Check the tool's parameters and retry with all required fields."
    except Exception as error:
        return f"Tool error: {error}. Retry, or try a smaller step."
