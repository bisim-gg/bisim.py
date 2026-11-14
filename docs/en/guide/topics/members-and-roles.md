# Members and roles

## Members

When the bot connects, bisim.py loads the members of every server, so `guild.members` and `guild.get_member()`
work from `on_ready` onwards. Pass `chunk_guilds_at_startup=False` to the client to skip that and load members
only when you ask for them.

```python
member = guild.get_member(123456789012345678)  # from the cache, or None
member = await guild.fetch_member(123456789012345678)  # always asks Bisim
found = await guild.query_members('ali', limit=10)  # username or nickname starting with "ali"
me = guild.me  # the bot itself

async for member in guild.fetch_members(limit=None):
    print(member.display_name)
```

A `bisim.Member` is a user in one server. Besides everything a `bisim.User` has (`name`, `display_name`,
`avatar`, `bot`, `mention`), it has `nick`, `joined_at`, `roles`, `top_role`, `guild_permissions`, `status`,
`activity`, `voice` and `timed_out_until`.

## Nicknames

```python
await member.edit(nick='New name', reason='Requested')
await member.edit(nick=None)  # removes the nickname
await guild.me.edit(nick='Helper')  # the bot's own nickname
```

Changing someone else's nickname needs the Manage Nicknames permission.

## Giving and taking roles

```python
role = guild.get_role(234567890123456789)
await member.add_roles(role, reason='Verified')
await member.remove_roles(role)

# Replace the whole set of roles at once
await member.edit(roles=[role_a, role_b])
```

`member.roles` lists the member's roles, starting with the server's default role (`@everyone`).
`bisim.utils.get(guild.roles, name='Moderator')` finds a role by name.

## Moderation

```python
import datetime

await member.timeout(datetime.timedelta(minutes=10), reason='Spamming')
await member.timeout(None)  # removes the timeout

await member.kick(reason='Breaking the rules')
await member.ban(delete_message_seconds=60 * 60 * 24, reason='Spam')
await guild.unban(bisim.Object(id=123456789012345678))

async for entry in guild.bans():
    print(entry.user, entry.reason)
```

`timeout()` takes a `timedelta` (how long) or a timezone aware `datetime` (until when), up to 28 days;
`member.is_timed_out()` tells you whether a timeout is running. `ban()` can delete the member's recent messages, up to seven days
(`delete_message_seconds` from 0 to 604800).

Each action needs its permission: Moderate Members for timeouts, Kick Members, Ban Members. Bisim also follows
Discord's role hierarchy: the bot can act only on members whose highest role is below its own highest role,
and never on the server's owner.

Server mute, deafen and moving (`member.edit(mute=True)`, `member.move_to(channel)`) work on members who are
in a voice channel; for anyone else they raise `bisim.ClientException`. The bot itself joins voice with
`channel.connect()` (see [Voice](voice.md)).

## Roles

```python
role = await guild.create_role(
    name='Helpers',
    permissions=bisim.Permissions(manage_messages=True),
    colour=bisim.Colour.green(),
    hoist=True,
    mentionable=True,
    reason='New team',
)

await role.edit(name='Helper team', colour=0x5197ED)
await role.edit(position=3)  # or guild.edit_role_positions({role: 3})
await role.delete(reason='No longer needed')
```

A `bisim.Role` has `name`, `colour`, `permissions`, `position`, `hoist`, `mentionable`, `members` and
`mention`. `role.is_default()` is `True` for `@everyone`. Managing roles needs the Manage Roles permission, and
the bot can only manage roles below its own highest role.

!!! note "Not on Bisim"

    Role icons (`display_icon`) and gradient colours (`secondary_colour`, `tertiary_colour`) raise
    `bisim.NotSupported`.

## Events

`on_member_join`, `on_member_remove` and `on_member_update` (nickname, roles or timeout) tell you about
members; `on_guild_role_create`, `on_guild_role_update` and `on_guild_role_delete` about roles. Bisim does not
send an event for bans. See [events](events.md).

Member and role checks for commands are on the [permissions](permissions.md) page. Everything about these
classes is in the [API reference](../../reference/users-and-members.md).
