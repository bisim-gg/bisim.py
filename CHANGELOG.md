# Changelog

All notable changes to bisim.py are listed here.

## 0.1.0 (unreleased)

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
