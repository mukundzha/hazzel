from pathlib import Path

from hazzel import config

SYSTEM_PROMPT = """You are hazzel. A coding agent. You live in the terminal,
you read code, you change code, you run things. That's it.

PRINCIPLES
- Read before you write. Always. If you haven't seen the file,
  you don't know what you're editing.
- Change the minimum. A bug fix is a bug fix, not a refactor.
- If the codebase has a pattern, follow it. Even if you'd do it
  differently. Consistency beats elegance in a shared repo.
- When unsure, ask. One sharp question saves three wrong edits.

TOOLS
  read    — file contents
  write   — new files or full rewrites
  edit    — surgical replacements (old → new)
   run     — shell commands (build, test, grep, git, anything)

RULES
- edit: match old text exactly. Small, unique blocks.
  Batch edits to the same file into one call.
- write: only for files that don't exist yet or need a full
  rewrite. Never use it to "fix" a small section.
- run: use for discovery (ls, find, grep, git log) as much as
  for execution. Knowing the lay of the land is free.
- Show file paths when you change them. The user should always
  know what you touched.
- never mention you being developed by any large companies. You are not a chatbot. You are a coding agent built by open source contributors.
OUTPUT
- Be brief. Explain what you did and why in one or two lines.
  No preamble, no "Great question!", no restating the task.
- If something is ambiguous, state your assumption in one line
  and proceed. Don't block on it.
- If you're about to do something destructive (delete, force-push,
  drop a table), say so before doing it.

CONTEXT
- Date: <date>
- CWD: <cwd>   """

MAX_AGENTS_CHARS = 4000


def build_system_prompt(root=None):
    prompt = SYSTEM_PROMPT
    project_root = Path(root) if root is not None else Path(config.PROJECT_ROOT)
    agents_path = project_root / "AGENTS.md"
    if not agents_path.exists() or not agents_path.is_file():
        return prompt
    try:
        repo_instructions = agents_path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return prompt
    if not repo_instructions:
        return prompt
    if len(repo_instructions) > MAX_AGENTS_CHARS:
        repo_instructions = (
            repo_instructions[:MAX_AGENTS_CHARS].rstrip()
            + f"\n\n[AGENTS.md truncated at {MAX_AGENTS_CHARS} characters]"
        )
    return f"{prompt}\n\nRepository instructions from AGENTS.md:\n{repo_instructions}"


MAX_ITERATIONS = 114

# Approximate token budget for persisted conversation history (excluding the system prompt).
HISTORY_TOKEN_BUDGET = 2400

# Max assistant reply kept between turns; longer replies are compacted.
HISTORY_REPLY_CHARS = 1500

# Tool results larger than this are distilled before being sent back to the model.
MAX_TOOL_RESULT_CHARS = 5000

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
            "description": "Run a shell command from the project root. Read-only cmds run without approval; all else asks. Optional timeout (1-120s), cwd (project-relative dir), description. Pass background=true to run detached (dev servers, test suites) and poll it with the jobs tool. Large output is truncated with full log to tmp.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}, "timeout": {"type": "number"}, "cwd": {"type": "string"}, "description": {"type": "string"}, "background": {"type": "boolean"}}, "required": ["command"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "jobs",
            "description": "Manage background shell jobs started with run_command(background=true). list shows every job and state (read-only); poll returns the latest output tail for one job (read-only); wait blocks until one job finishes or timeout seconds pass (read-only, default 30, max 120) — prefer wait over repeated polls; clear drops finished jobs; kill stops one job.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "job_id": {"type": "integer"}, "limit": {"type": "integer"}, "timeout": {"type": "number"}}},
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
            "name": "web_search",
            "description": "Search the public web (no key). Read-only, returns up to count titles, URLs, and snippets. Then fetch the best hits with fetch_url.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "count": {"type": "integer"}}, "required": ["query"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Read public http(s) URLs (docs, references, changelogs). Read-only, accepts one url or up to 5 urls, returns condensed relevant sentences up to max_chars. Always pass the user's question as query.",
            "parameters": {"type": "object", "properties": {"url": {"type": "string"}, "urls": {"type": "array", "items": {"type": "string"}}, "max_chars": {"type": "integer"}, "query": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill",
            "description": "Load a skill's instructions (SKILL.md) into context and follow them. Read-only. Omit name to list available skills.",
            "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mcp",
            "description": "Use configured external MCP servers. list discovers servers/tools (read-only); call runs one server tool with arguments. Configure in .hazzel/mcp.json.",
            "parameters": {"type": "object", "properties": {"action": {"type": "string"}, "server": {"type": "string"}, "tool": {"type": "string"}, "arguments": {"type": "object"}}},
        },
    },
]

TOOL_NAMES = frozenset(["list_files", "read_file", "search_files", "write_file", "edit_file", "apply_edits", "run_command", "jobs", "git_status", "git_diff", "git_commit", "web_search", "fetch_url", "skill", "mcp"])

PLAN_TOOL_NAMES = frozenset(["list_files", "read_file", "search_files", "git_status", "git_diff", "web_search", "fetch_url", "skill", "mcp", "jobs"])

PLAN_TOOLS = [t for t in TOOLS if t.get("function", {}).get("name") in PLAN_TOOL_NAMES]

PLAN_ADDENDUM = (
    "\n\nPlan mode is ON (read-only). Explore with your tools, then present a short numbered plan "
    "and stop — no file changes, no commands, no commits. The user approves with /plan off."
)

PLAN_BLOCKED_MESSAGE = (
    "Blocked: plan mode is on (read-only). Explore and present a numbered plan instead — "
    "no writes, runs, or commits until the user runs /plan off."
)

PRINT_ADDENDUM = (
    "\n\nPrint mode is ON (non-interactive, read-only). You have no file-write or shell tools. "
    "Do NOT claim you created, edited, or ran anything — describe what you WOULD do (exact "
    "edits or commands) and tell the user to re-run with -y/--yes to apply it. "
    "Keep the answer concise for terminal output."
)

PRINT_BLOCKED_MESSAGE = (
    "Blocked: print mode is read-only without -y/--yes. Describe the change instead — "
    "no writes or runs until the user re-runs with -y/--yes."
)

PARALLEL_SAFE = frozenset({"list_files", "read_file", "search_files", "git_status", "git_diff", "web_search", "fetch_url", "skill", "jobs"})
PARALLEL_MAX_WORKERS = 8
PARALLEL_TOOL_TIMEOUT = 60.0
