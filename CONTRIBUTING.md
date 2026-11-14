# Contributing to bisim.py

Thank you for helping. bisim.py is the official Python library for Bisim bots, and contributions of every
size are welcome: a typo fix, a test, a missing method, a translation of a guide page.

## The rule that shapes everything

bisim.py mirrors the public surface of discord.py 2.x: class, method, property, event, decorator and argument
names, signatures, defaults and behaviour. A discord.py bot should run on Bisim by changing the imports and
the token. The one renaming rule: a word "Discord" in a name becomes "Bisim" (`DiscordException` is
`BisimException`). Nothing else is renamed.

When Bisim does not have a feature, the method exists and raises `bisim.NotSupported` with a message naming
the feature. It never silently does nothing.

bisim.py is built on [discord.py](https://github.com/Rapptz/discord.py) (MIT), and much of its code and its
docstrings come from there, adapted to Bisim's API. Adapting more of discord.py is fine, as long as the result
is true for Bisim. Keep discord.py's copyright notice in `LICENSE` and the Credits section in the README.

## Getting started

```sh
git clone https://github.com/bisim-gg/bisim.py.git
cd bisim.py
python -m venv .venv
.venv/bin/pip install -e ".[test]"     # Windows: .venv\Scripts\pip install -e ".[test]"
.venv/bin/pytest
```

Useful commands:

| Command | What it does |
| --- | --- |
| `pytest` | the test suite, with a fake gateway and recorded responses |
| `python -m build` | the sdist and the wheel in `dist/` |
| `pip install -e ".[docs]"` | the documentation tools (Python 3.10 or newer) |
| `mkdocs build --strict` | the guide and the API reference in `site/` |

The tests never call a live Bisim service. If you need to see a change working end to end, run a bot against
a Bisim server for development with `api_url` and `gateway_url` pointing at it (see "A local Bisim server" in
the guide).

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Create a branch, make the change, and add or update tests.
3. Document every public member with a docstring in the existing style: reStructuredText with numpy style
   sections, as in discord.py. The API reference is generated from them (`docs/_ext/griffe_rst.py` turns
   them into Markdown), so `mkdocs build --strict` must pass.
4. If the change affects how a bot is written, update the guide in `docs/en/guide/` and its Persian version
   in `docs/fa/guide/`. If you cannot write Persian, say so in the pull request and we will translate it.
5. Add a line to `CHANGELOG.md` under an "Unreleased" heading.
6. Run `pytest` and `mkdocs build --strict` before opening the pull request.

## Style

- Python 3.9 or newer, asyncio and aiohttp, type hints on public members, no new runtime dependencies
  without a discussion.
- Write in plain English. Do not use the long dash or the short dash characters anywhere (code comments,
  docs, commit messages); use a comma, a colon or a full stop. A plain hyphen is fine.
- Persian text uses half-spaces (ZWNJ) where they belong, such as «می‌شود» and «پیام‌ها», and writes
  «بی‌سیم» with its half-space.
- Commit messages say what a user of the library gets, in a sentence or two.

## Reporting a security problem

Please do not open a public issue. See [SECURITY.md](./SECURITY.md).

## Code of conduct

Everyone taking part is expected to follow the [code of conduct](./CODE_OF_CONDUCT.md).
