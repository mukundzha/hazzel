from __future__ import annotations

SECTIONS: list[tuple[str, list[str]]] = [
    (
        "Start in 30 seconds",
        [
            "pip install hazzel, cd into your project, run hazzel.",
            "Run /model, pick a provider, paste your key. Done — Hazzel remembers it.",
            "No key yet? Set one via env (OPENAI_API_KEY, GROQ_API_KEY, …) or use Ollama locally with no key.",
        ],
    ),
    (
        "The everyday loop",
        [
            "1. Ask in plain words: 'fix the failing test', 'explain this file'.",
            "2. Hazzel shows each step (read, edit, run) with a diff or prompt.",
            "3. Approve (y) or cancel (n). Nothing mutates without you.",
            "Smallest change wins: ask for one thing at a time for best results.",
            "Ctrl+J adds a newline, Enter sends; pasting keeps every line.",
            "`hazzel -p \"question\"` answers once and exits (pipe stdin in; `-y` allows writes, `--output-format json` for scripts).",
        ],
    ),
    (
        "Slash commands",
        [
            "/model — switch provider/model   /help — quick overview   /docs — this guide",
            "/status /diff /commit /log /review — git core (push/pull via ! with approval)",
            "Run shell commands with ! or ask Hazzel to run them (approval first).",
            "Suffix ! with & (`!pytest -q &`) to run in the background; /jobs lists, polls, and kills jobs.",
            "/plan on|off — read-only exploration   /think on|off — deeper reasoning   /goal — objective, run it with /goal run",
            "/undo [n] — revert file changes   /retry — re-run last message",
            "/jobs [id|wait id|kill id|clear] — background jobs (wait blocks until done)",
            "/usage — token spend + cost   /usage today|week|month|--by-model|export|clear   /budget — spend warnings (never blocks)",
            "/export [file] — save transcript   /copy [code] — copy reply",
            "/init [file] — project map   /clear — reset chat   /logout — wipe keys   /exit — quit",
            "/mcp — list configured MCP servers/tools   /mcp <server> [<tool>] — inspect or run one",
            "MCP servers live in .hazzel/mcp.json ({\"mcpServers\": {\"name\": {\"command\": ..., \"args\": [...]}}}). Discovery is read-only; calls run third-party code.",
        ],
    ),
    (
        "Files and context",
        [
            "Type @ plus a path to attach a file to your message (Tab completes).",
            "Type @screenshot.png / @mock.jpg to attach an image — Hazzel sees it (png, jpg, gif, webp, up to 8MB).",
            "Hazzel reads attached files itself — never paste code by hand.",
            "'read <path>', 'list <dir>', 'create <file>', 'delete <file>' run instantly, no model needed.",
            "Say 'fetch <url>' or paste an http(s) link — Hazzel reads the page and tells you what it says.",
        ],
    ),
    (
        "Approvals and safety",
        [
            "Edits show a diff first. Shell commands ask first (read-only ones like ls and git status skip the queue).",
            "Destructive git (reset --hard, --force) stays blocked — use the git tools.",
            "Everything runs inside your project root. /undo restores any file change.",
        ],
    ),
    (
        "Git workflow",
        [
            "Typical flow: edit → /review → /commit (drafts a message, y/e/n) → !git push.",
            "/status and /diff [--staged] inspect; /log shows recents.",
            "/review [--staged] reads the diff back and flags risks, gaps, and what to fix before committing — read-only, changes nothing.",
        ],
    ),
    (
        "Shell workflow",
        [
            "Typical flow: edit → run tests with !pytest -q → fix what fails.",
            "Long suite or server? `!pytest -q &` runs it detached — /jobs 1 polls, /jobs kill 1 stops it.",
        ],
    ),
    (
        "Plan and think modes",
        [
            "/plan on makes Hazzel read-only: it explores and hands you a numbered plan, changing nothing until /plan off.",
            "/think on asks supported models to reason step-by-step before answering — costs more tokens, better on hard problems.",
        ],
    ),
    (
        "When something looks wrong",
        [
            "'Unable to contact the model' — key missing/invalid (/model to re-add) or rate-limited (wait, or switch model).",
            "Stuck or repeating? /clear for a fresh context, /retry to re-run, or split the task smaller.",
        ],
    ),
]


def get_sections() -> list[tuple[str, list[str]]]:
    return [(title, list(lines)) for title, lines in SECTIONS]
