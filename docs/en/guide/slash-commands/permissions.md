# Permissions and checks

Two kinds of rules decide who may run a command. **Default permissions** and **contexts** are sent to Bisim
with the command, and Bisim enforces them before your bot hears anything. **Checks** run in your bot when the
command arrives, and a failed check goes to your error handlers.

## Default permissions

```python
@client.tree.command(description='Ban a member')
@app_commands.default_permissions(ban_members=True)
@app_commands.guild_only()
async def ban(interaction: bisim.Interaction, member: bisim.Member, reason: Optional[str] = None) -> None:
    await member.ban(reason=reason)
    await interaction.response.send_message(f'Banned {member}.', ephemeral=True)
```

- Bisim hides the command from members who lack any of the listed permissions, and refuses it in a channel
  where they lack them. Administrators can always use it.
- `@app_commands.default_permissions()` with no permissions keeps the command to administrators.
- The names are the attributes of `bisim.Permissions`, with Discord's permission bits.
- Bisim has no per command permission overrides: server owners cannot change who may use a command, and
  `AppCommand.fetch_permissions()` raises `bisim.NotSupported`.
- On a group, put it on the group; on a subcommand it is ignored.

Whatever the command, in a server the member also needs **Use Application Commands** in the channel and must
not be timed out.

## Where a command runs

Bisim runs commands in servers and in the DM with the bot, and by default both are allowed. To keep a
command to one of them:

- `@app_commands.guild_only()`: servers only.
- `@app_commands.dm_only()`: the DM with the bot only.
- `@app_commands.allowed_contexts(guilds=True, dms=False)`: the same choice, spelled out.

Bisim enforces these too, so no error handler is called. `CommandTree(client, allowed_contexts=...)` sets a
default for every command in the tree. `private_channel_only()` keeps a command to the DM with the bot, since
Bisim has no other private context for commands.

## Checks

The checks in `app_commands.checks` run in your bot:

```python
from bisim.app_commands import checks


@client.tree.command(description='Delete recent messages')
@checks.has_permissions(manage_messages=True)       # the member, in this channel
@checks.bot_has_permissions(manage_messages=True)   # the bot, in this channel
@checks.cooldown(1, 30.0)                            # once every 30 seconds per member
async def clean(interaction: bisim.Interaction, count: app_commands.Range[int, 1, 100]) -> None:
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=count)  # type: ignore[union-attr]
    await interaction.edit_original_response(content=f'Deleted {len(deleted)} messages.')
```

| Check | Fails with |
| --- | --- |
| `checks.has_permissions(**perms)` | `app_commands.MissingPermissions` |
| `checks.bot_has_permissions(**perms)` | `app_commands.BotMissingPermissions` |
| `checks.has_role(name_or_id)` | `app_commands.MissingRole` |
| `checks.has_any_role(*names_or_ids)` | `app_commands.MissingAnyRole` |
| `checks.cooldown(rate, per, key=...)` | `app_commands.CommandOnCooldown` |
| `checks.dynamic_cooldown(factory, key=...)` | `app_commands.CommandOnCooldown` |

`has_permissions` reads `interaction.permissions` and `bot_has_permissions` reads
`interaction.app_permissions`: Bisim works out both for the channel the command runs in. The role checks
raise `app_commands.NoPrivateMessage` in a DM. A cooldown's `key` decides who shares it: by default each
member has their own, `key=lambda i: i.guild_id` makes one per server and `key=lambda i: None` one for
everybody.

Your own check is a function that takes the interaction and returns `True` or `False` (or raises an
`app_commands.AppCommandError`); it may be `async`:

```python
def is_staff(interaction: bisim.Interaction) -> bool:
    return any(role.name == 'Staff' for role in getattr(interaction.user, 'roles', []))


@client.tree.command(description='Staff only')
@app_commands.check(is_staff)
async def staff(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Hello, staff member.', ephemeral=True)
```

A check that returns `False` raises `app_commands.CheckFailure`. To check every command of a group, override
the group's `interaction_check()`; for the whole tree, subclass `CommandTree` and override its
`interaction_check()`.

## Handling errors

Errors from checks, transformers and the command itself reach, in order: the command's own handler
(`@command.error`), the parent groups' `on_error`, the cog's `cog_app_command_error`, and finally the tree's
`on_error`. An exception raised in your code arrives wrapped in `app_commands.CommandInvokeError`, with the
original in `.original`.

```python
import logging

log = logging.getLogger(__name__)


@client.tree.error
async def on_app_command_error(interaction: bisim.Interaction, error: app_commands.AppCommandError) -> None:
    if isinstance(error, app_commands.CommandOnCooldown):
        text = f'Slow down: try again in {error.retry_after:.0f} seconds.'
    elif isinstance(error, (app_commands.MissingPermissions, app_commands.MissingRole)):
        text = 'You are not allowed to do that here.'
    elif isinstance(error, app_commands.BotMissingPermissions):
        text = f'I need these permissions: {", ".join(error.missing_permissions)}.'
    else:
        log.exception('Error in a command', exc_info=error)
        text = 'Something went wrong.'
    if interaction.response.is_done():
        await interaction.followup.send(text, ephemeral=True)
    else:
        await interaction.response.send_message(text, ephemeral=True)
```

`@client.tree.error` replaces the tree's default handler, which only logs the error, so log what you do not
handle. Every check and error class is listed in the [API reference](../../reference/app-commands.md).
