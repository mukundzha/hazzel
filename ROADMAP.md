# Roadmap

Must-have features tracked against competitors.

| Feature | Why | Status |
|---|---|---|
| Session persistence | Save/restore conversation state across restarts. Every competitor has this; it's the #1 complaint for terminal agents that don't. | Planned |
| AGENTS.md support | The de-facto standard for per-repo instructions (used by Codex, Copilot, OpenCode, Omp). Read it at startup, merge into system prompt. | Shipped (`/init` generates it; Hazzel reads it for context) |
| Local model support (Ollama) | One of Hazzel's stated values is BYOK — Ollama is the natural extension for offline/private use. | Shipped (keyless, `OLLAMA_HOST` override) |
| MCP (Model Context Protocol) | Now the standard extension mechanism. Even a minimal stdio transport gets you access to the entire MCP server ecosystem. | Planned |
| Parallel tool execution | Biggest speed win — run independent tool calls concurrently instead of sequentially. | Shipped (read-only batches run in ThreadPoolExecutor, writes stay sequential) |
| Reasoning model pass-through (`/think` mode) | Surface model reasoning levels directly; let power models think harder on demand. | Planned |

Priority order: session persistence (still the #1 gap) → MCP support (even minimal stdio transport) → parallel tool execution → `/think` mode.
