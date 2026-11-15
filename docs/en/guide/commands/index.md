# Prefix commands

Besides slash commands, a bot can answer messages that start with a prefix, such as `!roll 2d6`.
`bisim.ext.commands` does this the way `discord.ext.commands` does: a command is a coroutine, its parameters are the
arguments, and the library parses, converts and checks them for you.

```python
import os

import bisim
from bisim.ext import commands

intents = bisim.Intents.default()
intents.message_content = True  # prefix commands read the text (switch it on at bisim.gg/developers)

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.command()
async def ping(ctx: commands.Context) -> None:
    """Checks that the bot is alive."""
    await ctx.send(f'Pong! {round(bot.latency * 1000)} ms')


bot.run(os.environ['BISIM_TOKEN'])
```

`commands.Bot` is a `bisim.Client` with commands, so everything a client does works here too, and it already has a
`CommandTree` for slash commands as `bot.tree`. A prefix command is read from the text of a message, so the bot
needs the privileged `message_content` intent, switched on at [bisim.gg/developers](https://bisim.gg/developers)
(see [Intents](../topics/events.md#intents)). Without it, only a prefix that mentions the bot
(`commands.when_mentioned`) works, and the library logs a warning at startup.

## The prefix

`command_prefix` can be:

- a string: `'!'`;
- a list of strings, where the first one that matches wins: `['!', '?']`;
- `commands.when_mentioned` (the bot's mention) or `commands.when_mentioned_or('!')` (the mention or `!`);
- a function, plain or async, that takes the bot and the message and returns a string or a list:

```python
prefixes = {}  # server id to prefix


async def get_prefix(bot: commands.Bot, message: bisim.Message):
    if message.guild is None:
        return commands.when_mentioned_or('!')(bot, message)
    return commands.when_mentioned_or(prefixes.get(message.guild.id, '!'))(bot, message)


bot = commands.Bot(command_prefix=get_prefix, intents=intents)
```

`case_insensitive=True` lets `!PING` work, and `strip_after_prefix=True` lets `!  ping` work. Messages from bots,
the bot's own included, never run commands.

If you add your own `on_message` with `@bot.event`, it replaces the one that runs commands; call
`await bot.process_commands(message)` at its end, or use `@bot.listen()` instead, which adds a listener next to it.

## Parameters

A command's parameters after `ctx` are its arguments. Each one takes a word; quotes keep several words together,
and the Persian «guillemets» count as quotes too:

```python
@bot.command()
async def greet(ctx: commands.Context, name: str, greeting: str = 'Hello') -> None:
    await ctx.send(f'{greeting}, {name}!')
# !greet Sara           -> Hello, Sara!
# !greet "Sara Ahmadi" Hi -> Hi, Sara Ahmadi!
```

`*args` takes any number of words as a tuple, and a keyword-only parameter after `*` takes the rest of the message
as one string, without quotes. A command can have one keyword-only parameter:

```python
@bot.command()
async def say(ctx: commands.Context, *, text: str) -> None:
    await ctx.send(text)


@bot.command()
async def total(ctx: commands.Context, *numbers: int) -> None:
    await ctx.send(f'{sum(numbers)}')
```

Annotations convert the words: `int`, `bisim.Member`, `bisim.TextChannel` and many more. See
[Converters](converters.md).

## The context

The first parameter is a `commands.Context`, everything about this use of the command:

- `ctx.message`, `ctx.author` (a `bisim.Member` in a server, a `bisim.User` in a DM), `ctx.guild` (`None` in a DM)
  and `ctx.channel`;
- `ctx.send(...)` sends to the channel, and `ctx.reply(...)` replies to the message;
- `ctx.command`, `ctx.prefix`, `ctx.clean_prefix` and `ctx.invoked_with` describe how it was called.

The context is a `Messageable`, so `ctx.send` takes everything `channel.send` takes: embeds, files and views.

## Options and groups

`@bot.command()` takes `name`, `aliases`, `help` (the docstring by default), `brief`, `description`, `usage`,
`hidden` and `enabled`. A group is a command with subcommands:

```python
@bot.group(aliases=['t'], invoke_without_command=True)
async def tag(ctx: commands.Context) -> None:
    """Short texts you can recall."""
    await ctx.send('Use !tag show <name> or !tag add <name> <text>.')


@tag.command()
async def show(ctx: commands.Context, name: str) -> None:
    await ctx.send(tags.get(name, 'There is no tag with that name.'))


@tag.command()
async def add(ctx: commands.Context, name: str, *, text: str) -> None:
    tags[name] = text
    await ctx.send(f'Saved {name}.')
```

With `invoke_without_command=True` the group's own body runs only when no subcommand was given; otherwise it runs
before the subcommand too, and `ctx.invoked_subcommand` tells which one follows.

## Errors

Errors from parsing, converting, [checks](checks.md) and [cooldowns](cooldowns.md) and exceptions raised inside a
command reach `on_command_error`. An exception from your own code arrives wrapped in `commands.CommandInvokeError`,
with the original in `error.original`. Without a handler, the library logs the error.

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
        await ctx.send(f'{error}\nUsage: `{ctx.clean_prefix}{ctx.command.qualified_name} {ctx.command.signature}`')
    else:
        raise error
```

A handler for one command only:

```python
@greet.error
async def greet_error(ctx: commands.Context, error: commands.CommandError) -> None:
    await ctx.send('Usage: !greet <name> [greeting]')
```

## Running the bot

`bot.run(token)` sets up logging and runs until you stop it. To do something before connecting, such as adding
[cogs](cogs.md), use `setup_hook`, or start the bot yourself:

```python
import asyncio


async def main() -> None:
    async with bot:
        await bot.add_cog(Music(bot))
        await bot.start(os.environ['BISIM_TOKEN'])


asyncio.run(main())
```

`examples/prefix_bot.py` in the repository is a complete bot with converters, checks, a group, a cog and a
background task. Every class and decorator is in the [API reference](../../reference/ext-commands.md).
