# Roadmap

Must-have features tracked against competitors. Shipped items stay listed so new
contributors can see how past work was scoped — active work is below.

## Shipped

| Feature | Why | Status |
|---|---|---|
| Session persistence | Save/restore conversation state across restarts. Every competitor has this; it's the #1 complaint for terminal agents that don't. | Shipped (single last-session slot per project in `~/.config/hazzel/sessions/` — save on exit, restore on launch, `/session restore` resumes, `/clear` archives for one restore) |
| AGENTS.md support | The de-facto standard for per-repo instructions (used by Codex, Copilot, OpenCode, Omp). Read it at startup, merge it into the system prompt, and keep repo guidance in context automatically. | Shipped (`/init` generates it; startup loads it automatically) |
| Local model support (Ollama) | One of Hazzel's stated values is BYOK — Ollama is the natural extension for offline/private use. | Shipped (keyless, `OLLAMA_HOST` override) |
| MCP (Model Context Protocol) | Now the standard extension mechanism. Even a minimal stdio transport gets you access to the entire MCP server ecosystem. | Shipped (minimal stdio transport in `mcp.py`: `.hazzel/mcp.json` + global config, lazy `initialize`/`tools/list`/`tools/call`, single skill-like `mcp` tool with read-only discovery, `/mcp` REPL command) |
| Parallel tool execution | Biggest speed win — run independent tool calls concurrently instead of sequentially. | Shipped (read-only batches run in ThreadPoolExecutor, writes stay sequential) |
| Reasoning model pass-through (`/think` mode) | Surface model reasoning levels directly; let power models think harder on demand. | Shipped (`/think on` toggles extended thinking: Anthropic `thinking`, OpenAI + GPT-OSS `reasoning_effort`, with graceful fallback when unsupported) |
| Diff review pass (`/review`) | Catch mistakes before they land: read the working diff back with the model and surface risks and gaps without leaving the terminal. | Shipped (read-only, working or `--staged` diff, 20-file/12k-char caps, untracked files included, deterministic offline fallback) |
| UI split (`ui/` package) | `ui.py` (~2.6k lines) owned all REPL rendering — split into navigable modules so contributors can find things. | Shipped (`src/hazzel/ui/`: `_state`, `input`, `stream`, `messages`, `git/`, `help_docs`, `usage`, `selectors`; `from hazzel import ui` keeps working) |

## Next

| Feature | Why | Status |
|---|---|---|
| Named sessions | Single last-session slot is limiting — name, list, and resume multiple sessions per project. | Planned — [good first issue](https://github.com/mukundzha/hazzel/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) |
| Richer MCP coverage | Resources/prompts plus SSE/streamable-HTTP transports beyond stdio. | Planned — [good first issue](https://github.com/mukundzha/hazzel/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) |
| Windows polish | Path handling, pager, and clipboard gaps on native Windows. | Planned — help wanted |
| `hazzel -p` scripting | Pipe diffs in, get summaries out — JSON output + exit codes for CI. | In progress (`-p` + `--output-format json` shipped; richer CI recipes coming) |

Have a use case that isn't covered? [Open a feature request](https://github.com/mukundzha/hazzel/issues/new?template=feature_request.md) — small and inspectable beats big and magical.
