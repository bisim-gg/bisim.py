# Context menus

Context menu commands appear when a member opens the menu of a message or of a user and goes to **Apps**.
They take no options: the message or the user they were opened on is the input.

## Message commands and user commands

The type of the second parameter decides which menu the command appears in:

```python
@client.tree.context_menu(name='Quote message')
async def quote(interaction: bisim.Interaction, message: bisim.Message) -> None:
    embed = bisim.Embed(description=message.content or '(no text)', timestamp=message.created_at)
    embed.set_author(name=message.author.display_name)
    await interaction.response.send_message(embed=embed)


@client.tree.context_menu(name='Account age')
async def account_age(interaction: bisim.Interaction, user: bisim.User) -> None:
    created = user.created_at.strftime('%Y-%m-%d')
    await interaction.response.send_message(f'{user.display_name} joined Bisim on {created}.', ephemeral=True)
```

- `bisim.Message` makes a message command.
- `bisim.Member`, `bisim.User` or `Union[bisim.Member, bisim.User]` makes a user command. Use `bisim.Member`
  when you need roles or the join date; it is a member in a server.

They are answered like any other command (see [Responding to commands](responding.md)) and synced with the
rest of the tree (see [Registering and syncing](syncing.md)).

## Names

Unlike slash commands, a context menu name may have capitals and spaces: 1 to 32 characters. Without
`name=`, the function's name is used in title case, so `account_age` becomes `Account_Age`; passing a name is
usually nicer. Context menu commands have no description.

## Permissions and errors

The same decorators as for slash commands work here: `@app_commands.default_permissions(...)`,
`@app_commands.guild_only()` and checks such as `@app_commands.checks.has_permissions(...)`. Put them under
`@client.tree.context_menu(...)`:

```python
@client.tree.context_menu(name='Delete and warn')
@app_commands.default_permissions(manage_messages=True)
@app_commands.guild_only()
async def delete_and_warn(interaction: bisim.Interaction, message: bisim.Message) -> None:
    await message.delete()
    await interaction.response.send_message(f'Deleted a message by {message.author.mention}.', ephemeral=True)


@delete_and_warn.error
async def delete_and_warn_error(interaction: bisim.Interaction, error: app_commands.AppCommandError) -> None:
    await interaction.response.send_message('I could not delete that message.', ephemeral=True)
```

See [Permissions and checks](permissions.md) for the whole picture.

## In a cog

A context menu cannot be defined as a method in a class. In a [cog](../commands/cogs.md), create it in
`__init__` with `app_commands.ContextMenu` and a bound method, add it to the tree, and remove it when the cog
is unloaded:

```python
from bisim.ext import commands


class Reports(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.report_menu = app_commands.ContextMenu(name='Report message', callback=self.report)
        self.bot.tree.add_command(self.report_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.report_menu.name, type=self.report_menu.type)

    async def report(self, interaction: bisim.Interaction, message: bisim.Message) -> None:
        await interaction.response.send_message('Thanks, the moderators will have a look.', ephemeral=True)
```

## Limits

Up to 5 message commands and 5 user commands per scope (global, or one server); `add_command()` raises
`app_commands.CommandLimitReached` past that. They count towards the 100 commands Bisim keeps per scope.

The `ContextMenu` class is in the [API reference](../../reference/app-commands.md).
