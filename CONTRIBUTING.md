# Contributing to Hazzel

Thanks for helping out! Hazzel is small on purpose, so the best contributions keep it that way.

## Ground rules

- **Stay small.** Prefer simple, readable code over clever or feature-heavy code.
- **Keep it safe.** Every change to files, shell, or git must go through user approval. Don't weaken that.
- **Open an issue first** for big changes or new features, so we can agree before you build.

## Setup

```bash
git clone https://github.com/mukundzha/hazzel.git
cd hazzel
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
```

Requires Python 3.10+.

## Making a change

1. Fork the repo and create a branch: `git checkout -b my-change`
2. Make your change and add or update tests in `tests/`
3. Run `pytest -q` and make sure everything passes
4. Add a line to [CHANGELOG.md](CHANGELOG.md)
5. Open a pull request with a short description of what and why

Small, focused PRs get merged fastest.

First-time contributors: your first CI run waits for a maintainer's approval before it
starts — that's a standard GitHub guard for forks, not a rejection. After your first
merged PR it runs automatically.

## Reporting bugs

Open an [issue](https://github.com/mukundzha/hazzel/issues) with:

- What you ran and what you expected
- What actually happened
- Your OS, Python version, and Hazzel version

## License

By contributing, you agree your work is licensed under [Apache-2.0](LICENSE).

