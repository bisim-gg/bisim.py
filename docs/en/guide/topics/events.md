# Events

bisim.py is event driven: when something happens on Bisim, the library calls the coroutine you registered for
that event. Event names and their arguments are the same as in discord.py, so `on_message(message)` and
`on_member_join(member)` work as you expect. The [event reference](../../reference/events.md) lists every
event with its arguments.

## Registering a handler

The quickest way is the `@client.event` decorator. The function's name is the event's name:

```python
import bisim

client = bisim.Client(intents=bisim.Intents.default())


@client.event
async def on_member_join(member: bisim.Member):
    channel = member.guild.system_channel
    if channel is not None:
        await channel.send(f'Welcome, {member.mention}!')
```

For a larger bot, subclass `bisim.Client` and write the handlers as methods:

```python
import bisim


class MyClient(bisim.Client):
    async def setup_hook(self) -> None:
        # Runs once, after logging in and before connecting to the gateway
        print('Setting up')

    async def on_ready(self) -> None:
        print(f'Ready as {self.user}')

    async def on_message(self, message: bisim.Message) -> None:
        if message.author.bot:
            return
        if message.content == '!hello':
            await message.channel.send(f'Hello, {message.author.display_name}!')


client = MyClient(intents=bisim.Intents.default())
```

With `bisim.ext.commands`, `@bot.listen()` and `@commands.Cog.listener()` add more than one handler for the
same event; see [cogs](../commands/cogs.md).

## The events you will use most

| Event | When it is dispatched |
| --- | --- |
| `on_ready()` | Once, when every server has been loaded (see [your first bot](../your-first-bot.md)) |
| `on_resumed()` | After a reconnect, once the servers have been loaded again |
| `on_message(message)` | A message is sent in a channel the bot can see, its own messages included |
| `on_message_edit(before, after)` | A message in the message cache is edited |
| `on_message_delete(message)` | A message in the message cache is deleted |
| `on_reaction_add(reaction, user)` | A reaction is added to a message in the message cache |
| `on_member_join(member)` | Someone joins a server |
| `on_member_remove(member)` | Someone leaves or is removed from a server |
| `on_member_update(before, after)` | A member's nickname, roles or timeout changes |
| `on_presence_update(before, after)` | A member's status or activity changes |
| `on_guild_join(guild)` | The bot is added to a server |
| `on_guild_remove(guild)` | The bot leaves or is removed from a server |
| `on_guild_channel_update(before, after)` | A channel's name, topic, position or settings change |
| `on_guild_role_create(role)` | A role is created |
| `on_voice_state_update(member, before, after)` | Someone joins, leaves or moves between voice channels, or is muted |
| `on_interaction(interaction)` | Any interaction arrives; `app_commands` and views handle them for you |

Bisim sends no separate event when a channel is created or deleted. The server tells the bot to reload it, and
the library then dispatches `on_guild_channel_create` and `on_guild_channel_delete` from what changed, a moment
after the change.

## Raw events

`on_message_edit`, `on_message_delete` and the reaction events only fire for messages the bot has in its
message cache: the last 1000 messages it saw, or `max_messages` if you pass it to the client. For older
messages use the raw events, which always fire and carry ids instead of objects:

```python
@client.event
async def on_raw_reaction_add(payload: bisim.RawReactionActionEvent):
    # payload.message_id, payload.channel_id, payload.guild_id, payload.user_id and payload.emoji
    if str(payload.emoji) == '⭐':
        channel = client.get_channel(payload.channel_id)
        if channel is not None:
            message = await channel.fetch_message(payload.message_id)
            print(f'Starred: {message.jump_url}')
```

The raw events are `on_raw_message_edit`, `on_raw_message_delete`, `on_raw_bulk_message_delete`,
`on_raw_reaction_add`, `on_raw_reaction_remove`, `on_raw_reaction_clear`, `on_raw_typing`,
`on_raw_member_remove` and, when the client is created with `enable_raw_presences=True`,
`on_raw_presence_update`.

## Waiting for an event

`wait_for` pauses a handler until an event happens. It takes the event name without `on_`, an optional
`check` that receives the event's arguments, and an optional `timeout` in seconds:

```python
import asyncio


@client.event
async def on_message(message: bisim.Message):
    if message.content != '!guess':
        return
    await message.channel.send('Guess a number between 1 and 10.')

    def check(m: bisim.Message) -> bool:
        return m.author == message.author and m.channel == message.channel and m.content.isdigit()

    try:
        guess = await client.wait_for('message', check=check, timeout=15.0)
    except asyncio.TimeoutError:
        return await message.channel.send('Too slow!')

    if int(guess.content) == 7:
        await message.channel.send('Right!')
    else:
        await message.channel.send('No, it was 7.')
```

For an event with several arguments, such as `reaction_add`, `check` receives all of them and `wait_for`
returns them as a tuple.

## Errors in handlers

An exception in an event handler does not stop the bot. The library calls `on_error` with the event's name,
and the default logs the traceback. Override it to report errors your own way:

```python
import traceback


class MyClient(bisim.Client):
    async def on_error(self, event_method: str, /, *args, **kwargs) -> None:
        print(f'Error in {event_method}')
        traceback.print_exc()
```

Errors in slash commands and prefix commands have their own handlers, described in
[permissions and checks](../slash-commands/permissions.md) and [prefix commands](../commands/index.md).

## Events Bisim does not send

Some discord.py events never fire on Bisim, because Bisim has no such feature or does not tell bots about it:
threads, scheduled events, stage instances, integrations, invites (`on_invite_create`, `on_invite_delete`) and
bans (`on_member_ban`, `on_member_unban`). Registering a handler for them is harmless; it is simply never
called.
