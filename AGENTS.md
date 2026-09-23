# Hazzel (Hazzel context, 2026-09-14)

## Stack
Python (pyproject)

## Commands
install: pip install -e . --no-deps
build: python -m build
test: pytest
lint: ruff check .
typecheck: none configured (no mypy)

## Conventions
src-layout under `src/hazzel/`; flat modules plus `agent/`, `tools/`, `providers/`, `ui/` subpackages.
Ruff, line-length 100, target py310. Tests in `tests/` (pytest, test_*.py), all offline/mockable.
Changelog: Keep-a-Changelog format in CHANGELOG.md; every release gets a version heading.
README/ROADMAP updated alongside features; core rule: small and inspectable over framework.

## Layout
assets/
site/
src/
tests/
AGENTS.md
CHANGELOG.md
LICENSE
pyproject.toml
README.md
ROADMAP.md

## Gotchas
`__init__.py` only holds `__version__`; most API surface re-exported through `hazzel.agent`.
Undo snapshots live in `~/.config/hazzel/undo/` (200 events, 20/file, 2MB persist cap).
Tool results are size-capped (`MAX_TOOL_RESULT_CHARS`); history compacted to a token budget.
`ui/` package (`input`, `stream`, `messages`, `git/`, `selectors`, `usage`, `help_docs`, `_state`) and `formatter.py` own all terminal rendering/colors; config dir `~/.config/hazzel/`.
Non-obvious reads: `tool_cache.py` (tool-result caching), `fastpath.py` (zero-LLM shortcuts).
Stale PyPI install in site-packages can shadow `src/` — if imports look old, reinstall editable.

## Don't
no new deps without asking
no public API changes without changelog
no reformatting untouched files

_Regenerate with `/init`. Edit freely — Hazzel reads this file for context._
