# Registering and syncing

Decorating a function only adds the command to your `CommandTree`, in your own process. Members see it once
the tree has been **synced**: `await tree.sync()` sends every command to Bisim in one request.

## Global commands and server commands

```python
await tree.sync()                       # the global commands
await tree.sync(guild=bisim.Object(id=GUILD_ID))  # the commands of one server
```

- A **global** command is available in every server the bot has been added to, and in the DM with the bot.
- A **server** command exists only in that server. Add one with `guild=` or `guilds=` on the decorator, or
  with `tree.add_command(command, guild=...)`, then sync that server.
- When a server has a command with the same name as a global one, the server's command is the one members see
  there.

While you work on a bot, copy the global commands to a test server and sync only that server:

```python
TEST_GUILD = bisim.Object(id=123456789012345678)


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        self.tree.copy_global_to(guild=TEST_GUILD)
        await self.tree.sync(guild=TEST_GUILD)
```

`copy_global_to()` only changes the tree in memory; the global commands stay global until you sync globally.

## A sync replaces the whole set

Bisim does not add or update commands one at a time: `sync()` replaces **all** the commands of that scope
(global, or one server) with what is in your tree. A command you removed from your code disappears from Bisim
at the next sync, and a command that only another program registered is deleted too. Sync from the one
program that holds all of your bot's commands.

To remove commands on purpose:

```python
tree.remove_command('ping')               # one global command
tree.clear_commands(guild=TEST_GUILD)     # every command of the test server
await tree.sync(guild=TEST_GUILD)
```

## When to sync

`setup_hook` runs once, after logging in and before the bot connects, so syncing there is fine for a small
bot. Do not sync in `on_ready` or on every message: each sync is a request that rewrites the set. Many bots
sync only when their owner asks, with a prefix command:

```python
import bisim
from bisim.ext import commands

bot = commands.Bot(command_prefix='!', intents=bisim.Intents.default())


@bot.command()
@commands.is_owner()
async def sync(ctx: commands.Context, scope: str = 'global') -> None:
    """Sends the slash commands to Bisim: !sync, or !sync here for this server only."""
    if scope == 'here' and ctx.guild is not None:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
    else:
        synced = await bot.tree.sync()
    await ctx.send(f'Synced {len(synced)} commands.')
```

## Reading what Bisim has

`sync()` returns the commands Bisim stored, as `app_commands.AppCommand` objects. `fetch_commands()` reads
them without changing anything:

```python
commands_now = await tree.fetch_commands()                # global
server_commands = await tree.fetch_commands(guild=TEST_GUILD)
for command in commands_now:
    print(command.id, command.name, command.mention)
```

`command.mention` is the `</name:id>` text that shows the command as a link in a message.

## Limits and errors

- Up to 100 commands per scope, context menu commands included; up to 25 options per command and up to 25
  subcommands per group.
- Up to 5 user and 5 message [context menu commands](context-menus.md) per scope.
- `sync()` raises `app_commands.CommandSyncFailure` when Bisim refuses the commands (a name or description
  it does not accept, for example), with the reason in the message, and `app_commands.MissingApplicationID`
  when it is called before the client has logged in.
- If a [translator](translations.md) is set, `sync()` runs it to add the Persian and English names.

See `CommandTree` in the [API reference](../../reference/app-commands.md).
