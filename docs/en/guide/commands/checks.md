# Checks

A **check** decides whether someone may run a command. Checks run before the arguments are converted; if one fails,
the command does not run and `on_command_error` receives a `commands.CheckFailure` (or a subclass that says why).

## Built-in checks

Add them as decorators under `@bot.command()`:

```python
@bot.command()
@commands.guild_only()
@commands.has_permissions(manage_messages=True)
@commands.bot_has_permissions(manage_messages=True)
async def clean(ctx: commands.Context, count: commands.Range[int, 1, 100] = 10) -> None:
    deleted = await ctx.channel.purge(limit=count + 1)
    await ctx.send(f'Deleted {len(deleted) - 1} messages.', delete_after=5)
```

| Check | Passes when | Fails with |
| --- | --- | --- |
| `has_permissions(**perms)` | the author has these permissions in this channel | `MissingPermissions` |
| `bot_has_permissions(**perms)` | the bot has them in this channel | `BotMissingPermissions` |
| `has_guild_permissions(**perms)` | the author has them server wide | `MissingPermissions` |
| `bot_has_guild_permissions(**perms)` | the bot has them server wide | `BotMissingPermissions` |
| `has_role(item)` | the author has the role, by ID or by name | `MissingRole` |
| `has_any_role(*items)` | the author has one of the roles | `MissingAnyRole` |
| `bot_has_role(item)`, `bot_has_any_role(*items)` | the same, for the bot | `BotMissingRole`, `BotMissingAnyRole` |
| `guild_only()` | the command is used in a server | `NoPrivateMessage` |
| `dm_only()` | the command is used in a DM | `PrivateMessageOnly` |
| `is_owner()` | the author owns the bot | `NotOwner` |
| `is_nsfw()` | the channel is marked age restricted, or it is a DM | `NSFWChannelRequired` |

Permission names are those of `bisim.Permissions`, such as `manage_messages`, `kick_members`, `ban_members`,
`manage_roles` and `moderate_members`; a name that does not exist raises `TypeError` when the bot starts. Channel
checks use the channel's permission overwrites, which the library loads from Bisim the first time a check needs
them.

`is_owner()` asks Bisim for the application's owner once, unless you pass `owner_id=` or `owner_ids=` to
`commands.Bot`.

## Checks of your own

`commands.check()` turns a predicate into a check. The predicate takes the context and returns `True` to allow the
command; it can be a plain function or a coroutine:

```python
def in_channel(name: str):
    def predicate(ctx: commands.Context) -> bool:
        return getattr(ctx.channel, 'name', None) == name

    return commands.check(predicate)


@bot.command()
@in_channel('bot-commands')
async def daily(ctx: commands.Context) -> None:
    await ctx.send('Here is your daily reward.')
```

Returning `False` raises a plain `CheckFailure`. To tell the person why, raise your own subclass of it:

```python
class NotInBotChannel(commands.CheckFailure):
    pass


def in_bot_channel():
    async def predicate(ctx: commands.Context) -> bool:
        if getattr(ctx.channel, 'name', None) != 'bot-commands':
            raise NotInBotChannel('Use this command in #bot-commands.')
        return True

    return commands.check(predicate)
```

`commands.check_any()` passes when any one of the checks given to it passes, and raises `CheckAnyFailure` otherwise:

```python
@bot.command()
@commands.check_any(commands.is_owner(), commands.has_role('Moderator'))
async def announce(ctx: commands.Context, *, text: str) -> None:
    await ctx.send(text)
```

## Checks for every command

A global check runs before every command of the bot. Register it with `@bot.check`:

```python
@bot.check
async def not_blocked(ctx: commands.Context) -> bool:
    return ctx.author.id not in blocked_users
```

Inside a [cog](cogs.md), a `cog_check` method is a check for every command of that cog:

```python
class Admin(commands.Cog):
    async def cog_check(self, ctx: commands.Context) -> bool:
        return ctx.guild is not None and ctx.author.guild_permissions.administrator
```

## Telling people what went wrong

Handle the failures in `on_command_error`, from the most specific class to the most general:

```python
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(f'You need these permissions: {", ".join(error.missing_permissions)}.')
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f'I need these permissions: {", ".join(error.missing_permissions)}.')
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send('This command works in servers only.')
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(str(error) or 'You cannot use this command here.')
```

Checks for slash commands work differently, on the interaction instead of a context: see
[Permissions and checks](../slash-commands/permissions.md). The check decorators are in the
[API reference](../../reference/ext-commands.md).
