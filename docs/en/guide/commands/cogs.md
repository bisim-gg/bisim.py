# Cogs and extensions

As a bot grows, one file becomes hard to work with. A **cog** groups commands, listeners and the state they share
into a class, and an **extension** is a module the bot loads, unloads and reloads while it runs.

## A cog

```python
import bisim
from bisim.ext import commands


class Greetings(commands.Cog):
    """Says hello."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.last_member = None

    @commands.Cog.listener()
    async def on_member_join(self, member: bisim.Member) -> None:
        channel = member.guild.system_channel
        if channel is not None:
            await channel.send(f'Welcome, {member.mention}!')

    @commands.command()
    async def hello(self, ctx: commands.Context, *, member: bisim.Member = None) -> None:
        """Says hello to you or to someone else."""
        member = member or ctx.author
        if self.last_member is None or self.last_member.id != member.id:
            await ctx.send(f'Hello {member.display_name}!')
        else:
            await ctx.send(f'Hello {member.display_name}... this feels familiar.')
        self.last_member = member
```

- Commands in a cog use `@commands.command()` and `@commands.group()`, not `@bot.command()`, and take `self` first.
- Listeners use `@commands.Cog.listener()`. The method's name is the event (`on_member_join`); to use another
  method name, pass the event: `@commands.Cog.listener('on_message')`.
- Every name in the class is shared by its commands, so `self.bot` and `self.last_member` live as long as the cog.

Add the cog with `await bot.add_cog(...)`, which is a coroutine. `setup_hook` is the usual place:

```python
class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.add_cog(Greetings(self))


intents = bisim.Intents.default()
intents.members = True  # on_member_join
intents.message_content = True  # prefix commands
bot = MyBot(command_prefix='!', intents=intents)
```

`bot.get_cog('Greetings')` returns the cog, `bot.cogs` lists them, and `await bot.remove_cog('Greetings')` removes
one with its commands and listeners. A cog's name is its class name; `class Greetings(commands.Cog, name='Hello')`
changes it, and the class docstring is its description in the help command.

## Special methods

A cog can define these methods; each one applies to the cog only:

| Method | What it does |
| --- | --- |
| `async def cog_load(self)` | runs when the cog is added; a good place to open a connection |
| `async def cog_unload(self)` | runs when the cog is removed, and when the bot closes |
| `def cog_check(self, ctx)` | a [check](checks.md) for every command of the cog; can be a coroutine |
| `async def cog_command_error(self, ctx, error)` | an error handler for the cog's commands |
| `async def cog_before_invoke(self, ctx)`, `async def cog_after_invoke(self, ctx)` | run before and after each command |
| `def bot_check(self, ctx)` | a global check, registered while the cog is loaded |

A cog can hold slash commands too: methods decorated with `@app_commands.command()` join the bot's tree when the
cog is added. A `commands.GroupCog` makes the cog itself a slash command group, named by `group_name=` (see
[Subcommands and groups](../slash-commands/groups.md)); only the cog's slash commands join that group.

## Extensions

An extension is a Python module with a `setup` function, usually a coroutine, that receives the bot:

```python
# cogs/greetings.py
from bisim.ext import commands


class Greetings(commands.Cog):
    ...


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Greetings(bot))
```

Load it by its import path:

```python
class MyBot(commands.Bot):
    async def setup_hook(self) -> None:
        await self.load_extension('cogs.greetings')
```

`await bot.unload_extension('cogs.greetings')` removes its cogs, commands and listeners and calls its `teardown(bot)`
function when there is one. `await bot.reload_extension('cogs.greetings')` unloads and loads it again in one step,
so you can change a command without restarting the bot; if the new code fails to load, the old version is put back
and the error is raised.

```python
@bot.command()
@commands.is_owner()
async def reload(ctx: commands.Context, name: str) -> None:
    await bot.reload_extension(f'cogs.{name}')
    await ctx.send(f'Reloaded {name}.')
```

Loading can raise `commands.ExtensionNotFound`, `commands.ExtensionAlreadyLoaded`, `commands.NoEntryPointError`
(no `setup`) or `commands.ExtensionFailed` (the module or its `setup` raised). `bot.extensions` maps the names of
the loaded extensions to their modules.

The cog and extension classes are in the [API reference](../../reference/ext-commands.md).
