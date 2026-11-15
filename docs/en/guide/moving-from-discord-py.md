# Moving from discord.py

bisim.py has discord.py 2.x's API, so most bots move over with two changes: the imports and the token. This
page lists everything else that is different, so nothing surprises you after the move.

## The imports

```diff
-import discord
-from discord import app_commands, ui
-from discord.ext import commands, tasks
+import bisim
+from bisim import app_commands, ui
+from bisim.ext import commands, tasks
```

Then replace `discord.` with `bisim.` in the code: `discord.Embed` is `bisim.Embed`, `discord.Interaction` is
`bisim.Interaction`, and so on. Some bots import the module under its old name to keep the rest of the code as
it is; that works too:

```python
import bisim as discord
```

## The token

A Discord token does not work on Bisim. Create the bot in Bisim's Developer Portal (Settings, Developer
Portal, or [bisim.gg/developers](https://bisim.gg/developers); see
[Creating your application](creating-an-application.md)) and pass its token to `client.run()` or
`bot.start()` as before. Keep it in an environment variable, never in the code.

## Names with "Discord" in them

Only the word "Discord" changes; every other name is discord.py's.

| discord.py | bisim.py |
| --- | --- |
| `discord.DiscordException` | `bisim.BisimException` |
| `discord.DiscordServerError` | `bisim.BisimServerError` |
| `discord.utils` | `bisim.utils` |
| `discord.utils.DISCORD_EPOCH` | `bisim.utils.BISIM_EPOCH` |
| `discord.gateway.DiscordWebSocket` | `bisim.gateway.BisimWebSocket` |

`except discord.DiscordException` becomes `except bisim.BisimException`, and it still catches every error the
library raises.

## Intents

Intents work as on Discord, with the same bits: the gateway sends only the events they cover, and the three
privileged ones (`members`, `presences`, `message_content`) must be switched on for the bot at
[bisim.gg/developers](https://bisim.gg/developers) (your application, **Bot**, **Privileged Gateway Intents**),
where Discord's Developer Portal had them. From 100 servers on, Bisim must approve them too. A privileged
intent that is not switched on raises `PrivilegedIntentsRequired` (close code 4014), and an invalid one
`ConnectionClosed` with code 4013, as in discord.py. So keep the intents your discord.py bot had, and switch
on the same privileged ones for its Bisim application. The [Intents](topics/events.md#intents) section has the
details.

## Starting up

Bisim's gateway has no IDENTIFY and no READY event. After connecting, bisim.py loads the bot's servers,
channels, roles and (with the `members` intent) members over the REST API and subscribes to each server, then
calls `on_ready`. The
cache is full when `on_ready` runs, as you expect.

- `on_ready` is called once. After a reconnect, the library loads everything again and calls `on_resumed`;
  changes it finds on the way arrive as the usual events.
- `on_guild_available` is called for each server as it loads; `on_guild_join` when the bot is added to a
  server later.
- `setup_hook` runs after logging in and before connecting, as in discord.py. It is the place to sync
  commands and register persistent views.

## What Bisim does not have

Bisim has no threads, stage, forum or media channels, scheduled events, sharding, video from bots, DM calls
for bots, sticker packs, server templates, widgets, SKUs or premium features. Calling something that needs them raises
`bisim.NotSupported`, a subclass of `bisim.ClientException`, with a message naming the feature:

```python
try:
    await channel.create_thread(name='Ideas')
except bisim.NotSupported as error:
    print(error)  # Threads is not supported on Bisim.
```

Nothing fails silently. Some of the calls that raise it:

| Area | Raises `NotSupported` |
| --- | --- |
| Voice | a bitrate, user limit or region when creating or editing a voice channel; text chat in voice channels |
| Channels | threads, stage, forum and announcement channels, following channels, changing a channel's type |
| Messages | forwarding and publishing messages |
| Interactions | a poll in an edited response (send it as a new answer or a followup) |
| Components | premium buttons (`sku_id`), `Client.add_dynamic_items()` |
| App commands | per command permission overrides (`AppCommand.fetch_permissions()`) |
| Servers | creating, deleting or templating a server as a bot, reading the vanity invite, role icons and gradient colours, role-locked emoji (`Emoji.edit(roles=)`), a sticker's description or emoji (`GuildSticker.edit(description=, emoji=)`) |
| AutoMod | harmful link rules and the block member interactions action |
| Bot account | changing the bot's bio (the username is the application's name) |
| Webhooks | components, threads and polls in webhook messages, ephemeral messages from a plain webhook |
| ext.commands | `Context.from_interaction()`; hybrid commands and `FlagConverter` do not exist yet |

Classes such as `bisim.Thread`, `bisim.StageChannel` and `bisim.ForumChannel` exist so that `isinstance`
checks still run, but no object of those types is ever created. `shard_id` and `shard_count` are ignored with
a warning, and the [event reference](../reference/events.md) lists the events that never fire.

## Things that work a little differently

- **Embed pictures.** The image, the thumbnail and the author and footer icons are `http` or `https` links,
  or `attachment://name` for a file sent (or kept) with the same message, as on Discord. An `attachment://`
  picture that names no file of the message is left out, with a warning once. Bisim keeps a file an embed
  shows in `message.attachments` (Discord leaves it out); Bisim's apps hide it. See
  [Embeds](topics/embeds.md).
- **Message length.** Up to 4000 characters, where Discord allows 2000.
- **Files.** `bisim.File` works wherever discord.py takes one: `send()`, interaction answers and followups,
  webhooks, and `attachments=` in edits (an `Attachment` is kept, a `File` is added, a file left out is
  removed). The library uploads each file to Bisim's upload address first, then sends the message. Up to 10
  files of 10 MiB each by default.
- **Following up a deferred interaction.** After `interaction.response.defer()`, the first `followup.send()`
  fills the "thinking" message, as on Discord, and later ones post new messages. A poll cannot fill it: answer
  the thinking message first, then send the poll as a followup. See
  [Responding to commands](slash-commands/responding.md).
- **Mentions.** `allowed_mentions` (and `Client(allowed_mentions=)`) work as on Discord. A mention that is
  not allowed is written into the message as plain words, the person's or the role's name, so it pings
  nobody; a reply pings nobody on Bisim, so `mention_author` only travels with the message.
- **Soundboard sounds.** Bisim does not send a server's sounds when the bot connects, so
  `Guild.soundboard_sounds` holds the ones the library has seen: call `Guild.fetch_soundboard_sounds()` once
  to load them.
- **Command names.** Slash command names are lower case `a-z`, `0-9`, `-` and `_`, up to 32 characters.
  Show them in Persian with [translations](slash-commands/translations.md).
- **Ids.** Ids are `int`, as in discord.py, but Bisim's snowflakes start from their own epoch:
  `bisim.utils.snowflake_time()` uses `BISIM_EPOCH`.
- **Rate limits.** Bisim's limits are handled for you, as discord.py does for Discord's: the same
  `X-RateLimit` headers and buckets, a queue per bucket, and a wait for the reset when a bucket is used up.

## A checklist

1. Change the imports, and `discord.` to `bisim.` (or `import bisim as discord`).
2. Rename `DiscordException` and `DiscordServerError` if you catch them.
3. Use a Bisim token.
4. Search the code for threads, stage or forum channels, scheduled events and sharding, and decide what the
   bot does without them. A voice bot needs `pip install "bisim.py[voice]"` (see [Voice](topics/voice.md)).
5. Run the bot and sync its commands with `tree.sync()` once.
