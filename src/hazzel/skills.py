import re
import time
from pathlib import Path

SKILL_FILENAME = "SKILL.md"

MAX_SKILL_CHARS = 12000
MAX_CATALOG_SKILLS = 40
_CATALOG_TTL = 30.0

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

_catalog_cache = {"ts": 0.0, "skills": []}


def _project_skill_dirs():
    from . import config

    root = config.PROJECT_ROOT
    return [
        (root / ".hazzel" / "skills", "project"),
        (root / "skills", "project"),
    ]


def _global_skill_dirs():
    from . import config

    return [
        (config.CONFIG_DIR / "skills", "global"),
        (Path.home() / ".agents" / "skills", "global"),
    ]


def _parse_frontmatter(text):
    meta = {}
    body = text or ""
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            raw = body[3:end].strip().strip("-").strip()
            body = body[end + 4:].lstrip("\n")
            current = None
            for line in raw.splitlines():
                if not line.strip() or line.strip().startswith("#"):
                    continue
                match = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", line)
                if match:
                    current = match.group(1).lower()
                    meta[current] = match.group(2).strip().strip("'\"")
                elif current and (line.startswith(" ") or line.startswith("\t")):
                    meta[current] += " " + line.strip().strip("'\"")
    return meta, body


def _read_skill_dir(skill_dir):
    try:
        text = (skill_dir / SKILL_FILENAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    meta, _ = _parse_frontmatter(text)
    name = (meta.get("name") or skill_dir.name).strip()
    if not _NAME_RE.match(name):
        return None
    description = (meta.get("description") or "").strip()
    return {"name": name, "description": description, "path": skill_dir, "source": ""}


def discover_skills():
    now = time.monotonic()
    if _catalog_cache["skills"] and now - _catalog_cache["ts"] < _CATALOG_TTL:
        return list(_catalog_cache["skills"])
    seen = {}
    for skill_dir, source in _project_skill_dirs() + _global_skill_dirs():
        try:
            entries = sorted(skill_dir.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for entry in entries:
            try:
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if not (entry / SKILL_FILENAME).is_file():
                    continue
            except OSError:
                continue
            info = _read_skill_dir(entry)
            if info is None:
                continue
            info["source"] = source
            seen.setdefault(info["name"], info)
            if len(seen) >= MAX_CATALOG_SKILLS:
                break
        if len(seen) >= MAX_CATALOG_SKILLS:
            break
    skills = sorted(seen.values(), key=lambda s: s["name"].lower())
    _catalog_cache.update({"ts": now, "skills": skills})
    return list(skills)


def clear_skill_cache():
    _catalog_cache.update({"ts": 0.0, "skills": []})


def catalog_lines():
    lines = []
    for s in discover_skills():
        desc = (s.get("description") or "no description").strip()
        if len(desc) > 120:
            desc = desc[:119].rstrip() + "…"
        lines.append(f"- {s['name']}: {desc}")
    return lines


def skills_prompt():
    lines = catalog_lines()
    if not lines:
        return ""
    return (
        "\n\nSkills (specialized instructions, read-only): when the user's task matches a skill, "
        "call skill(name) to load its instructions and follow them; call skill with no name to re-list.\n"
        + "\n".join(lines)
    )


def _sibling_files(skill_dir):
    try:
        names = sorted(
            p.name for p in skill_dir.iterdir()
            if p.is_file() and p.name != SKILL_FILENAME and not p.name.startswith(".")
        )
    except OSError:
        return []
    return names[:20]


def find_skill(name):
    clean = (name or "").strip().strip("'\"")
    if not clean or not _NAME_RE.match(clean):
        return None
    return next((s for s in discover_skills() if s["name"] == clean), None)


def get_skill_body(name):
    match = find_skill(name)
    if match is None:
        return None
    try:
        text = (match["path"] / SKILL_FILENAME).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    _, body = _parse_frontmatter(text)
    body = body.strip() or "(empty skill)"
    if len(body) > MAX_SKILL_CHARS:
        body = body[:MAX_SKILL_CHARS] + f"\n[…{len(body) - MAX_SKILL_CHARS} chars skipped…]"
    return body


def load_skill(name):
    clean = (name or "").strip().strip("'\"")
    if not clean:
        return list_skills()
    if not _NAME_RE.match(clean):
        return f"Invalid skill name: {clean}. Use /skills to list available skills."
    match = find_skill(clean)
    if match is None:
        close = [s["name"] for s in discover_skills() if clean.lower() in s["name"].lower()]
        hint = f" Did you mean: {', '.join(close[:3])}?" if close else " Use /skills to list available skills."
        return f"Skill not found: {clean}.{hint}"
    body = get_skill_body(clean)
    if body is None:
        return f"Skill not found: {clean}. Use /skills to list available skills."
    out = [f"Skill `{match['name']}` loaded — follow its instructions below.", "", body]
    siblings = _sibling_files(match["path"])
    if siblings:
        out += ["", f"Supporting files in {match['path'].name}/: {', '.join(siblings)} — read with read_file if the instructions reference them."]
    return "\n".join(out)


def list_skills():
    skills = discover_skills()
    if not skills:
        return (
            "No skills installed. Add a skill as <project>/.hazzel/skills/<name>/SKILL.md "
            "(frontmatter: name, description) or ~/.config/hazzel/skills/<name>/SKILL.md."
        )
    rows = []
    for s in skills:
        desc = (s.get("description") or "no description").strip()
        if len(desc) > 100:
            desc = desc[:99].rstrip() + "…"
        rows.append(f"- {s['name']} ({s['source']}): {desc}")
    return "Skills:\n" + "\n".join(rows) + "\n\nLoad one with skill(name) or /skills <name>."


def skill_tool(name=""):
    return load_skill(name or "")


def skill_locations():
    return [str(p) for p, _ in _project_skill_dirs() + _global_skill_dirs()]
