# Hazzel

**A small terminal coding agent that works on your code, not around it.**

Once upon a time, every coding assistant wanted to become your IDE, your cloud, your everything.

Hazzel chose a different story.

It stays where the work happens — your terminal, your project, your rules — and talks to your code through a small set of honest tools. You ask in plain language. It inspects, edits, runs, verifies, and shows its work. Nothing hidden. Nothing magic.

Just you, your terminal, and an agent that knows its place.

```text
Hazzel 0.1.1 ~/hazzel

❯ fix the bug in agent.py

  ● read_file  agent.py
  ● edit_file  agent.py
  ● run_command  python -m pytest — passed

Hazzel > Fixed. Verified with tests.
```

## Why Hazzel exists

Most agents grow into platforms. Hazzel shrinks into a tool.

The philosophy:

1. **Small beats complicated.** If it can be clear without another abstraction, keep it simple.
2. **The model requests, Hazzel decides.** The model never touches your machine directly.
3. **The terminal is enough.** No GUI, no cloud workspace, no lock-in.
4. **Your keys are yours.** Bring your own Groq / OpenAI / Mistral / Anthropic key.
5. **Show the work.** Every read, edit, and command is visible.

## Install

```bash
pip install hazzel
```

Requirements: Python 3.10+, a terminal, and one API key.

From source:

```bash
git clone https://github.com/mukundzha/hazzel.git
cd hazzel
pip install -e .
```

## Run

Start Hazzel from the project you want it to work on:

```bash
cd my-project
hazzel
```

(`python -m hazzel` works too.)

That directory becomes the project root. File tools cannot escape it — `../another-project` is rejected.

No export needed. Just run `/model`, pick a model, and paste your key in the input field when asked — it's saved securely and is the most stable way to stay signed in.

Config lives at `~/.config/hazzel/config.json` (0600).

## What it can do

Ten tools — six for code, four git-native:

| Tool | Story |
|------|-------|
| `list_files(".")` | Look around the room |
| `read_file("src/main.py")` | Read 60 numbered lines, page with offset |
| `search_files("MAX_ITERATIONS")` | Grep first, read second — never wander blind |
| `write_file("src/example.py", "...")` | Create, with undo |
| `edit_file("src/main.py", "old", "new")` | Small anchored edit, diff preview, undoable |
| `run_command("python -m pytest")` | Run shell, with approval, timeout, and cap |
| `git_status()` | Branch + working-tree status, read-only |
| `git_diff()` | Per-file diff with +/− counts, read-only |
| `git_commit("msg")` | Diff preview + approval; omit msg to auto-draft from diff |
| `git_branch("list")` | List, create, switch — writes ask first |

Tag files directly: `@src/agent.py fix this`. Tab-completes, highlights, attaches to context.

## Living in the terminal

```text
/model    — switch model / provider
/prove on — ephemeral smoke check after edits (off by default)
/status   — git working-tree status
/diff     — changed files, open any file's full diff
/commit   — suggest a message from your diff, y/e/n
/branch   — list / create / switch branches
/push     — push branch to remote (asks first)
/pull     — pull remote changes (asks first)
/sync     — pull then push (asks first)
/log      — recent commits
/help     — shortcuts + commands
/clear    — reset conversation + usage
/summary  — what did Hazzel just do?
/usage    — tokens sent, received, cached
/undo 2   — undo last 2 file changes
/logout   — clear saved keys
/exit     — leave
```

Prove mode is optional and off initially. Turn it on with `/prove on`: after each edit Hazzel shows what it will run and asks once (`Run?`), then either writes a happy-path smoke script to `/tmp` (Python changes, imports just work) or runs your repo's suite (`npm test`, `cargo test`, `go test`, `pytest`) for other files — and reports `prove … — passed/failed`. Nothing is written into your project.

Commands ask first:

```text
Hazzel wants to run: python -m pytest
Allow? [y/N]
```

Edits show a diff and ask first. Deletes and overwrites are checkpointed for `/undo`.

The agent is frugal by design: trivial turns (`hi`, `read foo.py`, `list files`) run locally with zero LLM calls, history is compacted to ~1200 tokens, tool output is distilled to ~2500 chars.

## Models

Pick your pilot with `/model`:

- OpenAI: GPT-6 Astra, GPT-5.6 Sol/Terra/Luna, GPT-5, GPT-5 Mini, GPT-4.1, GPT-4o
- Anthropic: Claude Fable 5.1, Opus 5, Sonnet 5, Haiku 4.5
- Mistral: Medium 3.5, Small 4, Large 3, Ministral 3, Codestral, GLM 5.2, Leanstral 1.5
- Groq: GPT OSS 120B (default), GPT OSS 20B

Default: `openai/gpt-oss-120b` on Groq.

## Architecture — a short story in 6 acts

```text
You
 ↓
__main__.py  — listens, routes slash commands
 ↓
agent.py     — fast-path + tool loop (max 10), history, budget
 ↓
providers/   — groq / openai / mistral / anthropic, one interface
 ↓
tools/       — the only hands that touch your project
 ↓
safety.py    — checkpoint before every mutation
 ↓
ui.py + formatter.py — spinners, diffs, markdown, token meter
```

The model decides *what*. Hazzel decides *whether and how*. Tools do the work.

```text
src/hazzel/
  __main__.py  agent.py  config.py
  llm.py  mentions.py  safety.py  tokens.py
  git.py  git_suggest.py  ui.py  formatter.py
  providers/base.py groq.py openai.py mistral.py anthropic.py
  tools/list_files.py read_file.py search_files.py
       write_file.py edit_file.py run_command.py
       git_status.py git_diff.py git_commit.py git_branch.py
```

## Safety

Hazzel is an agent, not a sandbox. `run_command` runs on your machine — only approve what you understand.

File writes/edits/`rm` are undoable. Nothing leaves the project root without your `y`.

## Status

`0.1.1` — early, deliberate, reliable foundation. Not big, on purpose.

Included: terminal UI, multi-provider, tool-calling, @mentions, history compaction, undo, approval, timeout, token usage, markdown rendering, git-native status/diff/commit/branch with message suggestions.

Not yet: streaming, background commands, session persistence, IDE plugins. Omissions, not oversights.

## Author

Built by **Mukund Jha** — mukundzha33@gmail.com

License: AGPL-3.0-or-later — see [LICENSE](./LICENSE).
