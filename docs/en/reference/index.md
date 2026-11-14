# API reference

Every public class, function and decorator of bisim.py, generated from the docstrings in the code. The
names, arguments and behaviour follow discord.py 2.x; where Bisim differs, the entry says so. Calling
something Bisim does not have raises [`bisim.NotSupported`][bisim.NotSupported].

New to the library? Start with the [guide](../guide/index.md). Moving a discord.py bot? Read
[Moving from discord.py](../guide/moving-from-discord-py.md).

## The client

- [Client](client.md): logging in, the connection, the cache, presence and fetching things.
- [Event reference](events.md): every event, its arguments and when it is called.

## Models

- [Servers](guilds.md) {: #bisim-api-models }: `Guild`, bans, invites and the audit log.
- [Channels](channels.md): text, voice and category channels, DMs and group DMs.
- [Users, members and roles](users-and-members.md): `User`, `Member`, `Role`, voice states and activities.
- [Messages](messages.md): `Message`, attachments, reactions, polls, `File` and `AllowedMentions`.
- [Embeds](embeds.md): `Embed` and `Colour`.
- [Emoji and stickers](emoji-and-stickers.md).
- [Permissions, intents and flags](permissions-and-flags.md).
- [Webhooks](webhooks.md): posting with a webhook, with or without asyncio.
- [Abstract base classes](abc.md): `abc.Messageable`, `abc.GuildChannel`, `Object` and `Asset`.
- [Voice](voice.md): `VoiceClient`, the audio sources and soundboard sounds.

## Interactions

- [Interactions](interactions.md): `Interaction`, responding and followups.
- [Application commands](app-commands.md): `bisim.app_commands`, slash commands and context menus.
- [Views and components](ui.md): `bisim.ui`, buttons, select menus and modals.
- [Interactions URL](http-interactions.md): receiving interactions over HTTP.

## Extensions

- [bisim.ext.commands](ext-commands.md): prefix commands, converters, checks, cooldowns, cogs and help.
- [bisim.ext.tasks](ext-tasks.md): background tasks.
- [bisim.ext.voice_recv](ext-voice-recv.md): receiving voice.

## More

- [Enumerations](enums.md)
- [Utilities](utils.md): `bisim.utils`.
- [Exceptions](errors.md)

!!! note "Where the docstrings come from"

    Much of bisim.py, its docstrings included, comes from [discord.py](https://github.com/Rapptz/discord.py)
    by Rapptz and its contributors (MIT), adapted to Bisim. Thank you to everyone who made discord.py.
