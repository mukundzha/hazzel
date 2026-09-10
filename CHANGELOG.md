# Changelog

All notable changes to Hazzel are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [0.1.6] - 2026-09-10
### Added
- `/copy [code]`: copy last reply (or just its last code block) via pbcopy/wl-copy/xclip/xsel.
- `/retry`: re-run the last user message through the full agent loop.
- Star nudges: one-time first-run note plus a line in `/help`.
### Changed
- `/help` prints inline instead of taking over the whole screen.

## [0.1.5] - 2026-09-10
### Added
- Safe-command allowlist: `run_command` skips approval for read-only cmds (`ls`, `pwd`, `cat`, `head`, `tail`, `echo`, `wc`, `file`, `git status/diff/log`); chained or shell-metachar commands still ask.
- `/export [file.md]`: save transcript + last implementation summary + tool trace + usage to markdown, jailed to project root with auto-suffix on clash.

## [0.1.4] - 2026-09-09
### Added
- Plan mode (`/plan on|off`): read-only exploration with a reduced tool set — writes, runs, and commits are blocked until approval; footer shows `· plan` vs `· build` so the mode is always visible.
- Streaming answers on all four providers with automatic fallback to a full response if a stream drops.
- `/` menu pages 5 commands at a time with a `(n/total)` counter; pink `❯` on selection.
- Cleaner replies: code blocks hug content, tables drop per-row lines, uniform indent, no dead gap before the input box.
- Version detection falls back to `__version__` when package metadata is missing.
- Git-native agent: 4 new tools (`git_status`, `git_diff`, `git_commit`, `git_branch`) — 10 total, up from 6.
- Slash commands: `/status`, `/diff`, `/commit`, `/branch`, `/log`, `/push`, `/pull`, `/sync`.
- Commit-message suggestions: `/commit` with no message drafts a Conventional Commit from your diff via the current model (offline heuristic fallback), then asks `[y] commit · [e] edit · [n] cancel`.
- `/diff` file browser: changed-files panel with `M/A/D` icons and `+add −del` counts; open any file's full diff by number, list re-renders after each view.
- Push/pull/sync with approval: `/push` (auto `-u origin` on first push), `/pull` (blocked on dirty tree), `/sync` (pull then push). No `--force` anywhere; raw `git push/commit/reset --hard/clean` via `run_command` stays blocked.
- `src/hazzel/git.py`: no-shell git subprocess helpers (10s timeout, repo guard, branch-name validation, per-file numstat + single-file diff with untracked-file support).
- `src/hazzel/git_suggest.py`: LLM suggestion + heuristic fallback.
- Zero-LLM fast paths for `git status`, `git diff`, `git log`, `git branch`.
- `/help` Git section, autocomplete entries, and README coverage for all of the above.

### Fixed
- Markdown rendering overhaul (`formatter.py`): paragraphs no longer run together, lists are single-spaced, tables get constrained columns with row separators and full-width rendering, one blank line between every block.
- Prove approval card: replaced the jumbled `Hazzel wants to prove: prove …` prompt with a clean `◈ Prove · <command>` panel showing files and a single `Run? [y/N]` question.

## [0.1.1] - 2026-09-08
### Added
- `hazzel` console entry point (`pip install hazzel`, run `hazzel` or `python -m hazzel`).
- First-run key nudge and single-source version lookup.

### Changed
- PyPI description covering all four providers; breathing room between long bullet points.

## [0.1.0] - 2026-09-08
### Added
- Multi-provider terminal coding agent (Groq, OpenAI, Anthropic, Mistral) with tool-calling loop.
- Six file/shell tools with approval, diff preview, undo, timeout, and project-root sandboxing.
- `@mentions` with tab-completion, history compaction, token usage meter, markdown rendering.
- Prove mode: ephemeral smoke check in `/tmp` after edits (off by default).
- Slash commands: `/model`, `/prove`, `/help`, `/clear`, `/summary`, `/usage`, `/undo`, `/logout`, `/exit`.
