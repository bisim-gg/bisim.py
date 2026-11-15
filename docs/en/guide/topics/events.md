# Events

bisim.py is event driven: when something happens on Bisim, the library calls the coroutine you registered for
that event. Event names and their arguments are the same as in discord.py, so `on_message(message)` and
`on_member_join(member)` work as you expect. The [event reference](../../reference/events.md) lists every
event with its arguments.

## Registering a handler

The quickest way is the `@client.event` decorator. The function's name is the event's name:

```python
import bisim

intents = bisim.Intents.default()
intents.members = True  # on_member_join needs it (see Intents below)
client = bisim.Client(intents=intents)


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


intents = bisim.Intents.default()
intents.message_content = True  # to read message.content in servers
client = MyClient(intents=intents)
```

With `bisim.ext.commands`, `@bot.listen()` and `@commands.Cog.listener()` add more than one handler for the
same event; see [cogs](../commands/cogs.md).

## Intents

Intents tell Bisim which events the bot wants. They are Discord's, bit for bit, and you pass them to the
client:

```python
intents = bisim.Intents.default()
intents.members = True          # privileged
intents.message_content = True  # privileged

client = bisim.Client(intents=intents)
```

`Intents.default()` turns on everything except the three privileged intents, `Intents.all()` turns on
everything and `Intents.none()` nothing. The library sends them when it connects, and the gateway sends the bot
only the events they cover. Each flag of [`Intents`](../../reference/permissions-and-flags.md) lists its events; the main ones:

| Intent | Events |
| --- | --- |
| `guilds` | servers, channels, roles, pins and voice channel status; leave it on |
| `members` (privileged) | members joining, leaving and changing |
| `moderation` | bans, unbans and new audit log entries |
| `expressions` | custom emoji and stickers |
| `webhooks` | `on_webhooks_update` |
| `invites` | `on_invite_create`, `on_invite_delete` |
| `voice_states` | `on_voice_state_update` (the bot's own voice state always arrives) |
| `presences` (privileged) | `on_presence_update` |
| `guild_messages`, `dm_messages` | messages in servers and in DMs |
| `guild_reactions`, `dm_reactions` | reactions |
| `guild_typing`, `dm_typing` | `on_typing` |
| `message_content` (privileged) | the text of messages (see below) |
| `auto_moderation_configuration` | AutoMod rules made, changed and deleted |
| `auto_moderation_execution` | `on_automod_action` |
| `guild_polls`, `dm_polls` | poll votes |

Interactions (slash commands, buttons, select menus, modals) arrive whatever the intents, and so does
`on_guild_join`.

### The privileged intents

| Intent | What it gives |
| --- | --- |
| `members` | `on_member_join`, `on_member_remove`, `on_member_update`, and the member list: the library loads every member at startup, and `Guild.chunk()` and `Guild.fetch_members()` work |
| `presences` | `on_presence_update` and members' status and activity; without it everyone reads as offline |
| `message_content` | the text, embeds, attachments, components and poll of messages in servers |

To use one, switch it on for the bot first: open [bisim.gg/developers](https://bisim.gg/developers), choose your
application, then **Bot**, and turn it on under **Privileged Gateway Intents**. While the bot is in fewer than
100 servers that is all. From 100 servers on, Bisim must also approve each privileged intent for the
application; one that is switched on but not approved is refused like one that is off.

Without `members`, the library does not load the member list: `guild.members` holds the bot and the members it
has heard about, and `Guild.chunk()` and `Guild.fetch_members()` raise `ClientException`.
`Guild.fetch_member()` and `Guild.query_members()` still work, and `message.author` is still a `Member`, built
from the membership that comes with each message.

### When the gateway refuses the intents

The gateway checks the intents when the bot connects, and closes the connection before anything else:

- **4014**: a privileged intent that is not switched on, or not approved. `client.run()` and `client.start()`
  raise `bisim.PrivilegedIntentsRequired`.
- **4013**: a bit that is not an intent. They raise `bisim.ConnectionClosed` with `code` 4013.

The library does not reconnect after either one, since the same intents would be refused again. Switch the
intent on, or take it out of your `Intents`, and start the bot again.

### Without Message Content

A bot without `message_content` still receives every message event, but a message in a server arrives with
`content` empty (`''`) and without embeds, attachments, components or poll, except:

- the bot's own messages,
- messages that mention the bot,
- direct messages.

Messages read over REST (`history()`, `fetch_message()`, `pins()`) follow the same rule, and so do
`AutoModAction.content` and `matched_content`. Mentions still work: `message.mentions`, `message.role_mentions`,
`message.raw_mentions` and `message.mention_everyone` come from Bisim, not from the text.

Slash commands, buttons and the other interactions are not affected, so a bot built on them needs no
privileged intent. Prefix commands need `message_content`, unless the prefix is a mention of the bot
(`commands.when_mentioned`).

## The events you will use most

| Event | When it is dispatched | Intent |
| --- | --- | --- |
| `on_ready()` | Once, when every server has been loaded (see [your first bot](../your-first-bot.md)) | |
| `on_resumed()` | After a reconnect, once the servers have been loaded again | |
| `on_message(message)` | A message is sent in a channel the bot can see, its own messages included | `guild_messages`, `dm_messages` |
| `on_message_edit(before, after)` | A message in the message cache is edited | `guild_messages`, `dm_messages` |
| `on_message_delete(message)` | A message in the message cache is deleted | `guild_messages`, `dm_messages` |
| `on_reaction_add(reaction, user)` | A reaction is added to a message in the message cache | `guild_reactions`, `dm_reactions` |
| `on_reaction_clear_emoji(reaction)` | Every reaction of one emoji is removed from a message in the message cache | `guild_reactions`, `dm_reactions` |
| `on_member_join(member)` | Someone joins a server | `members` |
| `on_member_remove(member)` | Someone leaves, is kicked or is banned | `members` |
| `on_member_update(before, after)` | A member's nickname, roles or timeout changes | `members` |
| `on_member_ban(guild, user)` | Someone is banned | `moderation` |
| `on_presence_update(before, after)` | A member's status or activity changes | `presences` |
| `on_guild_join(guild)` | The bot is added to a server | |
| `on_guild_remove(guild)` | The bot leaves or is removed from a server | |
| `on_guild_channel_create(channel)` | A channel is created | `guilds` |
| `on_guild_channel_update(before, after)` | A channel's name, topic, position or settings change | `guilds` |
| `on_guild_role_create(role)` | A role is created | `guilds` |
| `on_voice_state_update(member, before, after)` | Someone joins, leaves or moves between voice channels, or is muted | `voice_states` |
| `on_voice_channel_effect(effect)` | Someone plays a soundboard sound in a voice channel | `voice_states` |
| `on_soundboard_sound_create(sound)` | A server adds a soundboard sound (also `_update` and `_delete`) | `expressions` |
| `on_audit_log_entry_create(entry)` | Something is written to the audit log | `moderation` |
| `on_automod_action(execution)` | An AutoMod rule blocks a message, sends an alert or times someone out | `auto_moderation_execution` |
| `on_interaction(interaction)` | Any interaction arrives; `app_commands` and views handle them for you | |

Some of these also depend on the bot's permissions in the server, as on Discord: bans need Ban Members or View
Audit Log, the audit log needs View Audit Log, invites need Manage Channels, AutoMod needs Manage Server, and
channel and webhook events need the channel to be visible to the bot.

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
`on_raw_reaction_add`, `on_raw_reaction_remove`, `on_raw_reaction_clear`, `on_raw_reaction_clear_emoji`,
`on_raw_typing`, `on_raw_member_remove` and, when the client is created with `enable_raw_presences=True`,
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
threads, scheduled events, stage instances, integrations, entitlements and application command
permissions. The [event reference](../../reference/events.md#events-that-never-fire-on-bisim) lists them.
Registering a handler for them is harmless; it is simply never called.
