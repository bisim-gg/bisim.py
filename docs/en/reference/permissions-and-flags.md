# Permissions, intents and flags

Permissions use Discord's bit numbers, so a permission value from a discord.py bot means the same thing on Bisim. The [Permissions guide](../guide/topics/permissions.md) shows how to read and set them.

::: bisim.Permissions

::: bisim.PermissionOverwrite

## Intents

Intents say which gateway events a bot receives, with Discord's bits. The privileged ones (`members`, `presences`, `message_content`) must also be switched on for the bot at [bisim.gg/developers](https://bisim.gg/developers); see the guide's [Intents](../guide/topics/events.md#intents) section.

::: bisim.Intents
    options:
      heading_level: 3

::: bisim.MemberCacheFlags
    options:
      heading_level: 3

## Flags

::: bisim.MessageFlags
    options:
      heading_level: 3

::: bisim.PublicUserFlags
    options:
      heading_level: 3

::: bisim.SystemChannelFlags
    options:
      heading_level: 3

::: bisim.ChannelFlags
    options:
      heading_level: 3

::: bisim.ApplicationFlags
    options:
      heading_level: 3

::: bisim.MemberFlags
    options:
      heading_level: 3

::: bisim.RoleFlags
    options:
      heading_level: 3

::: bisim.AttachmentFlags
    options:
      heading_level: 3

::: bisim.EmbedFlags
    options:
      heading_level: 3

::: bisim.AppCommandContext
    options:
      heading_level: 3

::: bisim.AppInstallationType
    options:
      heading_level: 3

::: bisim.AutoModPresets
    options:
      heading_level: 3
