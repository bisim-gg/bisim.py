# Changelog

All notable changes to bisim.py are listed here.

## Unreleased

- Embeds show their pictures: `set_image()`, `set_thumbnail()` and the `icon_url`
  of `set_author()` and `set_footer()` are sent instead of being kept on the
  `Embed`, and an embed Bisim sends back has its thumbnail and its author and
  footer `icon_url` filled in. A picture must be an `http` or `https` link;
  discord.py's `attachment://` is left out with a warning once, since Bisim would
  refuse the whole message for it. Needs the Bisim server of 2026-11-15 or later;
  an older one ignores the pictures.

## 0.2.0 (unreleased)

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
