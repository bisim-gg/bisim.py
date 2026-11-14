# FAQ

## Does my discord.py bot run on Bisim?

Usually, yes, once you change the imports and use a Bisim token. Features Bisim does not have, such as voice
connections, threads and scheduled events, raise `bisim.NotSupported`. [Moving from
discord.py](moving-from-discord-py.md) lists every difference.

## Do I need to enable intents?

No. Intents are accepted and change nothing: a bot receives every event its permissions let it see, and
messages always carry their text. Keep `intents=bisim.Intents.default()` so the code stays the same as on
discord.py.

## My slash commands do not show up

- Commands are only sent to Bisim when you call `await tree.sync()`. Sync once after changing them, for
  example in `setup_hook` or from an owner-only command, not on every start.
- `tree.sync(guild=...)` updates one server at once. Global commands can take a moment to appear.
- A command added to the tree after the sync is not on Bisim until the next sync.

See [Registering and syncing](slash-commands/syncing.md).

## Why does my command say the application did not respond?

Every interaction must be answered within three seconds. If the work takes longer, call
`await interaction.response.defer()` first, then finish with `interaction.edit_original_response()` within
15 minutes. See [Responding to commands](slash-commands/responding.md).

## Why does my bot not see a channel or a message?

A bot sees what its roles let it see. Check that it has the View Channel and Read Message History
permissions in that channel, including the channel's permission overwrites. See
[Permissions](topics/permissions.md).

## Can my bot join a voice channel?

No. Bots cannot connect to voice on Bisim, and `VoiceChannel.connect()` raises `bisim.NotSupported`. A bot
can still see who is in voice channels (`on_voice_state_update`, `VoiceChannel.members`) and, with the
permissions, mute, deafen, move or disconnect members.

## Why is my embed's image missing?

Bisim does not show images, thumbnails or icons in embeds a bot sends. The title, description, link, colour,
timestamp, author, footer text and fields are shown. Send an image as a file with `bisim.File` instead. See
[Embeds](topics/embeds.md).

## How do I keep my token safe?

Read it from an environment variable, never put it in the code or a repository, and reset it in Bisim
(Settings, Applications) if it may have leaked. Anyone with the token controls the bot.

## How do I see what the library is doing?

`client.run()` sets up logging for you. Pass `log_level=logging.DEBUG` to see every request and gateway step,
or configure the `bisim` logger yourself and use `client.start()`.

## Where do I report a bug?

Open an issue on [GitHub](https://github.com/bisim-gg/bisim.py/issues) with the smallest code that shows it.
Report security problems privately to security@bisim.gg instead.
