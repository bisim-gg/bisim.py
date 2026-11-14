# Event reference { #bisim-api-events }

bisim.py calls a coroutine of yours when something happens on Bisim. Register it with the
[`Client.event`][bisim.Client.event] decorator, by overriding the method on a subclass of
[`Client`][bisim.Client], with [`Bot.listen`][bisim.ext.commands.Bot.listen], or with
[`Cog.listener`][bisim.ext.commands.Cog.listener]:

```python
import bisim

client = bisim.Client(intents=bisim.Intents.default())


@client.event
async def on_message(message: bisim.Message) -> None:
    if message.content == '!ping':
        await message.channel.send('Pong!')


class MyClient(bisim.Client):
    async def on_ready(self) -> None:
        print(f'Logged in as {self.user}')
```

The names and arguments are discord.py's. An event that raises is passed to [`on_error`](#on_error) and
does not stop the bot. Intents change nothing on Bisim: a bot receives every event its permissions let it
see. The events at the end of this page exist in discord.py but never fire on Bisim.

Events named `on_raw_*` fire for every change, with a small payload object. Their counterparts without
`raw` need the message or member in the cache, and give you the full objects.

## Connection

### on_connect() { #on_connect }

Called when the connection to Bisim's gateway is open. The servers are not loaded yet at that point; wait
for [`on_ready`](#on_ready) before using the cache.

### on_disconnect() { #on_disconnect }

Called when the connection to the gateway is lost or closed. The client reconnects by itself, so this can
be called many times.

### on_ready() { #on_ready }

Called once, when the bot is logged in and its servers, channels, roles and members are loaded.

Bisim's gateway has no READY event. After connecting, bisim.py reads the bot's servers over REST and
subscribes to each one, then calls `on_ready`. It is called only once for a client: after a reconnect,
[`on_resumed`](#on_resumed) is called instead.

### on_resumed() { #on_resumed }

Called after a reconnect, once the servers have been loaded again. Bisim has no session resume, so the
library loads everything again and reports the differences as the usual events.

### on_error(event, \*args, \*\*kwargs) { #on_error }

Called when an event handler raises. By default it logs the traceback; the exception is available through
`sys.exc_info()`.

- **event** (`str`): the name of the event that raised, such as `'on_message'`.
- **args**, **kwargs**: the arguments of that event.

### on_socket_event_type(event_type) { #on_socket_event_type }

Called for every event the gateway sends, with its type, such as `'MESSAGE_CREATE'`. Only with
`enable_debug_events=True` on the client.

### on_socket_raw_receive(msg) { #on_socket_raw_receive }

Called with every message received from the gateway, as text, before it is processed. Only with
`enable_debug_events=True` on the client. Use it for debugging, never to read events.

## Servers

### on_guild_available(guild) { #on_guild_available }

Called for each server when it is loaded: at startup, before [`on_ready`](#on_ready), and again after a
reconnect.

- **guild** ([`Guild`][bisim.Guild]): the server.

### on_guild_join(guild) { #on_guild_join }

Called when the bot is added to a server.

- **guild** ([`Guild`][bisim.Guild]): the server.

### on_guild_remove(guild) { #on_guild_remove }

Called when the bot leaves a server, is kicked or banned from it, or the server is deleted.

- **guild** ([`Guild`][bisim.Guild]): the server, as it was in the cache.

### on_guild_update(before, after) { #on_guild_update }

Called when a server changes, for example its name, description, icon or system channel.

- **before**, **after** ([`Guild`][bisim.Guild]): the server before and after the change.

### on_guild_emojis_update(guild, before, after) { #on_guild_emojis_update }

Called when a server adds or removes a custom emoji.

- **guild** ([`Guild`][bisim.Guild]): the server.
- **before**, **after** (sequence of [`Emoji`][bisim.Emoji]): the emoji before and after the change.

### on_guild_stickers_update(guild, before, after) { #on_guild_stickers_update }

Called when a server adds or removes a sticker.

- **guild** ([`Guild`][bisim.Guild]): the server.
- **before**, **after** (sequence of [`GuildSticker`][bisim.GuildSticker]): the stickers before and after.

## Channels

### on_guild_channel_create(channel) { #on_guild_channel_create }

### on_guild_channel_delete(channel) { #on_guild_channel_delete }

Called when a channel is created in a server or deleted from it.

- **channel** ([`abc.GuildChannel`][bisim.abc.GuildChannel]): the channel.

### on_guild_channel_update(before, after) { #on_guild_channel_update }

Called when a channel in a server changes: its name, topic, position, category, slow mode or permissions.

- **before**, **after** ([`abc.GuildChannel`][bisim.abc.GuildChannel]): the channel before and after.

### on_guild_channel_pins_update(channel, last_pin) { #on_guild_channel_pins_update }

Called when a message is pinned or unpinned in a server channel.

- **channel** ([`abc.GuildChannel`][bisim.abc.GuildChannel]): the channel.
- **last_pin** (`Optional[datetime.datetime]`): when a message was pinned, the time of the event in UTC;
  `None` when a message was unpinned.

### on_private_channel_update(before, after) { #on_private_channel_update }

Called when a group DM changes, for example its name.

- **before**, **after** ([`GroupChannel`][bisim.GroupChannel]): the group DM before and after.

### on_private_channel_pins_update(channel, last_pin) { #on_private_channel_pins_update }

Like [`on_guild_channel_pins_update`](#on_guild_channel_pins_update), for a DM or group DM.

### on_typing(channel, user, when) { #on_typing }

Called when someone starts typing in a channel the bot can see.

- **channel** ([`abc.Messageable`][bisim.abc.Messageable]): where they are typing.
- **user** ([`User`][bisim.User] or [`Member`][bisim.Member]): who is typing.
- **when** (`datetime.datetime`): when they started, in UTC.

### on_raw_typing(payload) { #on_raw_typing }

Like [`on_typing`](#on_typing), for every typing event, even when the channel or the user is not cached.

- **payload** ([`RawTypingEvent`][bisim.RawTypingEvent])

## Messages

### on_message(message) { #on_message }

Called when a message is sent in a channel the bot can see, including the bot's own messages. Bisim always
sends the message text; the `message_content` intent is not needed.

- **message** ([`Message`][bisim.Message]): the message.

### on_message_edit(before, after) { #on_message_edit }

Called when a message is edited, if it is in the message cache (see `max_messages` on the client). For
every edit, use [`on_raw_message_edit`](#on_raw_message_edit).

- **before**, **after** ([`Message`][bisim.Message]): the message before and after the edit.

### on_raw_message_edit(payload) { #on_raw_message_edit }

Called for every message edit, cached or not.

- **payload** ([`RawMessageUpdateEvent`][bisim.RawMessageUpdateEvent])

### on_message_delete(message) { #on_message_delete }

Called when a message is deleted, if it is in the message cache. For every deletion, use
[`on_raw_message_delete`](#on_raw_message_delete).

- **message** ([`Message`][bisim.Message]): the deleted message.

### on_raw_message_delete(payload) { #on_raw_message_delete }

- **payload** ([`RawMessageDeleteEvent`][bisim.RawMessageDeleteEvent])

### on_bulk_message_delete(messages) { #on_bulk_message_delete }

Called when several messages are deleted at once, with those that were in the message cache.

- **messages** (list of [`Message`][bisim.Message])

### on_raw_bulk_message_delete(payload) { #on_raw_bulk_message_delete }

- **payload** ([`RawBulkMessageDeleteEvent`][bisim.RawBulkMessageDeleteEvent])

## Reactions and polls

### on_reaction_add(reaction, user) { #on_reaction_add }

### on_reaction_remove(reaction, user) { #on_reaction_remove }

Called when someone adds or removes a reaction on a message in the message cache.

- **reaction** ([`Reaction`][bisim.Reaction]): the reaction, with its current count.
- **user** ([`Member`][bisim.Member] or [`User`][bisim.User]): who reacted.

### on_raw_reaction_add(payload) { #on_raw_reaction_add }

### on_raw_reaction_remove(payload) { #on_raw_reaction_remove }

Called for every reaction added or removed, cached or not.

- **payload** ([`RawReactionActionEvent`][bisim.RawReactionActionEvent])

### on_reaction_clear(message, reactions) { #on_reaction_clear }

Called when all reactions are removed from a message in the message cache.

- **message** ([`Message`][bisim.Message]): the message.
- **reactions** (list of [`Reaction`][bisim.Reaction]): the reactions it had.

### on_raw_reaction_clear(payload) { #on_raw_reaction_clear }

- **payload** ([`RawReactionClearEvent`][bisim.RawReactionClearEvent])

### on_poll_vote_add(user, answer) { #on_poll_vote_add }

### on_poll_vote_remove(user, answer) { #on_poll_vote_remove }

Called when someone votes for an answer of a poll in the message cache, or takes the vote back.

- **user** ([`Member`][bisim.Member] or [`User`][bisim.User]): who voted.
- **answer** ([`PollAnswer`][bisim.PollAnswer]): the answer.

### on_raw_poll_vote_add(payload) { #on_raw_poll_vote_add }

### on_raw_poll_vote_remove(payload) { #on_raw_poll_vote_remove }

- **payload** ([`RawPollVoteActionEvent`][bisim.RawPollVoteActionEvent])

## Roles

### on_guild_role_create(role) { #on_guild_role_create }

### on_guild_role_delete(role) { #on_guild_role_delete }

Called when a role is created or deleted.

- **role** ([`Role`][bisim.Role]): the role.

### on_guild_role_update(before, after) { #on_guild_role_update }

Called when a role changes: its name, colour, permissions, position or settings.

- **before**, **after** ([`Role`][bisim.Role]): the role before and after.

## Members and users

### on_member_join(member) { #on_member_join }

### on_member_remove(member) { #on_member_remove }

Called when someone joins a server, or leaves it, is kicked or is banned.

- **member** ([`Member`][bisim.Member]): the member.

### on_raw_member_remove(payload) { #on_raw_member_remove }

Like [`on_member_remove`](#on_member_remove), even when the member was not cached.

- **payload** ([`RawMemberRemoveEvent`][bisim.RawMemberRemoveEvent])

### on_member_update(before, after) { #on_member_update }

Called when a member's nickname, roles or timeout changes.

- **before**, **after** ([`Member`][bisim.Member]): the member before and after.

### on_user_update(before, after) { #on_user_update }

Called when a user changes their username, display name or avatar.

- **before**, **after** ([`User`][bisim.User]): the user before and after.

### on_presence_update(before, after) { #on_presence_update }

Called when a member's status or activity changes.

- **before**, **after** ([`Member`][bisim.Member]): the member before and after.

### on_raw_presence_update(payload) { #on_raw_presence_update }

Called for every presence change, cached or not. Only with `enable_raw_presences=True` on the client.

- **payload** ([`RawPresenceUpdateEvent`][bisim.RawPresenceUpdateEvent])

### on_voice_state_update(member, before, after) { #on_voice_state_update }

Called when a member joins, leaves or moves between voice channels, or is muted or deafened, the bot
itself included.

- **member** ([`Member`][bisim.Member]): the member.
- **before**, **after** ([`VoiceState`][bisim.VoiceState]): the voice state before and after.

### on_voice_channel_status_update(channel, before, after) { #on_voice_channel_status_update }

Called when the status text of a voice channel changes.

- **channel** ([`VoiceChannel`][bisim.VoiceChannel]): the channel.
- **before**, **after** (`Optional[str]`): the status before and after.

## Interactions

### on_interaction(interaction) { #on_interaction }

Called for every interaction: slash and context menu commands, clicks on buttons and select menus, and
submitted modals. A [`CommandTree`][bisim.app_commands.CommandTree] and your views answer them by
themselves; this event is for logging or for answering them by hand.

- **interaction** ([`Interaction`][bisim.Interaction])

### on_app_command_completion(interaction, command) { #on_app_command_completion }

Called when an application command finished without an error.

- **interaction** ([`Interaction`][bisim.Interaction])
- **command** ([`app_commands.Command`][bisim.app_commands.Command] or
  [`app_commands.ContextMenu`][bisim.app_commands.ContextMenu]): the command that ran.

## bisim.ext.commands { #ext-commands-events }

These are called only for a [`commands.Bot`][bisim.ext.commands.Bot].

### on_command(ctx) { #on_command }

Called when a prefix command is found and about to run.

- **ctx** ([`Context`][bisim.ext.commands.Context])

### on_command_completion(ctx) { #on_command_completion }

Called when a prefix command finished without an error.

- **ctx** ([`Context`][bisim.ext.commands.Context])

### on_command_error(ctx, error) { #on_command_error }

Called when a prefix command raises, a check fails, or an argument cannot be converted. Without a handler,
the error is logged.

- **ctx** ([`Context`][bisim.ext.commands.Context])
- **error** ([`CommandError`][bisim.ext.commands.CommandError])

## bisim.ext.voice_recv { #voice-recv-events }

These are called while a [`VoiceRecvClient`][bisim.ext.voice_recv.VoiceRecvClient] listens. Sinks can listen
to them too (see [`AudioSink.listener`][bisim.ext.voice_recv.AudioSink.listener]); there they run on the
receive thread.

### on_voice_member_speaking_start(member) { #on_voice_member_speaking_start }

Called when someone in the bot's voice channel starts speaking.

- **member** ([`Member`][bisim.Member] or [`User`][bisim.User])

### on_voice_member_speaking_stop(member) { #on_voice_member_speaking_stop }

Called when they stop.

- **member** ([`Member`][bisim.Member] or [`User`][bisim.User])

### on_voice_member_disconnect(member, ssrc) { #on_voice_member_disconnect }

Called when someone leaves the bot's voice channel.

- **member** ([`Member`][bisim.Member] or [`User`][bisim.User])
- **ssrc** (`int`): the number their audio carried in [`FramePacket.ssrc`][bisim.ext.voice_recv.FramePacket].

## Events that never fire on Bisim

These discord.py events can be registered, but Bisim has nothing that would call them: `on_shard_*`,
`on_guild_unavailable`, `on_member_ban`, `on_member_unban`, `on_invite_create`, `on_invite_delete`,
`on_webhooks_update`, `on_guild_integrations_update`, `on_integration_*`, `on_thread_*`,
`on_raw_thread_*`, `on_scheduled_event_*`, `on_stage_instance_*`, `on_automod_*`,
`on_audit_log_entry_create`, `on_reaction_clear_emoji`, `on_raw_reaction_clear_emoji`,
`on_app_command_permissions_update`, `on_entitlement_*` and `on_soundboard_sound_*`.

## Event payloads

::: bisim.RawMessageDeleteEvent
    options:
      heading_level: 3

::: bisim.RawBulkMessageDeleteEvent
    options:
      heading_level: 3

::: bisim.RawMessageUpdateEvent
    options:
      heading_level: 3

::: bisim.RawReactionActionEvent
    options:
      heading_level: 3

::: bisim.RawReactionClearEvent
    options:
      heading_level: 3

::: bisim.RawTypingEvent
    options:
      heading_level: 3

::: bisim.RawMemberRemoveEvent
    options:
      heading_level: 3

::: bisim.RawPollVoteActionEvent
    options:
      heading_level: 3

::: bisim.RawPresenceUpdateEvent
    options:
      heading_level: 3
