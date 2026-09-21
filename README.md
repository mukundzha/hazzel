<p align="center">
  <img src="assets/logo.png" alt="Hazzel" width="140" />
</p>

<h1 align="center">Hazzel</h1>

<p align="center">
  <b>A terminal coding agent you can actually read.</b><br/>
  Bring your own key. No subscription. Every change shown as a diff before it touches disk.
</p>

<p align="center">
  <a href="https://github.com/mukundzha/hazzel/actions/workflows/ci.yml">
    <img src="https://github.com/mukundzha/hazzel/actions/workflows/ci.yml/badge.svg" alt="CI">
  </a>
  <a href="https://pypi.org/project/hazzel/">
    <img src="https://img.shields.io/pypi/v/hazzel" alt="PyPI">
  </a>
  <a href="https://pypistats.org/packages/hazzel">
    <img src="https://img.shields.io/badge/downloads-4k%2Fmonth-blue" alt="Downloads">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-AGPL--3.0--or--later-green" alt="License">
  </a>
  <a href="https://github.com/mukundzha/hazzel/stargazers">
    <img src="https://img.shields.io/github/stars/mukundzha/hazzel?style=social" alt="Stars">
  </a>
</p>

![Hazzel demo](assets/demo.gif)

> Built with help from [@ronaldsterners](https://github.com/ronaldsterners) · [@Gambit-Checkmate](https://github.com/Gambit-Checkmate) (first external PR, v1.5.1) · [@DYNOSuprovo](https://github.com/DYNOSuprovo) (#12) — [good first issues welcome](https://github.com/mukundzha/hazzel/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

**Recently shipped:** `NO_COLOR` support — piped logs and dumb terminals stay plain (#12, @DYNOSuprovo) · v1.5.3 SEO landing page · confirmation prompts accept `yes` — first external contribution (@Gambit-Checkmate, 1.5.1) · `/review` (1.5.0) · background `!cmd &` jobs (1.4.9) — [full changelog](CHANGELOG.md)

## Try it in your project

Every agent claims transparency. Hazzel is ~10k lines of Python you can trace end to end — `agent/core.py` is the whole loop, `tools/` is every action it can take, `safety.py` is the entire undo system — and it stops before every write to show you what's about to happen.

```bash
pip install hazzel
export GROQ_API_KEY="..."   # or skip this and pick a provider inside with /model
cd your-project
hazzel
```

```text
❯ Fix the failing test in tests/test_agent.py

  ● read_file   tests/test_agent.py
  ● edit_file   src/hazzel/agent/core.py
  ● run_command pytest -q — passed
```

**Things you can say on day one**

```text
❯ /review --staged
❯ /commit
❯ what does agent/fastpath.py do — is it just caching?
❯ @screenshot.png make the nav match this
```

No project quiz, no config ceremony — the read-only commands answer instantly, and anything that touches disk stops at a diff first.

## Why it's built this way

Most agents ask you to trust a black box. Hazzel asks you to trust three specific, inspectable mechanisms instead:

* **Every write is a diff you approve, first.** Shell commands too — except a small allowlist of true read-onlys (`ls`, `cat`, `git status`) that skip the queue.
* **Every write is checkpointed, automatically.** Prior bytes snapshotted to `~/.config/hazzel/undo/` (200 events, 20 per file) before anything lands. `/undo` restores them.
* **Commands are sandboxed to your project root.** `git reset --hard` and `clean` are blocked outright; raw `git commit` is steered into `/commit` with its own diff preview.

You can verify all three claims in about 200 lines: `src/hazzel/safety.py`, `src/hazzel/tools/run_command.py`.

```mermaid
flowchart LR
    you["you — prompt, @file, slash command"] --> repl["__main__.py"]
    repl --> loop["agent/core.py — the whole loop"]
    loop --> fast["agent/fastpath.py — zero-LLM answers for reads"]
    loop --> dispatch["agent/dispatch.py"]
    dispatch --> gate["safety.py — approve · sandbox · checkpoint"]
    gate --> tools["tools/ — 13 actions"]
    loop --> llm["providers/ — 8 backends, your key"]
    loop --> term["ui.py + formatter.py — your terminal"]
```

## How it compares

Where Hazzel stands out, measured against the tools people actually compare it to:

| Capability | Hazzel | Aider | Cloud agents |
| ---------- | ------ | ----- | ------------ |
| Price model | free · BYOK | free · BYOK | subscription |
| Local models | Ollama, keyless, zero config | supported, needs env setup | no |
| Readable end to end | ~10k lines | tens of thousands | closed source |
| `/undo` without git | byte-level snapshots | git-commit based | varies |
| MCP client | stdio, zero new deps | — | varies |

Aider is excellent — this is about fit, not superiority.

## What it actually does

| What | In practice |
| ---- | ----------- |
| Understands your repo | Reads, searches, lists. `@path` pins a file into context; `/init` drafts an `AGENTS.md` map so every session starts oriented. |
| Ships real changes | Diff-preview editing, `/undo` checkpoints, shell with timeouts, `!cmd &` background jobs via `/jobs`, `fetch <url>` for docs, `@image.png` for vision-capable models. |
| Speaks fluent git | `/status` · `/diff --staged` · `/review` · `/commit` (auto-drafted Conventional message) · `/log` — reads run instantly, zero LLM round-trip. |
| Extends without lock-in | Minimal MCP stdio client — standard library only, any server via `.hazzel/mcp.json`. `SKILL.md` skills load on demand. Neither needs Hazzel-specific tooling to author. |
| Shows you the bill | Provider-reported tokens parsed into real dollars, logged locally — not estimated. Live `tokens · $` line every turn; `/usage today\|week\|month --by-model`, `/budget`. |
| Remembers between sessions | Per-project sessions persist with `/session restore`. `/plan on` explores read-only first; `/think on` buys extended reasoning for hard edits. |
| Works in a pipeline | `hazzel -p "prompt"` runs one turn and exits — pipe a diff in, get a summary out. `--output-format json` + real exit codes for CI. |

See [five copy-paste sessions](docs/EXAMPLES.md) for concrete `/review`, `/commit`, image, background-job, and pipeline examples.

## Providers — bring your own key, no subscription

Eight providers: OpenAI, Anthropic, Mistral, Gemini, DeepSeek, OpenRouter (100+ models, one key), Groq (default: `openai/gpt-oss-120b`) — set one env var (`OPENAI_API_KEY`, `GROQ_API_KEY`, …) and skip the prompt entirely.

Ollama runs fully local and needs no key at all. Switch anytime with `/model`. Nothing is metered by Hazzel — you pay your provider directly, or nothing at all if you're running local.

## Commands at a glance

| Group      | Commands                                                                               |
| ---------- | -------------------------------------------------------------------------------------- |
| Modes      | `/model` · `/plan on\|off` · `/think on\|off` · `/goal [@objective]`                   |
| Git        | `/status` · `/diff [--staged]` · `/review [--staged]` · `/commit` · `/log`            |
| Cost       | `/usage [today\|week\|month\|--by-model]` · `/budget`                                  |
| Extend     | `/mcp [server [tool]]` · `/skills [name]` · `/init`                                    |
| Transcript | `/export` · `/copy` · `/retry` · `/jobs` · `/undo [n]` · `/session restore` · `/clear` |

Type `/` to filter live, `@` to attach a file, `/docs` for the full guide without leaving the terminal.

## What it's honest about not being

v1.5.3 + `NO_COLOR` (unreleased), early-stage. No autonomous PRs, no cloud dashboard, no session sync across machines. It doesn't replace your editor — it sits in the terminal next to it, and it stays small on purpose.

If you need a heavier, more automated agent, better options exist. If you want to see exactly what's about to happen to your files before it happens, this is built for that.

## Support Hazzel

<a href="https://star-history.com/#mukundzha/hazzel&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mukundzha/hazzel&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=mukundzha/hazzel&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=mukundzha/hazzel&type=Date" />
 </picture>
</a>

Hazzel is free and open-source, and it plans to stay both. The cheapest support costs nothing: use it, report what breaks, or send a PR.

If you'd rather throw money at the problem, that works too — it goes straight into maintainer time for docs, fixes, and reviews:

<p align="center">
  <a href="https://paypal.me/mukundzi">
    <img src="https://img.shields.io/badge/Donate-PayPal-0070BA?sHazzel: the open source terminal coding agenttyle=for-the-badge&logo=paypal&logoColor=white" alt="Donate via PayPal">
  </a>
</p>

## Who's behind this

<p align="left">
  <table align="left">
    <tr>
    <td align="left">
      <a href="https://github.com/mukundzha">
        <img src="https://avatars.githubusercontent.com/mukundzha?v=4&s=80" width="80" alt="mukundzha"/><br/>
        <sub><b>Mukund Jha</b><br/>creator</sub>
      </a>
    </td>
    <td align="left">
      <a href="https://github.com/ronaldsterners">
        <img src="https://avatars.githubusercontent.com/ronaldsterners?v=4&s=80" width="80" alt="ronaldsterners"/><br/>
        <sub><b>ronaldsterners</b></sub>
      </a>
    </td>
    <td align="left">
      <a href="https://github.com/Gambit-Checkmate">
        <img src="https://avatars.githubusercontent.com/Gambit-Checkmate?v=4&s=80" width="80" alt="Gambit-Checkmate"/><br/>
        <sub><b>Gambit-Checkmate</b></sub>
      </a>
    </td>
    <td align="left">
      <a href="https://github.com/DYNOSuprovo">
        <img src="https://avatars.githubusercontent.com/DYNOSuprovo?v=4&s=80" width="80" alt="DYNOSuprovo"/><br/>
        <sub><b>DYNOSuprovo</b></sub>
      </a>
    </td>
  </tr>
  </table>
</p>

Every PR lands through the same door: reviewed, CI-verified on four Python versions, credited in the release notes. ronaldsterners, Gambit-Checkmate, and DYNOSuprovo all started with a good first issue — the next row is one PR away.

## Contributing

Issues and PRs genuinely welcome — `ROADMAP.md` tracks what's next, `CONTRIBUTING.md` has the ground rules (small, inspectable, no new deps without asking), and good first issues are labeled as such.

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).

Why AGPL? It keeps hosted clones open — if you run Hazzel as a service, share your changes back. Normal use (install it, use it at work, ship code it helped you write) is unaffected — only re-hosting Hazzel itself triggers share-alike. If the license blocks adoption at your company, [open an issue](https://github.com/mukundzha/hazzel/issues/new?template=feature_request.md) — dual-licensing is on the table with enough demand.

---

<p align="center">
  Small tools stay small because people who find them useful say so.<br/>
  If Hazzel is now sitting in your terminal next to your editor,
  <a href="https://github.com/mukundzha/hazzel">a star</a>
  is how the next person finds it too.
</p>
