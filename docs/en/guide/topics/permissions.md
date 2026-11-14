# Permissions

Bisim's permission system is Discord's: the same permissions with the same bit numbers, roles that grant them,
channel overwrites that allow or deny them per role or member, and the same rules for combining them. So
`bisim.Permissions` works exactly like `discord.Permissions`.

## bisim.Permissions

A `Permissions` object is a set of permission flags. Each permission is an attribute you can read and set:

```python
perms = bisim.Permissions(view_channel=True, send_messages=True)
print(perms.value)  # 3072, the bits as one number
print(perms.send_messages)  # True
print(perms.kick_members)  # False

perms.update(embed_links=True, attach_files=True)
perms.manage_messages = True

everything = bisim.Permissions.all()
nothing = bisim.Permissions.none()
from_number = bisim.Permissions(8)  # administrator
```

Presets such as `Permissions.text()`, `Permissions.voice()`, `Permissions.general()` and
`Permissions.membership()` group related permissions. Two sets combine with `|`, `&` and `^`, and compare with
`<=` and `>=` (subset and superset). Iterating a `Permissions` gives `(name, value)` pairs.

Some names you will meet often: `view_channel` (also `read_messages`), `send_messages`, `manage_messages`,
`embed_links`, `attach_files`, `add_reactions`, `read_message_history`, `pin_messages`, `mention_everyone`,
`manage_channels`, `manage_roles`, `manage_nicknames`, `kick_members`, `ban_members`, `moderate_members`,
`mute_members`, `move_members` and `administrator`. The full list is in the
[API reference](../../reference/permissions-and-flags.md).

## What someone may do

`member.guild_permissions` is what a member may do across the server, from their roles alone.
`channel.permissions_for(member)` is what they may do in one channel, with the channel's overwrites applied:

```python
perms = channel.permissions_for(member)
if perms.send_messages:
    await channel.send(f'{member.mention} can write here.')

# What the bot itself may do here
if channel.permissions_for(guild.me).manage_messages:
    await channel.purge(limit=10)
```

For the bot itself, Bisim tells the library its permissions in every channel, so
`channel.permissions_for(guild.me)` is always exact. For other members the library needs the channel's
overwrites, which Bisim's server listing does not carry. Load them first with
`await channel.fetch_overwrites()`; the prefix command check `commands.has_permissions()` does this for
you.

The server's owner and members with `administrator` have every permission. A member in a timeout keeps only
`view_channel` and `read_message_history`.

## Channel overwrites

An overwrite allows or denies permissions for one role or member in one channel, on top of what their roles
give. `bisim.PermissionOverwrite` holds one: each permission is `True` (allow), `False` (deny) or `None`
(inherit).

```python
# Make a channel read only for everyone, writable for one role
await channel.set_permissions(guild.default_role, send_messages=False)
await channel.set_permissions(helpers, send_messages=True, manage_messages=True)

# The same with a PermissionOverwrite object
overwrite = bisim.PermissionOverwrite()
overwrite.view_channel = False
await channel.set_permissions(member, overwrite=overwrite, reason='Muted in this channel')

# Remove an overwrite
await channel.set_permissions(member, overwrite=None)
```

To read them, `await channel.fetch_overwrites()` returns a dictionary from each role or member to its
`PermissionOverwrite`, and `channel.overwrites_for(target)` gives the one for a target afterwards. Changing
overwrites needs the Manage Roles permission in that channel.

A new channel can get its overwrites when it is created:

```python
overwrites = {
    guild.default_role: bisim.PermissionOverwrite(view_channel=False),
    guild.me: bisim.PermissionOverwrite(view_channel=True),
    staff_role: bisim.PermissionOverwrite(view_channel=True),
}
await guild.create_text_channel('staff', overwrites=overwrites)
```

## Permissions in commands

Commands can check permissions before they run:

- Slash commands: `@app_commands.default_permissions()` decides who sees a command, and
  `@app_commands.checks.has_permissions()` and `bot_has_permissions()` check when it runs. See
  [permissions and checks](../slash-commands/permissions.md).
- Prefix commands: `@commands.has_permissions()`, `@commands.bot_has_permissions()` and their `guild_`
  variants. See [checks](../commands/checks.md).

When an action fails for lack of a permission, Bisim answers with an error and the library raises
`bisim.Forbidden`.
