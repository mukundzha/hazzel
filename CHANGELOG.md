# Changelog

All notable changes to Hazzel are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

## [1.5.6] - 2026-09-22
### Removed
- Dead UI stubs `show_turn_card` / `show_turn_from_trace` (always returned `None`, zero callers) plus their re-exports from `hazzel.ui` and the `panels` compat shim (#21).
### Added
- Background jobs: `jobs(action=wait)` blocks until a job finishes or a timeout (1–120s) passes — prefer it over repeated polls; `jobs(action=clear)` drops finished jobs and deletes their logs (`/jobs wait <id> [seconds]`, `/jobs clear`).

### Changed
- Deduplicated live tool-row append and trim handling in the terminal UI.

## [1.5.4] - 2026-09-21
### Added
- Ask-once approvals (`tools/approvals.py`): a y/N decision sticks for the turn — approvals run without re-prompting, denials fail fast with guidance instead of prompting again. Wired into `run_command`, `write_file`, `edit_file`, `apply_edits`, and `git_commit`; memory resets every turn and on conversation clear.
- README quickstart leads with a zero-install trial (`uvx hazzel` / `pipx run hazzel` — verified: 5s cold, instant warm) with persistent alternatives (`uv tool install`, `pipx install`) alongside `pip`.
- CI coverage report (`pytest-cov`, report-only, no fail-under gate) on the Python 3.13 leg, with the HTML report uploaded as a 14-day artifact. `pytest-cov` added to the `dev` extra.
- README test-count badge (linked to CI) so the suite size is visible without clicking through.
- `vercel.json` pinning deployments to `main`, so pull requests stop inheriting a failing "Authorization required to deploy" check on `site/`.

### Changed
- `src/hazzel/ui.py` (2.6k lines) split into the `hazzel.ui` package (`_state`, `input`, `stream`, `messages`, `git/`, `help_docs`, `usage`, `selectors`; `panels` kept as a compat shim). Zero behavior change — `from hazzel import ui` keeps working.
- README "Who's behind this" → "Contributors": PFP row only, dropping the duplicate names line and the prose that repeated every contributor name a third time. Header no longer lists contributor handles.

## [1.5.3] - 2026-09-20
### Added
- docs/EXAMPLES.md: five copy-paste transcripts for `/review`, `/commit`, vision `@image`, `!cmd &` / `/jobs`, and `hazzel -p` (#14).

### Removed
- Star nudge and its 0600-perm marker file (`~/.config/hazzel/.star_nudged`); first launch no longer prints the star line.

### Changed
- Landing page (`site/`): full SEO pass — keyword title/meta, canonical, OG/Twitter cards, `SoftwareApplication` + `FAQPage` JSON-LD, live demo GIF, Hazzel-vs-alternatives comparison, crawlable FAQ, `robots.txt`/`sitemap.xml`; dropped the locomotive-scroll dependency (~40KB) for faster loads.

## [1.5.2] - 2026-09-20
### Added
- README: architecture diagram (mermaid) and an honest comparison table (Hazzel vs Aider vs cloud agents).
- Community: issue templates (bug, feature request, security routing), PR template, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `FUNDING.yml`, GitHub Discussions.

### Changed
- README rewritten: 280 → ~200 lines, repetition cut, features compressed into a scannable table, "Recently shipped" now leads with the first external contribution.

## [1.5.1] - 2026-09-20
### Fixed
- Confirmation prompts accept both `y` and `yes`, regardless of letter case (@Gambit-Checkmate in #7).

## [1.5.0] - 2026-09-20
### Added
- `/review [--staged]`: read-only review of the uncommitted diff. The current model receives the changed files and their diffs (capped at 20 files / 12k chars, untracked files synthesized in) and answers with Summary · Risks · Missing · Before commit as rendered markdown; a deterministic offline heuristic scan (`review.py`) is used when no model is reachable. It never writes files, runs commands, or creates undo checkpoints, and it leaves the last reply set so `/copy` works afterwards.

### Changed
- Reply colors (`formatter.py`): one fixed role per color — brand orange (`#ec8500`) is reserved for structure (heading markers, bullets, panel titles, quote bars), a lighter tint (`#ffb454`) highlights bold "main words" in prose, and a single cool blue (`#8ab4f8`) marks everything that points somewhere (links, `@file` mentions). Italic and strikethrough stay uncolored; nothing is colored at random.

### Fixed
- Reply rendering (`formatter.py`): bold/italic no longer match inside words — `__init__`, `my_var_name`, and `1*2*3` render verbatim instead of being mangled into styled text (emphasis still requires word boundaries and non-blank content). Tables hug their content (narrow cells no longer padded to a 20-char floor) with padded edge borders so text no longer touches the box; blockquotes get an accent bar (`▌`) with dimmed content; anonymous fenced code blocks no longer show a meaningless `text` title.

## [1.4.9] - 2026-09-18
### Added
- Background shell jobs: `run_command(background=true)` starts a detached job (dev servers, long test suites) and returns a job id; new `jobs` agent tool (`list` read-only, `poll` one job's output tail read-only, `kill` stops one, plan-mode and `hazzel -p` safe for reads). REPL: `!command &` runs in background, `/jobs`, `/jobs <id>`, `/jobs kill <id>`. Per-job full logs in `/tmp/hazzel-job-*.log`, up to 32 jobs, remaining jobs killed on exit.

## [1.4.8] - 2026-09-17
### Added
- Core git back: `git_status`, `git_diff`, `git_commit` agent tools plus `/status`, `/diff [--staged]` (changed-files browser), `/commit` (auto-drafted Conventional message with y/e/n, diff preview, approval), `/log` slash commands, and zero-LLM fast paths for `status`/`diff`/`log`. Reads are plan-mode safe and skip approval (`git status/diff/log`); raw `git commit` and destructive git (`reset --hard`, `clean`) stay blocked in favor of the tools; push/pull flow through normal command approval.

## [1.4.7] - 2026-09-17
### Added
- Image attach: `@screenshot.png` / `@mock.jpg` sends the image to the model (png, jpg/jpeg, gif, webp, up to 8MB, max 5 per turn). Works on vision-capable models (OpenAI, Anthropic, Groq/OpenRouter vision models, Ollama vision models); text + `<image>` placeholder stays in context, base64 never touches saved sessions/history. Bare `@img.png` asks what to do, like file attaches.
- Minimal MCP stdio transport: configure servers in `.hazzel/mcp.json` (`{"mcpServers": {"name": {"command": ..., "args": [...], "env": {...}, "timeout": 30}}}`) or `~/.config/hazzel/mcp.json` (project wins on clash, stdlib only, no new dependencies). Single skill-like `mcp` agent tool — `list` discovers servers/tools read-only (plan-mode and `hazzel -p` safe), `call` runs one remote tool; processes spawn lazily on first use with initialize handshake, per-server timeouts, and clean shutdown. `/mcp`, `/mcp <server>`, `/mcp <server> <tool>` in the REPL; server names appear in the system prompt without spawning.

## [1.4.6] - 2026-09-17
### Added
- Non-interactive print mode: `hazzel -p "prompt"` runs one turn, prints the reply, and exits (0 ok, 1 turn failure, 2 usage/no-key, 130 cancelled). Piped stdin becomes context (`git diff | hazzel -p "summarize"`); bare `-p` uses stdin as the prompt. Read-only by default (writes/runs blocked with a re-run hint); `-y/--yes` pre-approves them; `--output-format json` emits `{response, model, usage}` for scripts. Progress UI stays off stdout; saved sessions untouched.

## [1.4.5] - 2026-09-17
### Added
- Native cost and token visibility: normalized `UsageRecord` per provider adapter (`parse_usage`), dollar pricing (`pricing.py`, dated table + `custom_pricing` override, `unknown` shown honestly instead of guessed), append-only local log (`usage_store.py` → `~/.config/hazzel/usage.jsonl`, 90-day retention), `/usage today|week|month|--by-model|export|clear`, `/budget` warn-only thresholds, per-turn `tokens · session $` status line.

## [1.4.4] - 2026-09-16
### Fixed
- `@` mention fuzzy test now matches the `hazzel.agent` package layout (`agnt`→`agent/` files); provider factory hardened (`get_provider` zero-arg, compat wiring, Ollama local-model fetch).
### Added
- Session persistence: single last-session slot per project (`~/.config/hazzel/sessions/`) — saved after each turn and on exit, restored on launch; `/session restore` reloads it ("back where you left off"); `/clear` archives the wiped session for one restore.
- Stronger Ollama base: curated defaults (`qwen2.5-coder:32b`, `qwen3:30b`, `deepseek-coder-v2:16b`, `codestral:22b`) with per-model context, dedicated `OllamaProvider` (`num_ctx` 65536, `keep_alive` 30m, `ollama pull` hints).
### Removed
- Prove mode (`/prove`, `config.is_prove_enabled/set_prove_enabled`, `agent` prove helpers): no more post-turn smoke scripts in `/tmp`; verify with `!pytest -q` / `run` instead.
### Changed
- Split `agent.py` (1668 lines) into the `hazzel.agent` package: `toolspec` (prompt/schemas), `state` (usage/target/reasoning state), `dispatch` (tool normalization + `run_tool`), `history` (summary/compaction/budget), `fastpath` (zero-LLM replies), `prove` (smoke harness), `core` (chat + `run()` loop). `hazzel.agent` re-exports the full previous surface, so `from hazzel import agent` and `agent.run/run_tool/try_fast_path/...` keep working unchanged.

## [1.4.3] - 2026-09-16
### Changed
- Packaging: single-source version from `hazzel.__version__`, PEP 639 license expression, authors/URLs, floored dependencies, `dev` extras, pytest/ruff config, `MANIFEST.in`; removed unused imports; fixed stale version fallbacks and docs.

## [1.4.2] - 2026-09-15
### Changed
- Header stacks project path under the version line instead of sharing one row.
- Dividers use live terminal width full-bleed so prompt, echo, and reply rules match.
- `/` palette shows the cursor only on the highlighted row.

## [1.4.1] - 2026-09-14
### Added
- `/think on|off|toggle|status`: extended thinking mode (Anthropic `thinking`, OpenAI `reasoning_effort`, Groq GPT-OSS only), persisted in config, `· think` indicator in the prompt bar, graceful fallback when the model rejects it.
- Live thinking stream: reasoning tokens render dim in the loader while the model thinks, clear when the answer starts streaming, and are not re-printed after the turn.
### Fixed
- `extract_reasoning` now captures Groq's `reasoning` delta attribute alongside OpenAI's `reasoning_content` — GPT-OSS thinking was silently dropped.
### Changed
- `/init` generates a compact `AGENTS.md` template (Stack / Commands / Conventions / Layout / Gotchas / Don't) with inferred commands per stack (Node lockfile + scripts, Python, Cargo, Go) and top-level layout only — ~155 tokens vs ~600 before.
- Slimmer system prompt: dropped the verbatim tool-name list and repeated per-tool rules (schemas + per-turn skill catalog already carry them).
### Tests
- New `tests/test_think.py` (9 tests): config round-trip/persistence, provider flag flow, `reasoning_effort` gating, rejection hints, both reasoning attributes, live-stream state machine.
- `test_agent_registers_skill_tool` now asserts skill registration via the tool schema instead of prompt prose.

## [1.4.0] - 2026-09-14
### Changed
- Republished 0.4.0 content under 1.x numbering so PyPI resolves it as latest (`pip install hazzel` now gets the skill system).

## [0.4.0] - 2026-09-13
### Added
- AGENTS.md startup support: Hazzel reads a repo-level `AGENTS.md` at launch and merges the repo instructions into the system prompt, so project-specific guidance is included automatically without extra setup.
- Skill system: drop a `SKILL.md` (frontmatter `name` + `description`) in `.hazzel/skills/<name>/`, `skills/<name>/`, `~/.config/hazzel/skills/<name>/`, or `~/.agents/skills/<name>/` and the model sees a per-turn catalog, loads instructions via the new read-only `skill(name)` tool (plan-mode safe), and follows them. `/skills` opens an interactive names-only picker (↑↓ navigate, Enter selects) that pastes `@<skill>` onto the input bar — type your message after it (prefill works on Windows via a native `msvcrt` input loop); `@skill` mentions resolve to the skill body, are traced as `skill` tool calls, and also surface in `@` autocomplete (files still win on name collisions). `/skills list` prints the catalog, `/skills <name>` previews one.

## [1.3.9] - 2026-09-13
### Removed
- Turn recap card (`show_turn_card` / `show_turn_from_trace`): turns no longer print the boxed `model ── path` Panel repeating the prompt, tool rows, and summary. Tool progress still streams live via `show_tool`; the final reply prints once via `show_hazzel_message`.

## [1.3.8] - 2026-09-13
### Added
- Fuzzy `@` file tags: fzf-style subsequence matching with consecutive/boundary/camelCase bonuses (`agnt`→`agent.py`, `sfty`→`safety.py`); exact tiers unchanged, fuzzy as fallback tier.
- Fuzzy `/` command palette: prefix → substring → fuzzy fallback over names + descriptions (`/cmt`→`/commit`, `/stus`→`/status`); Tab/Enter completes off the fuzzy list.
### Tests
- 7 new tests in `tests/test_ui_pure.py` (fuzzy scoring, mention transpositions, exact-first ordering, slash prefix/substring/fuzzy).

## [1.3.7] - 2026-09-13
### Added
- Persistent undo: `safety` spills checkpoints to `~/.config/hazzel/undo/` (0600 blobs + index) and restores after restart; `clear_undo_log()` for tests/logout.
- Destructive shell guard: `run_command` checkpoints `rm/rmdir` targets plus `mv/cp` destinations (globs resolved), not just `rm`.
- UI perf: `get_input` hoists model/context/plan footer out of the per-frame loop, `@` candidates recompute only on query change, mention walk TTL 10s→30s with `site/dist/build` prune; `show_tool` keeps append-only rows (cap 8) instead of last-only.
### Tests
- New `tests/test_safety.py` (14 tests): checkpoint/undo, caps, diff truncation, persist round-trip, `is_safe_command`, timeout/cwd guards, destructive targets, approval cancel, plan-mode blocks, raw-git blocks.

## [1.3.6] - 2026-09-12
### Added
- Parallel tool execution: independent read-only calls (`list/read/search`, `git status/diff`, `web_search`, `fetch_url`, `review_diff`, read-only `git_branch`/`github_pr`) run concurrently in a ThreadPoolExecutor with order preserved; write/run/commit batches stay sequential. World-class hardening: per-tool 60s timeout, `as_completed` live tool rows with ordered message commit, `Working… · N parallel` loader state.
- Streaming: live TTFT + token-count in the loader (`ttft 0.4s · N tokens`, throttled repaints), no double-print — tool-call turns still discard the preview buffer.
- Prompt caching: `stream_options.include_usage` on OpenAI/Groq streams for real (non-estimated) usage, `prompt_cache_key` extended to OpenRouter, Anthropic `cache_control` on tools + system + last user message, and full `message_start` cache-read usage accounting.
- 10x tool-speed system (`tool_cache.py`): ripgrep-first `search_files` with 20s result cache, TTL caches for `web_search`/`fetch_url`/`list_files`/filename index (writes invalidate), parallel multi-URL fetch (5 pages in one call's time), cached `git is_repo` plus single-call `status` branch parse. Measured: repeat search 134x, 3-page fetch 3x, 3x `is_repo` → 1 subprocess.

## [1.3.5] - 2026-09-12
### Added
- Live context meter in the input footer (`12.4%/1.0M (auto)`): per-model context windows, green/amber/red thresholds, session-burn tracking that climbs as you work.
- `◈ context` line in `/usage` with the same window fill.

## [1.3.4] - 2026-09-12
### Added
- `web_search` tool: keyless public-web search (titles, URLs, snippets), plan-mode safe; pairs with `fetch_url` for a search-then-fetch flow.
- `fetch_url` multi-page: accepts one `url` or up to 5 `urls` in a single call with per-page budget and `=== [i/n] ===` sections; single-URL output unchanged.

## [1.3.3] - 2026-09-12
### Added
- `apply_edits` tool: up to 10 unique-anchor edits across files, atomically validated with one diff preview, one approval, rollback plus undo support.
- Pi-style `run_command`: optional `timeout` (1-120s), `cwd` (project-jailed), `description` in approval; large output tails 4k chars with full log spilled to `/tmp/hazzel-bash-*.log`.
- `!command` shortcut: runs shell directly with no LLM call; `!` highlights bold white while typing; `! bash` hint in input footer.
### Fixed
- Hazzel identity guard: always Hazzel, never ChatGPT/Claude/Gemini/DeepSeek/Grok.
- Turn card only shows when a tool acted; greetings, single-char inputs, and read-only turns print just the reply.

## [1.3.2] - 2026-09-11
### Added
- Windows support with no new dependencies: plain-prompt fallbacks where Unix raw-terminal menus can't run, ANSI enabled via console mode, Windows-safe process control and read-only commands.

## [1.3.1] - 2026-09-11
### Added
- `/goal`: pin a session objective with acceptance criteria (persisted); every model turn steers toward it with a progress note.
- `/goal run`: executes the goal as a task; one-line setup (`/goal fix x | tests pass`), goal dimmed in the input footer, model proposes clearing when met.
- `/review @file` reviews one file; `/review codebase` reviews staged plus unstaged together; scope shows in the result card.
- `/review @file` reviews the full file content when it has no pending changes.
### Removed
- Prompt history recall across restarts; multiline input (Ctrl+J, full paste) stays.
- `/todo` task list and agent tool.

## [1.3.0] - 2026-09-11
### Added
- `/review`: senior-level code review (verdict plus severity-ranked findings with fixes) as a `review_diff` agent tool and slash command; read-only, plan-mode safe, with an offline heuristic fallback and a structured result card.

## [1.2.0] - 2026-09-11
### Added
- Multiline input (Ctrl+J for newline, full multiline paste) and Up/Down prompt history persisted across restarts at `~/.config/hazzel/history`.

## [1.1.0] - 2026-09-11
### Added
- Web reading: new `fetch_url` agent tool (read-only, plan-mode safe) for public docs and references, no new dependencies. Paste a URL and Hazzel summarizes the page instead of dumping raw text.
### Changed
- Model catalog trimmed to verified models only (35 total); README covers web reading.
- Extraction prefers main content, dedupes repeats, and condenses long pages to ~2k query-relevant chars (~10x fewer tokens).

## [0.1.9] - 2026-09-11
### Added
- `/docs`: full in-terminal usage guide (setup, loop, commands, approvals, git/PR workflows, troubleshooting).
- Slash commands echo as `❯ /cmd` divider card before running.
### Changed
- Brand accent pink to red, cleaner slash-menu selection, `/help` covers `/docs`, replies hug content without left indent.

## [0.1.8] - 2026-09-10
### Added
- New providers (8 total): Gemini, DeepSeek, OpenRouter via OpenAI-compatible endpoints, plus keyless local Ollama (`OLLAMA_HOST` override). No new dependencies.
- GitHub PRs via `gh`: `/pr` list/view/diff/checks (read-only) plus comment/create/merge/close with approval; new `github_pr` agent tool (plan-mode read-only for reads, raw `gh pr` writes blocked).

## [0.1.7] - 2026-09-10
### Added
- Collapsible thinking log: model reasoning (Groq/OpenAI `reasoning_content`, Anthropic thinking blocks) hides behind an Enter-to-expand prompt after each reply.
- `/init [file]`: generate an `AGENTS.md` project map (structure, stack, file counts) with diff preview and approval.
### Fixed
- Token streaming no longer paints a live preview, so replies can't appear twice (streamed tail + final print). The loader stays up until the single formatted reply prints.

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
