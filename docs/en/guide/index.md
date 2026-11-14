# Introduction

bisim.py is the official Python library for building bots on [Bisim](https://bisim.gg). It has the
discord.py 2.x API: the same `Client`, events, models, slash commands, views, modals and `ext.commands`, so a
bot written for discord.py runs on Bisim once you change the imports and use a Bisim token.

```diff
-import discord
-from discord import app_commands
-from discord.ext import commands, tasks
+import bisim
+from bisim import app_commands
+from bisim.ext import commands, tasks
```

Underneath, bisim.py talks to Bisim's own REST API and gateway. Ids, permission bits, channel types and enum
values use Discord's numbers, so what you know about them still holds.

## What you need

- Python 3.9 or newer.
- Some Python, including `async` and `await`. If coroutines are new to you, read the
  [asyncio documentation](https://docs.python.org/3/library/asyncio.html) first; every bot is built on them.
- A Bisim account and a server where you can add a bot.

## How this guide is laid out

**Getting started** takes you from nothing to a running bot: [installing](installing.md) the library,
[creating your application](creating-an-application.md) in Bisim and writing [your first bot](your-first-bot.md).

**Slash commands** cover `app_commands`: [creating commands](slash-commands/index.md),
[syncing them to Bisim](slash-commands/syncing.md), [responding](slash-commands/responding.md),
[options and choices](slash-commands/options.md), [autocomplete](slash-commands/autocomplete.md),
[groups](slash-commands/groups.md), [context menus](slash-commands/context-menus.md),
[permissions and checks](slash-commands/permissions.md) and [translations](slash-commands/translations.md).

**Buttons, menus and modals** show `bisim.ui`: [views and buttons](components/buttons.md),
[select menus](components/select-menus.md) and [modals](components/modals.md).

**Prefix commands** cover `bisim.ext.commands`, for bots that read commands like `!help` from messages:
[commands](commands/index.md), [converters](commands/converters.md), [checks](commands/checks.md),
[cooldowns](commands/cooldowns.md), [cogs](commands/cogs.md) and [the help command](commands/help.md).

**Topics** go deeper into [events](topics/events.md), [messages](topics/messages.md),
[embeds](topics/embeds.md), [members and roles](topics/members-and-roles.md),
[permissions](topics/permissions.md), [background tasks](topics/tasks.md) and receiving interactions on an
[Interactions URL](topics/interactions-url.md).

**More** has the page for [moving from discord.py](moving-from-discord-py.md), how to run a bot against a
[local Bisim server](local-server.md) and the [FAQ](faq.md).

Every class, method and event is listed in the [API reference](../reference/index.md), generated from the
library's docstrings.

## Coming from discord.py

Most bots run unchanged. Intents are accepted and change nothing, and what Bisim does not have (voice
connections for bots, threads, stage and forum channels, scheduled events, sharding) raises
`bisim.NotSupported` instead of failing silently. [Moving from discord.py](moving-from-discord-py.md) lists
every difference.

!!! note "Credits"

    bisim.py is built on [discord.py](https://github.com/Rapptz/discord.py) by Rapptz and its contributors,
    and parts of this guide are adapted from discord.py's documentation. Both are MIT licensed.
