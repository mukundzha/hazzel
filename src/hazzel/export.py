from datetime import datetime


def build_markdown(messages, summary, trace, session_usage, model_name):
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# Hazzel transcript — {stamp}", ""]
    lines.append(f"Model: {model_name or 'unknown'}")
    lines.append("")
    for msg in (messages or [])[1:]:
        role = msg.get("role")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            lines += ["## User", "", content, ""]
        elif role == "assistant":
            lines += ["## Hazzel", "", content, ""]
    if summary:
        lines += ["## Last implementation", "", summary.strip(), ""]
    if trace:
        lines.append("### Tools")
        lines.append("")
        for t in trace:
            mark = "✓" if t.get("success") else "✗"
            lines.append(f"- [{mark}] {t.get('tool', '')} {t.get('detail', '') or ''}".rstrip())
        lines.append("")
    if session_usage and session_usage.get("calls"):
        total = session_usage.get("input", 0) + session_usage.get("output", 0)
        lines.append(f"_Usage: {total:,} tokens across {session_usage.get('calls')} calls._")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def export_transcript(messages, summary, trace, session_usage, model_name, filename=None):
    from . import config

    name = (filename or "").strip().strip("\"'") or datetime.now().strftime("hazzel-transcript-%Y%m%d-%H%M%S.md")
    if not name.endswith(".md"):
        name += ".md"
    try:
        path = config.resolve_project_path(name)
    except ValueError as error:
        return False, str(error)
    if path.exists():
        stem, suffix = path.stem, path.suffix
        for i in range(1, 100):
            candidate = path.with_name(f"{stem}-{i}{suffix}")
            if not candidate.exists():
                path = candidate
                break
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_markdown(messages, summary, trace, session_usage, model_name), encoding="utf-8")
    except OSError as error:
        return False, f"Export failed ({error})."
    try:
        return True, str(path.relative_to(config.PROJECT_ROOT.resolve()))
    except ValueError:
        return True, str(path)
