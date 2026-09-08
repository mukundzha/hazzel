from __future__ import annotations


SUGGEST_SYSTEM = (
    "You write Conventional Commit messages. Reply with ONE line only, no quotes, "
    "no code fences, no explanation. Format: type(scope): subject. "
    "Types: feat, fix, docs, refactor, chore, test, perf, build, ci. "
    "Subject <= 72 chars, imperative mood (e.g. 'add', not 'added')."
)

MAX_SUGGEST_DIFF = 6000


def heuristic_message(status: str, diff: str) -> str:
    files = []
    for line in (status or "").splitlines():
        line = line.strip()
        if not line or line.startswith("##"):
            continue
        name = line[2:].strip().split(" -> ")[-1].strip().strip('"')
        if name:
            files.append(name)
    n = len(files) or diff.count("diff --git")
    scope = files[0].split("/")[-1].split(".")[0] if files else ""
    if n <= 0:
        return "chore: update working tree"
    if n == 1:
        return f"chore({scope}): update {files[0]}"[:100] if scope else f"chore: update {files[0]}"[:100]
    return f"chore: update {n} files" + (f" ({scope}…)" if scope else "")


def suggest_message(diff: str, status: str) -> tuple[str, bool]:
    clipped = (diff or "")[:MAX_SUGGEST_DIFF]
    body = f"STATUS:\n{(status or '')[:1000]}\n\nDIFF:\n{clipped}"
    messages = [
        {"role": "system", "content": SUGGEST_SYSTEM},
        {"role": "user", "content": body},
    ]
    try:
        from .providers import get_provider

        resp = get_provider().chat(messages, [])
        text = (getattr(resp, "content", None) or "").strip()
    except Exception:
        return heuristic_message(status, diff), True
    if not text:
        return heuristic_message(status, diff), True
    line = text.splitlines()[0].strip().strip("\"'`").strip()
    if line.lower().startswith("conventional"):
        line = heuristic_message(status, diff)
        return line, True
    if len(line) > 200:
        line = line[:200].rstrip()
    return line or heuristic_message(status, diff), False
