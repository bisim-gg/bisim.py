## What this changes

<!-- What a bot author gets from this change, in a sentence or two. Link the issue it closes, if any. -->

## Checklist

- [ ] Names and behaviour follow discord.py 2.x (only "Discord" becomes "Bisim").
- [ ] Features Bisim lacks raise `bisim.NotSupported`, never a silent no-op.
- [ ] Tests added or updated; `python -m pytest` passes.
- [ ] Public members have docstrings in the existing style (they become the API reference); `mkdocs build --strict` passes.
- [ ] The guide is updated in `docs/en/guide/` (and `docs/fa/guide/`, or I asked for a translation).
- [ ] `CHANGELOG.md` has a line under "Unreleased".
- [ ] No long dash or short dash characters were added.
