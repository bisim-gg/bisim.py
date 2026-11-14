# Application commands

`bisim.app_commands` holds slash commands, context menu commands, their groups, options and checks, and the [`CommandTree`][bisim.app_commands.CommandTree] that syncs them to Bisim and runs them. The [slash commands guide](../guide/slash-commands/index.md) explains them step by step.

::: bisim.app_commands.CommandTree

## Commands

::: bisim.app_commands.Command
    options:
      heading_level: 3

::: bisim.app_commands.Group
    options:
      heading_level: 3

::: bisim.app_commands.ContextMenu
    options:
      heading_level: 3

::: bisim.app_commands.Parameter
    options:
      heading_level: 3

## Decorators

::: bisim.app_commands.command
    options:
      heading_level: 3

::: bisim.app_commands.context_menu
    options:
      heading_level: 3

::: bisim.app_commands.describe
    options:
      heading_level: 3

::: bisim.app_commands.rename
    options:
      heading_level: 3

::: bisim.app_commands.choices
    options:
      heading_level: 3

::: bisim.app_commands.autocomplete
    options:
      heading_level: 3

::: bisim.app_commands.guilds
    options:
      heading_level: 3

::: bisim.app_commands.guild_only
    options:
      heading_level: 3

::: bisim.app_commands.dm_only
    options:
      heading_level: 3

::: bisim.app_commands.private_channel_only
    options:
      heading_level: 3

::: bisim.app_commands.allowed_contexts
    options:
      heading_level: 3

::: bisim.app_commands.guild_install
    options:
      heading_level: 3

::: bisim.app_commands.user_install
    options:
      heading_level: 3

::: bisim.app_commands.allowed_installs
    options:
      heading_level: 3

::: bisim.app_commands.default_permissions
    options:
      heading_level: 3

## Checks

::: bisim.app_commands.check
    options:
      heading_level: 3

::: bisim.app_commands.checks.has_role
    options:
      heading_level: 3

::: bisim.app_commands.checks.has_any_role
    options:
      heading_level: 3

::: bisim.app_commands.checks.has_permissions
    options:
      heading_level: 3

::: bisim.app_commands.checks.bot_has_permissions
    options:
      heading_level: 3

::: bisim.app_commands.checks.cooldown
    options:
      heading_level: 3

::: bisim.app_commands.checks.dynamic_cooldown
    options:
      heading_level: 3

::: bisim.app_commands.Cooldown
    options:
      heading_level: 3

## Options and choices

::: bisim.app_commands.Choice
    options:
      heading_level: 3

::: bisim.app_commands.Range
    options:
      heading_level: 3

::: bisim.app_commands.Transform
    options:
      heading_level: 3

::: bisim.app_commands.Transformer
    options:
      heading_level: 3

::: bisim.app_commands.Namespace
    options:
      heading_level: 3

## Translations

::: bisim.app_commands.Translator
    options:
      heading_level: 3

::: bisim.app_commands.locale_str
    options:
      heading_level: 3

::: bisim.app_commands.TranslationContext
    options:
      heading_level: 3

::: bisim.app_commands.TranslationContextLocation
    options:
      heading_level: 3

## Commands as Bisim stores them

::: bisim.app_commands.AppCommand
    options:
      heading_level: 3

::: bisim.app_commands.AppCommandGroup
    options:
      heading_level: 3

::: bisim.app_commands.Argument
    options:
      heading_level: 3

::: bisim.app_commands.AppCommandChannel
    options:
      heading_level: 3

## Errors

::: bisim.app_commands.AppCommandError
    options:
      heading_level: 3

::: bisim.app_commands.CommandInvokeError
    options:
      heading_level: 3

::: bisim.app_commands.TransformerError
    options:
      heading_level: 3

::: bisim.app_commands.TranslationError
    options:
      heading_level: 3

::: bisim.app_commands.CheckFailure
    options:
      heading_level: 3

::: bisim.app_commands.NoPrivateMessage
    options:
      heading_level: 3

::: bisim.app_commands.MissingRole
    options:
      heading_level: 3

::: bisim.app_commands.MissingAnyRole
    options:
      heading_level: 3

::: bisim.app_commands.MissingPermissions
    options:
      heading_level: 3

::: bisim.app_commands.BotMissingPermissions
    options:
      heading_level: 3

::: bisim.app_commands.CommandOnCooldown
    options:
      heading_level: 3

::: bisim.app_commands.CommandAlreadyRegistered
    options:
      heading_level: 3

::: bisim.app_commands.CommandSignatureMismatch
    options:
      heading_level: 3

::: bisim.app_commands.CommandNotFound
    options:
      heading_level: 3

::: bisim.app_commands.CommandLimitReached
    options:
      heading_level: 3

::: bisim.app_commands.MissingApplicationID
    options:
      heading_level: 3

::: bisim.app_commands.CommandSyncFailure
    options:
      heading_level: 3
