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

A Discord token does not work on Bisim. Create the bot in Bisim under Settings, Applications (see
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

Intents are accepted wherever discord.py takes them, and they change nothing. A Bisim bot receives every event
its permissions let it see, and messages always carry their text, so `intents.message_content = True` and
`intents.members = True` are harmless and not needed. `bisim.Intents.default()` and `bisim.Intents.all()`
both work. `PrivilegedIntentsRequired` is never raised.

## Starting up

Bisim's gateway has no IDENTIFY and no READY event. After connecting, bisim.py loads the bot's servers,
channels, roles and members over the REST API and subscribes to each server, then calls `on_ready`. The
cache is full when `on_ready` runs, as you expect.

- `on_ready` is called once. After a reconnect, the library loads everything again and calls `on_resumed`;
  changes it finds on the way arrive as the usual events.
- `on_guild_available` is called for each server as it loads; `on_guild_join` when the bot is added to a
  server later.
- `setup_hook` runs after logging in and before connecting, as in discord.py. It is the place to sync
  commands and register persistent views.

## What Bisim does not have

Bisim has no voice connections for bots, threads, stage, forum or media channels, scheduled events, sharding,
sticker packs, server templates, widgets, SKUs or premium features. Calling something that needs them raises
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
| Voice | `VoiceChannel.connect()`; a bitrate, user limit or region when creating or editing a voice channel; text chat in voice channels |
| Channels | threads, stage, forum and announcement channels, following channels, changing a channel's type |
| Messages | forwarding and publishing messages, changing a message's attachments |
| Interactions | files, attachments and polls in interaction responses and followups |
| Components | `default_values` in select menus, premium buttons (`sku_id`), `Client.add_dynamic_items()` |
| App commands | per command permission overrides (`AppCommand.fetch_permissions()`) |
| Servers | creating, deleting or templating a server as a bot, reading the vanity invite, role icons and gradient colours, editing an emoji or a sticker |
| Bot account | changing the bot's avatar, banner or bio from the library |
| Webhooks | avatars, files, components, threads and polls in webhook messages |
| ext.commands | `Context.from_interaction()`; hybrid commands and `FlagConverter` do not exist yet |

Classes such as `bisim.Thread`, `bisim.StageChannel` and `bisim.ForumChannel` exist so that `isinstance`
checks still run, but no object of those types is ever created. `shard_id` and `shard_count` are ignored with
a warning, and the [event reference](../reference/events.md) lists the events that never fire.

## Things that work a little differently

- **Embeds.** Bisim shows the title, description, link, colour, timestamp, author name and link, footer text
  and up to 25 fields. `set_image()`, `set_thumbnail()` and icon URLs are kept on the `Embed` but not shown.
  See [Embeds](topics/embeds.md).
- **Message length.** Up to 4000 characters, where Discord allows 2000.
- **Files.** `bisim.File` works with `send()`, uploaded through Bisim's upload addresses. Up to 10 files of
  10 MiB each by default.
- **Following up a deferred interaction.** After `interaction.response.defer()`, `followup.send()` posts a
  new message; it does not replace the "thinking" message. Fill that one with
  `interaction.edit_original_response()`. See [Responding to commands](slash-commands/responding.md).
- **Command names.** Slash command names are lower case `a-z`, `0-9`, `-` and `_`, up to 32 characters.
  Show them in Persian with [translations](slash-commands/translations.md).
- **Ids.** Ids are `int`, as in discord.py, but Bisim's snowflakes start from their own epoch:
  `bisim.utils.snowflake_time()` uses `BISIM_EPOCH`.
- **Rate limits.** Bisim's limits are handled for you, as discord.py does for Discord's.

## A checklist

1. Change the imports, and `discord.` to `bisim.` (or `import bisim as discord`).
2. Rename `DiscordException` and `DiscordServerError` if you catch them.
3. Use a Bisim token.
4. Search the code for threads, voice connections, stage or forum channels, scheduled events and sharding,
   and decide what the bot does without them.
5. Run the bot and sync its commands with `tree.sync()` once.
