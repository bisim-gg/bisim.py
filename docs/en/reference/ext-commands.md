# bisim.ext.commands

Prefix commands, written the discord.ext.commands way. The [prefix commands guide](../guide/commands/index.md) explains them step by step; the events this extension adds are in the [event reference](events.md#ext-commands-events).

## Bot

::: bisim.ext.commands.Bot
    options:
      heading_level: 3
      inherited_members: true

::: bisim.ext.commands.when_mentioned
    options:
      heading_level: 3

::: bisim.ext.commands.when_mentioned_or
    options:
      heading_level: 3

## Context

::: bisim.ext.commands.Context
    options:
      heading_level: 3
      inherited_members: true

## Commands

::: bisim.ext.commands.command
    options:
      heading_level: 3

::: bisim.ext.commands.group
    options:
      heading_level: 3

::: bisim.ext.commands.Command
    options:
      heading_level: 3

::: bisim.ext.commands.Group
    options:
      heading_level: 3

::: bisim.ext.commands.GroupMixin
    options:
      heading_level: 3

## Cogs

::: bisim.ext.commands.Cog
    options:
      heading_level: 3

::: bisim.ext.commands.GroupCog
    options:
      heading_level: 3

::: bisim.ext.commands.CogMeta
    options:
      heading_level: 3

## Help commands

::: bisim.ext.commands.HelpCommand
    options:
      heading_level: 3

::: bisim.ext.commands.DefaultHelpCommand
    options:
      heading_level: 3

::: bisim.ext.commands.MinimalHelpCommand
    options:
      heading_level: 3

::: bisim.ext.commands.Paginator
    options:
      heading_level: 3

## Checks

::: bisim.ext.commands.check
    options:
      heading_level: 3

::: bisim.ext.commands.check_any
    options:
      heading_level: 3

::: bisim.ext.commands.has_role
    options:
      heading_level: 3

::: bisim.ext.commands.has_permissions
    options:
      heading_level: 3

::: bisim.ext.commands.has_guild_permissions
    options:
      heading_level: 3

::: bisim.ext.commands.has_any_role
    options:
      heading_level: 3

::: bisim.ext.commands.bot_has_role
    options:
      heading_level: 3

::: bisim.ext.commands.bot_has_permissions
    options:
      heading_level: 3

::: bisim.ext.commands.bot_has_guild_permissions
    options:
      heading_level: 3

::: bisim.ext.commands.bot_has_any_role
    options:
      heading_level: 3

::: bisim.ext.commands.guild_only
    options:
      heading_level: 3

::: bisim.ext.commands.dm_only
    options:
      heading_level: 3

::: bisim.ext.commands.is_owner
    options:
      heading_level: 3

::: bisim.ext.commands.is_nsfw
    options:
      heading_level: 3

::: bisim.ext.commands.before_invoke
    options:
      heading_level: 3

::: bisim.ext.commands.after_invoke
    options:
      heading_level: 3

## Cooldowns

::: bisim.ext.commands.cooldown
    options:
      heading_level: 3

::: bisim.ext.commands.dynamic_cooldown
    options:
      heading_level: 3

::: bisim.ext.commands.max_concurrency
    options:
      heading_level: 3

::: bisim.ext.commands.BucketType
    options:
      heading_level: 3

::: bisim.ext.commands.Cooldown
    options:
      heading_level: 3

::: bisim.ext.commands.CooldownMapping
    options:
      heading_level: 3

::: bisim.ext.commands.DynamicCooldownMapping
    options:
      heading_level: 3

::: bisim.ext.commands.MaxConcurrency
    options:
      heading_level: 3

## Converters

::: bisim.ext.commands.Converter
    options:
      heading_level: 3

::: bisim.ext.commands.ObjectConverter
    options:
      heading_level: 3

::: bisim.ext.commands.MemberConverter
    options:
      heading_level: 3

::: bisim.ext.commands.UserConverter
    options:
      heading_level: 3

::: bisim.ext.commands.MessageConverter
    options:
      heading_level: 3

::: bisim.ext.commands.PartialMessageConverter
    options:
      heading_level: 3

::: bisim.ext.commands.GuildChannelConverter
    options:
      heading_level: 3

::: bisim.ext.commands.TextChannelConverter
    options:
      heading_level: 3

::: bisim.ext.commands.VoiceChannelConverter
    options:
      heading_level: 3

::: bisim.ext.commands.CategoryChannelConverter
    options:
      heading_level: 3

::: bisim.ext.commands.InviteConverter
    options:
      heading_level: 3

::: bisim.ext.commands.GuildConverter
    options:
      heading_level: 3

::: bisim.ext.commands.RoleConverter
    options:
      heading_level: 3

::: bisim.ext.commands.GameConverter
    options:
      heading_level: 3

::: bisim.ext.commands.ColourConverter
    options:
      heading_level: 3

::: bisim.ext.commands.EmojiConverter
    options:
      heading_level: 3

::: bisim.ext.commands.PartialEmojiConverter
    options:
      heading_level: 3

::: bisim.ext.commands.GuildStickerConverter
    options:
      heading_level: 3

::: bisim.ext.commands.clean_content
    options:
      heading_level: 3

::: bisim.ext.commands.Greedy
    options:
      heading_level: 3

::: bisim.ext.commands.Range
    options:
      heading_level: 3

::: bisim.ext.commands.run_converters
    options:
      heading_level: 3

## Parameters

::: bisim.ext.commands.Parameter
    options:
      heading_level: 3

::: bisim.ext.commands.parameter
    options:
      heading_level: 3

::: bisim.ext.commands.param
    options:
      heading_level: 3

::: bisim.ext.commands.Author
    options:
      heading_level: 3

::: bisim.ext.commands.CurrentChannel
    options:
      heading_level: 3

::: bisim.ext.commands.CurrentGuild
    options:
      heading_level: 3

## Errors

Every error below derives from [`CommandError`][bisim.ext.commands.CommandError] and reaches `on_command_error`.

::: bisim.ext.commands.CommandError
    options:
      heading_level: 3

::: bisim.ext.commands.ConversionError
    options:
      heading_level: 3

::: bisim.ext.commands.UserInputError
    options:
      heading_level: 3

::: bisim.ext.commands.MissingRequiredArgument
    options:
      heading_level: 3

::: bisim.ext.commands.MissingRequiredAttachment
    options:
      heading_level: 3

::: bisim.ext.commands.TooManyArguments
    options:
      heading_level: 3

::: bisim.ext.commands.BadArgument
    options:
      heading_level: 3

::: bisim.ext.commands.MessageNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.MemberNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.GuildNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.UserNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.ChannelNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.ChannelNotReadable
    options:
      heading_level: 3

::: bisim.ext.commands.BadColourArgument
    options:
      heading_level: 3

::: bisim.ext.commands.RoleNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.BadInviteArgument
    options:
      heading_level: 3

::: bisim.ext.commands.EmojiNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.PartialEmojiConversionFailure
    options:
      heading_level: 3

::: bisim.ext.commands.GuildStickerNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.BadBoolArgument
    options:
      heading_level: 3

::: bisim.ext.commands.RangeError
    options:
      heading_level: 3

::: bisim.ext.commands.BadUnionArgument
    options:
      heading_level: 3

::: bisim.ext.commands.BadLiteralArgument
    options:
      heading_level: 3

::: bisim.ext.commands.ArgumentParsingError
    options:
      heading_level: 3

::: bisim.ext.commands.UnexpectedQuoteError
    options:
      heading_level: 3

::: bisim.ext.commands.InvalidEndOfQuotedStringError
    options:
      heading_level: 3

::: bisim.ext.commands.ExpectedClosingQuoteError
    options:
      heading_level: 3

::: bisim.ext.commands.CommandNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.CheckFailure
    options:
      heading_level: 3

::: bisim.ext.commands.CheckAnyFailure
    options:
      heading_level: 3

::: bisim.ext.commands.PrivateMessageOnly
    options:
      heading_level: 3

::: bisim.ext.commands.NoPrivateMessage
    options:
      heading_level: 3

::: bisim.ext.commands.NotOwner
    options:
      heading_level: 3

::: bisim.ext.commands.MissingPermissions
    options:
      heading_level: 3

::: bisim.ext.commands.BotMissingPermissions
    options:
      heading_level: 3

::: bisim.ext.commands.MissingRole
    options:
      heading_level: 3

::: bisim.ext.commands.BotMissingRole
    options:
      heading_level: 3

::: bisim.ext.commands.MissingAnyRole
    options:
      heading_level: 3

::: bisim.ext.commands.BotMissingAnyRole
    options:
      heading_level: 3

::: bisim.ext.commands.NSFWChannelRequired
    options:
      heading_level: 3

::: bisim.ext.commands.DisabledCommand
    options:
      heading_level: 3

::: bisim.ext.commands.CommandInvokeError
    options:
      heading_level: 3

::: bisim.ext.commands.CommandOnCooldown
    options:
      heading_level: 3

::: bisim.ext.commands.MaxConcurrencyReached
    options:
      heading_level: 3

::: bisim.ext.commands.ExtensionError
    options:
      heading_level: 3

::: bisim.ext.commands.ExtensionAlreadyLoaded
    options:
      heading_level: 3

::: bisim.ext.commands.ExtensionNotLoaded
    options:
      heading_level: 3

::: bisim.ext.commands.NoEntryPointError
    options:
      heading_level: 3

::: bisim.ext.commands.ExtensionFailed
    options:
      heading_level: 3

::: bisim.ext.commands.ExtensionNotFound
    options:
      heading_level: 3

::: bisim.ext.commands.CommandRegistrationError
    options:
      heading_level: 3
