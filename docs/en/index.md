---
title: bisim.py
hide:
  - navigation
  - toc
---

<div class="bisim-hero" markdown>

<img class="bisim-hero__logo" src="assets/logo.svg" alt="">

<div class="bisim-hero__text" markdown>

# bisim.py

<p class="bisim-hero__tagline">The official Python library for Bisim bots, with the discord.py 2.x API.
Change the import and the token, and a discord.py bot runs on Bisim.</p>

<div class="bisim-hero__actions" markdown>
[Get started](guide/index.md){ .md-button .md-button--primary }
[Moving from discord.py](guide/moving-from-discord-py.md){ .md-button }
[API reference](reference/index.md){ .md-button }
</div>

</div>

</div>

```diff
-import discord
-from discord.ext import commands
+import bisim
+from bisim.ext import commands
```

<div class="bisim-features" markdown>

<div class="bisim-feature" markdown>
### Change two lines
A discord.py 2.x bot moves to Bisim by changing its imports and using a Bisim token. The classes, events,
decorators and arguments are the ones you know.
</div>

<div class="bisim-feature" markdown>
### Everything a bot needs
Slash commands with options, groups and autocomplete, context menus, buttons, select menus, modals, embeds,
prefix commands with cogs, and background tasks.
</div>

<div class="bisim-feature" markdown>
### Built for Bisim
Commands in Persian and English, Bisim's gateway and rate limits handled for you, and a clear
`bisim.NotSupported` for anything Bisim does not have.
</div>

<div class="bisim-feature" markdown>
### Typed and asyncio
Python 3.9 or newer, asyncio with aiohttp, type hints throughout, and tests that run without a network.
</div>

</div>

## A bot in twenty lines

```python
import bisim
from bisim import app_commands

intents = bisim.Intents.default()
intents.message_content = True  # to read '!hello' (switch it on at bisim.gg/developers)
client = bisim.Client(intents=intents)
tree = app_commands.CommandTree(client)


@tree.command(description='Check that the bot is alive')
async def ping(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


@client.event
async def on_ready() -> None:
    await tree.sync()
    print(f'Logged in as {client.user} ({client.user.id})')


@client.event
async def on_message(message: bisim.Message) -> None:
    if message.content == '!hello' and not message.author.bot:
        await message.reply(f'Hello, {message.author.display_name}!')


client.run('your bot token')
```

Install it with `pip install bisim.py`, create the bot in Bisim's Developer Portal
([bisim.gg/developers](https://bisim.gg/developers)), and follow the [guide](guide/index.md) from there.

!!! note "Built on discord.py"

    Much of bisim.py, its documentation included, comes from [discord.py](https://github.com/Rapptz/discord.py)
    by Rapptz and its contributors, adapted to Bisim's API. That is what lets a discord.py bot move over
    unchanged. Thank you to everyone who made discord.py.
