# bisim.py

[![PyPI](https://img.shields.io/pypi/v/bisim.py.svg)](https://pypi.org/project/bisim.py/)
[![CI](https://github.com/bisim-gg/bisim.py/actions/workflows/ci.yml/badge.svg)](https://github.com/bisim-gg/bisim.py/actions/workflows/ci.yml)

The official Python library for [Bisim](https://bisim.gg) bots.

It has the discord.py 2.x API: a bot written for discord.py runs on Bisim by
changing `import discord` to `import bisim` (and `from discord.ext import commands`
to `from bisim.ext import commands`). Events, models, slash commands, buttons,
select menus, modals and `ext.commands` work the way you know them.

Python 3.9 or newer, asyncio with aiohttp.

## Install

```sh
pip install bisim.py
```

Signed interactions on an Interactions URL need PyNaCl:

```sh
pip install "bisim.py[http]"
```

## A bot in 20 lines

```python
import bisim
from bisim import app_commands

intents = bisim.Intents.default()  # accepted for compatibility; Bisim has no intents
client = bisim.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction):
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user} ({client.user.id})')


@client.event
async def on_message(message: bisim.Message):
    if message.content == '!hello' and not message.author.bot:
        await message.reply(f'Hello, {message.author.display_name}!')


client.run('your bot token')
```

Create an application and copy its token in Bisim: Settings, Applications.
More examples are in [`examples/`](examples/): slash commands and context menus,
buttons with a select menu and a modal, and a prefix command bot with a cog and a
background task.

## Documentation

- **Guide:** [English](https://bisim-gg.github.io/bisim.py/guide/) and
  [فارسی](https://bisim-gg.github.io/bisim.py/fa/guide/), from your first bot to slash
  commands, buttons, modals, prefix commands, cogs and background tasks.
- **API reference:** [every class, function and event](https://bisim-gg.github.io/bisim.py/reference/),
  generated from the docstrings.
- **Moving from discord.py:** [what changes and what Bisim does not have](https://bisim-gg.github.io/bisim.py/guide/moving-from-discord-py/).
- **Bisim developer docs:** [docs.bisim.gg](https://docs.bisim.gg), for webhooks, bots
  and the HTTP API underneath this library.

The same site is also served at [docs.bisim.gg/py](https://docs.bisim.gg/py/).

## Moving from discord.py

- Change the imports. A word "Discord" in a name becomes "Bisim":
  `discord.DiscordException` is `bisim.BisimException`, `discord.utils` is `bisim.utils`.
- Intents are accepted and change nothing: a bot sees what its permissions let it see.
- What Bisim does not have (voice connections, threads, stage and forum channels,
  scheduled events, sharding) raises `bisim.NotSupported`, a `ClientException`.
- A local Bisim server: `bisim.Client(api_url='http://localhost:3000/api',
  gateway_url='ws://localhost:4000/ws')`, or the `BISIM_API_URL` and
  `BISIM_GATEWAY_URL` environment variables.

The [full page](https://bisim-gg.github.io/bisim.py/guide/moving-from-discord-py/) covers
startup, embeds, files, interactions and everything that raises `NotSupported`.

## Contributing

Issues and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first,
and follow the [code of conduct](CODE_OF_CONDUCT.md). Report security problems
privately as described in [SECURITY.md](SECURITY.md).

```sh
python -m venv .venv
.venv/bin/pip install -e ".[test]"     # Windows: .venv\Scripts\pip
.venv/bin/pytest
```

The tests never touch a real server: REST calls are answered from recorded
payloads and the gateway is a small fake served on localhost.

The documentation needs Python 3.10 or newer:

```sh
.venv/bin/pip install -e ".[docs]"
.venv/bin/mkdocs build --strict        # the guide and the API reference in site/
```

## Credits

bisim.py is built on [discord.py](https://github.com/Rapptz/discord.py) by Rapptz
and its contributors. Much of its code and documentation comes from discord.py,
adapted to Bisim's API, which is what lets a discord.py bot move over unchanged.
Thank you to everyone who made discord.py.

## License

MIT, see [LICENSE](LICENSE). It carries discord.py's copyright notice next to
Bisim's, as discord.py's license asks.
