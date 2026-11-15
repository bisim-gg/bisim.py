# Changelog

All notable changes to bisim.py are listed here.

## Unreleased

## 0.3.0 (2026-11-15)

- Intents work as on Discord. The client sends its `intents` when it connects,
  and Bisim sends only the events they cover. `Intents.default()` leaves out
  the three privileged intents (`members`, `presences`, `message_content`);
  switch each one you use on for the bot at bisim.gg/developers (your
  application, Bot, Privileged Gateway Intents). Close code 4014 raises
  `PrivilegedIntentsRequired` and 4013 raises `ConnectionClosed`, and the
  client does not reconnect after either.
- Without `message_content`, a message in a server has an empty `content` and
  no embeds, attachments, components or poll, unless the bot sent it or it
  mentions the bot; DMs come whole. `Message.mentions`, `role_mentions`,
  `raw_mentions` and `mention_everyone` come from Bisim, so they work either
  way, and in a server `message.author` is a `Member` even when the members are
  not cached.
- Without `members`, the member list is not loaded at startup
  (`chunk_guilds_at_startup` now defaults to `intents.members`), and
  `Guild.chunk()` and `Guild.fetch_members()` raise `ClientException`, as in
  discord.py. Without `presences`, startup no longer waits for presence
  snapshots that will not come.
- Without `members`, whoever is in voice or adds a reaction is still a cached
  `Member` with their roles, from the member Bisim now sends with a voice state
  (at startup and live) and a reaction, as Discord does: `voice_recv` hands a
  `Member` again, and `on_raw_reaction_add`'s `member` is set.
- New events: `on_member_ban`, `on_member_unban`, `on_invite_create`,
  `on_invite_delete`, `on_audit_log_entry_create`, `on_webhooks_update`,
  `on_automod_rule_create`, `on_automod_rule_update`, `on_automod_rule_delete`
  and `on_automod_action`, with `AutoModRule`, `AutoModAction`,
  `AutoModRuleAction`, `AutoModTrigger`, `AutoModPresets` and the AutoMod enums.
  `AutoModRule.edit()`, `AutoModRule.delete()` and `AutoModAction.fetch_rule()`
  work too.
- `on_guild_channel_create` and `on_guild_channel_delete` come from Bisim's
  own channel events, once each, instead of a moment later from a reload.
- `on_member_remove` and `on_raw_member_remove` know who left even when the
  member was not cached.
- `commands.Bot` warns at startup when it has a text prefix but no
  `message_content` intent, as discord.py does.
- Needs the Bisim server of 2026-11-15 or later.

- A bot joins voice deafened unless it asks to hear: `connect()` left without
  `self_deaf` joins deafened, as Bisim enforces a bot's deafen on its media
  server (a deafened bot receives no audio and everyone sees the deafen mark).
  `VoiceRecvClient` joins undeafened (`VoiceProtocol.deaf_by_default`), and
  `listen()` on a deafened one turns the deafen off first. discord.py's default
  is `False`.
- `Guild.change_voice_state()` keeps the bot's mute and deafen when they are
  left out (they used to go back to `False`), so following a moderator's move no
  longer undeafens the bot.

- Embeds show their pictures: `set_image()`, `set_thumbnail()` and the `icon_url`
  of `set_author()` and `set_footer()` are sent instead of being kept on the
  `Embed`, and an embed Bisim sends back has its thumbnail and its author and
  footer `icon_url` filled in. A picture is an `http` or `https` link, or
  `attachment://name` for a file sent (or kept) with the same message; an
  `attachment://` that names no file of the message is left out with a warning
  once, since Bisim would refuse the whole message for it. Needs the Bisim server
  of 2026-11-15 or later; an older one ignores the pictures.

- Files everywhere discord.py takes them: `file=` and `files=` in
  `InteractionResponse.send_message()`, `followup.send()` and `Webhook.send()`
  (and `SyncWebhook.send()`), and `attachments=` in
  `edit_original_response()`, `InteractionResponse.edit_message()`,
  `followup.edit_message()`, `Webhook.edit_message()`, `WebhookMessage.edit()`
  and the bot's own `Message.edit()`, with `add_files()` and
  `remove_attachments()`. An edit's `attachments` is the whole list after it:
  an `Attachment` is kept, a `File` is added, a file left out is removed.
  Interaction and webhook files are uploaded with their token, so an
  Interactions URL bot sends files too.
- Polls in interaction answers: `send_message(poll=)` and `followup.send(poll=)`.
  A poll is sent on its own and never ephemeral; a poll in an edit still raises
  `NotSupported`, and a poll cannot be the followup that fills a deferred
  "thinking" message (Bisim refuses it).
- `allowed_mentions` is honoured: per message, merged over
  `Client(allowed_mentions=)`, with `mention_author` as `repliedUser`, on
  `send()`, edits, interaction answers, followups and webhooks. A mention that is
  not allowed is written as plain words by Bisim.
- Message flags: `silent=True` and `suppress_embeds=True` reach Bisim on
  webhooks too, and `Message.edit(suppress=True|False)` (now `MISSING` by
  default, as in discord.py) hides or brings back a message's embeds, as do the
  Bisim additions `suppress_embeds=` on `edit_original_response()`,
  `Webhook.edit_message()` and `followup.edit_message()`.
- Select menus take `default_values` (user, role, mentionable and channel
  selects; `SelectDefaultValue`, objects or `Object`), and read them back.
- `Message.clear_reaction()` and `Reaction.clear()` use Bisim's single call
  for one emoji, and `on_reaction_clear_emoji` and `on_raw_reaction_clear_emoji`
  fire.
- `Guild.bulk_ban()` uses Bisim's bulk ban (up to 200 users, Ban Members and
  Manage Server).
- `Emoji.edit(name=)` and `GuildSticker.edit(name=)` rename them, and
  `on_guild_emojis_update` and `on_guild_stickers_update` fire for a rename.
  `roles`, `description` and `emoji` still raise `NotSupported`.
- Webhooks: `Webhook.fetch_message()`, `edit_message()` and `delete_message()`
  through the token, `WebhookMessage.edit()` and `delete()` on a plain
  webhook's messages, and the webhook's own picture with
  `TextChannel.create_webhook(avatar=)` and `Webhook.edit(avatar=)` (`None`
  removes it). A per message `avatar_url` is still accepted and ignored.
- `ClientUser.edit(avatar=, banner=)` sets or removes the bot's own picture and
  banner, and `VoiceChannel.edit(status=)` sets a voice channel's status line
  while the bot is in it.
- Rate limits follow Bisim's `X-RateLimit` headers as discord.py follows
  Discord's: the library learns each route's bucket, keeps one queue per
  bucket, sends as many requests at once as the bucket has room for, and waits
  `Reset-After` once it is used up. A 429 with `X-RateLimit-Global` pauses every
  request.
- Soundboard events: `on_soundboard_sound_create`, `on_soundboard_sound_update`,
  `on_soundboard_sound_delete` and `on_voice_channel_effect` (with
  `VoiceChannelEffect`), and `Guild.soundboard_sounds`,
  `Guild.get_soundboard_sound()` and `Client.get_soundboard_sound()` hold the
  sounds the library has seen.
- `Guild.fetch_automod_rules()`, `fetch_automod_rule()` and
  `create_automod_rule()`.
- The guide says the bot is created in the Developer Portal
  (bisim.gg/developers), and that the first followup after `defer()` fills the
  "thinking" message.

## 0.2.0 (2026-11-14)

Voice: a bot joins voice channels, plays sound and hears what is said, with
discord.py's API.

- `pip install "bisim.py[voice]"` adds LiveKit's Python SDK, which carries the
  sound. There is no PyNaCl, libopus or DAVE to install; `bisim.opus.load_opus()`
  and `is_loaded()` keep working.
- `VoiceChannel.connect()` returns a `VoiceClient` with `play`, `pause`, `resume`,
  `stop`, `is_playing`, `is_paused`, `source`, `move_to`, `disconnect`, `latency`
  and `average_latency`; `Guild.voice_client`, `Client.voice_clients`,
  `Guild.change_voice_state` and `VoiceProtocol` for classes of your own.
- The audio sources: `AudioSource`, `PCMAudio`, `FFmpegAudio`, `FFmpegPCMAudio`,
  `FFmpegOpusAudio` (decodes to PCM on Bisim) and `PCMVolumeTransformer`, with
  `after` and `FFmpegProcessError`.
- The voice client follows the server: a moderator's move, a Disconnect (which
  calls `after`), a server mute and its unmute, and a lost connection, which
  joins again while `reconnect` is on.
- `bisim.ext.voice_recv`, with the API of `discord-ext-voice-recv`:
  `VoiceRecvClient`, `listen`, `stop_listening`, `AudioSink`, `BasicSink`,
  `WaveSink`, `UserFilter`, `VoiceData` and the speaking events.
- `VoiceChannel.send_sound`, `SoundboardSound` and `Guild.fetch_soundboard_sounds`.
- A Voice page in the guide, in English and Persian.

A bot sends sound only, sits in one voice channel per server and does not join
DM calls, as on Discord.

## 0.1.0 (2026-11-14)

The first version: the discord.py 2.x API on Bisim's REST API and gateway.

- `Client` with `run`, `start`, `login`, `connect`, `close`, events, `wait_for`,
  `change_presence` and the caches (`guilds`, `users`, `get_*`, `fetch_*`).
- The gateway: passes, heartbeats and `latency`, reconnecting with backoff, and
  loading the servers over REST before `on_ready` (Bisim has no READY event).
- Every Bisim event as its discord.py event: messages, edits, deletions,
  reactions, members, roles, channels, presences, typing, voice states and more.
- Models with discord.py's names: `Guild`, `Member`, `User`, `Role`, `TextChannel`,
  `VoiceChannel`, `CategoryChannel`, `DMChannel`, `Message`, `Embed`, `File`,
  `Emoji`, `Invite`, `Webhook`, `Permissions`, `Colour` and the enums.
- File uploads through Bisim's presigned upload addresses.
- The REST client with per-route rate limits, the global limit and retries.
- Interactions and `app_commands`: slash commands, groups, context menus,
  autocomplete, choices, transformers, checks, and syncing to Bisim.
- `ui`: views with buttons and select menus, persistent views, and modals.
- `bisim.ext.commands` and `bisim.ext.tasks`.
- `bisim.http_interactions` for bots that receive interactions on an Interactions URL.
- The documentation site: the guide in English and Persian and the API reference,
  on GitHub Pages and docs.bisim.gg/py.
