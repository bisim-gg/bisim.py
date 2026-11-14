# Subcommands and groups

A group gathers related commands under one name: `/note save`, `/note show` and `/note delete` instead of
three separate commands. On Bisim, as on Discord, the group itself cannot be run; only its subcommands can.

## A group as a class

Subclass `app_commands.Group`. Its name and description come from the class keywords (or from the class name
and docstring), and every method decorated with `@app_commands.command()` becomes a subcommand:

```python
from typing import Dict, List

import bisim
from bisim import app_commands


class Notes(app_commands.Group, name='note', description='Save short notes and show them later'):
    def __init__(self) -> None:
        super().__init__()
        self.notes: Dict[str, str] = {}

    @app_commands.command(description='Save a note')
    async def save(self, interaction: bisim.Interaction, name: str, text: str) -> None:
        self.notes[name.lower()] = text
        await interaction.response.send_message(f'Saved **{name}**.', ephemeral=True)

    @app_commands.command(description='Show a note')
    async def show(self, interaction: bisim.Interaction, name: str) -> None:
        await interaction.response.send_message(self.notes.get(name.lower(), 'There is no such note.'))


client.tree.add_command(Notes())
```

Without `name=`, a class `TodoList` becomes the group `todo-list`. The group's state lives on the instance,
like `self.notes` here.

## A group without a class

For a few commands, create a `Group` and decorate functions with its `command()`:

```python
tags = app_commands.Group(name='tag', description='Short texts the server can recall')


@tags.command(description='Show a tag')
async def show(interaction: bisim.Interaction, name: str) -> None:
    await interaction.response.send_message(f'Tag {name}')


@tags.command(name='list', description='List every tag')
async def list_tags(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('No tags yet.')


client.tree.add_command(tags)
```

## Nested groups

A group can hold other groups, one level deep: `/settings welcome set` is a group (`settings`), a subgroup
(`welcome`) and a subcommand (`set`). Pass `parent=` to create the subgroup:

```python
settings = app_commands.Group(name='settings', description='Change how the bot behaves here')
welcome = app_commands.Group(name='welcome', description='The welcome message', parent=settings)


@welcome.command(name='set', description='Set the welcome message')
async def welcome_set(interaction: bisim.Interaction, text: str) -> None:
    await interaction.response.send_message(f'New members will read: {text}', ephemeral=True)


@welcome.command(name='off', description='Turn the welcome message off')
async def welcome_off(interaction: bisim.Interaction) -> None:
    await interaction.response.send_message('Welcome message turned off.', ephemeral=True)


client.tree.add_command(settings)
```

In a class, a subgroup is a class attribute: `welcome = app_commands.Group(name='welcome', description='...')`,
and its commands use `@welcome.command()`. A group nested deeper than that raises `ValueError`.

## Settings that belong to the group

- `@app_commands.guild_only()`, `@app_commands.default_permissions(...)` and `@app_commands.guilds(...)`
  apply to the whole group: put them on the class (or pass `guild_only=` and `default_permissions=` to
  `Group`). Bisim keeps them for the top level command only: on a subcommand `guild_only` and
  `default_permissions` are ignored, and `guilds` raises `ValueError`.
- Override `interaction_check()` on the group to run a check before any of its subcommands.
- Override `on_error()`, or decorate a function with `@group.error`, to handle the errors of every
  subcommand. See [Permissions and checks](permissions.md).

## Groups in cogs

With `bisim.ext.commands`, a `GroupCog` is a [cog](../commands/cogs.md) whose app commands form one group:

```python
from bisim.ext import commands


class Todo(commands.GroupCog, group_name='todo', group_description='A small to do list'):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.items: Dict[int, List[str]] = {}

    @app_commands.command(description='Add something to your list')
    async def add(self, interaction: bisim.Interaction, item: str) -> None:
        self.items.setdefault(interaction.user.id, []).append(item)
        await interaction.response.send_message('Added.', ephemeral=True)


# In setup_hook or an extension's setup function:
# await bot.add_cog(Todo(bot))
```

## Limits

- Up to 25 subcommands and subgroups in a group.
- Two levels at most: group, subgroup, subcommand.
- A group counts as one of the 100 commands of its scope.
- Names follow the same rule as command names, and every group needs a description.

The classes are described in the [API reference](../../reference/app-commands.md).
