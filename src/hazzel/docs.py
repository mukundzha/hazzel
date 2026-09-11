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
        ],
    ),
    (
        "Slash commands",
        [
            "/model — switch provider/model   /help — quick overview   /docs — this guide",
            "/status /diff /commit /branch /log — git   /push /pull /sync — remote sync",
            "/pr — list PRs, /pr view|diff|checks <n> — read, /pr comment|merge|close <n>, /pr create <title> — write",
            "/plan on|off — read-only exploration   /prove on|off — smoke-check edits",
            "/undo [n] — revert file changes   /retry — re-run last message",
            "/usage — token spend   /export [file] — save transcript   /copy [code] — copy reply",
            "/init [file] — project map   /clear — reset chat   /logout — wipe keys   /exit — quit",
        ],
    ),
    (
        "Files and context",
        [
            "Type @ plus a path to attach a file to your message (Tab completes).",
            "Hazzel reads attached files itself — never paste code by hand.",
            "'read <path>', 'list <dir>', 'create <file>', 'delete <file>' run instantly, no model needed.",
            "Say 'fetch <url>' or paste an http(s) link — Hazzel reads the page and tells you what it says.",
        ],
    ),
    (
        "Approvals and safety",
        [
            "Edits show a diff first. Shell commands ask first (read-only ones like ls and git status skip the queue).",
            "Destructive git (reset --hard, --force, raw gh pr writes) stays blocked — use the git/PR tools.",
            "Everything runs inside your project root. /undo restores any file change.",
        ],
    ),
    (
        "Git and PR workflow",
        [
            "Typical flow: edit → /commit (drafts a message, y/e/n) → /push → /pr create 'title'.",
            "Review with /pr view <n>, /pr diff <n>, /pr checks <n>; merge with /pr merge <n>, walk away with /pr close <n>.",
            "Needs the gh CLI authenticated (gh auth login) for anything under /pr.",
        ],
    ),
    (
        "Plan and prove modes",
        [
            "/plan on makes Hazzel read-only: it explores and hands you a numbered plan, changing nothing until /plan off.",
            "/prove on smoke-checks Python edits in /tmp after each change, so you see pass/fail before trusting it.",
        ],
    ),
    (
        "When something looks wrong",
        [
            "'Unable to contact the model' — key missing/invalid (/model to re-add) or rate-limited (wait, or switch model).",
            "'gh is not authenticated' — run gh auth login in another terminal.",
            "Stuck or repeating? /clear for a fresh context, /retry to re-run, or split the task smaller.",
        ],
    ),
]


def get_sections() -> list[tuple[str, list[str]]]:
    return [(title, list(lines)) for title, lines in SECTIONS]
