# Slash commands

Slash commands are what members type after `/` in a channel. Each one has a name and a description, and it
can take options, have subcommands and ask for permissions. In bisim.py they live in `bisim.app_commands`,
exactly as in discord.py: you write an `async` function, decorate it, and a `CommandTree` sends it to Bisim
and runs it when someone uses it.

## A first command

```python
import os

import bisim
from bisim import app_commands


class MyClient(bisim.Client):
    def __init__(self) -> None:
        super().__init__(intents=bisim.Intents.default())
        # One tree per client: it holds the commands and runs them.
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        # Runs once after logging in: send the commands to Bisim.
        await self.tree.sync()


client = MyClient()


@client.tree.command()
async def ping(interaction: bisim.Interaction) -> None:
    """Check that the bot is alive."""
    await interaction.response.send_message(f'Pong! {round(client.latency * 1000)} ms')


client.run(os.environ['BISIM_TOKEN'])
```

Run it, type `/ping` in a channel the bot can see, and the bot answers. The first parameter of every command
is the `bisim.Interaction`; everything you need to answer is on it.

If you use `bisim.ext.commands`, the bot already has a tree: use `@bot.tree.command()` and
`await bot.tree.sync()`.

## Names and descriptions

- The **name** is the function's name unless you pass `name=`. Bisim accepts 1 to 32 characters made of
  lower case letters `a` to `z`, digits, `-` and `_`. Anything else raises `ValueError` as soon as the
  command is defined, so you find out before syncing.
- The **description** is `description=`, or else the first paragraph of the docstring. Bisim allows 1 to 100
  characters; a longer docstring is shortened to 100. A command with neither shows `…`.
- Persian names and descriptions are added as translations; see [Translating commands](translations.md).

```python
@client.tree.command(name='server-info', description='Show this server\'s name and member count')
@app_commands.guild_only()
async def server_info(interaction: bisim.Interaction) -> None:
    guild = interaction.guild
    await interaction.response.send_message(f'{guild.name} has {guild.member_count} members.')
```

Other keyword arguments of `tree.command()`: `guild=` or `guilds=` makes it a server command instead of a
global one (see [Registering and syncing](syncing.md)), and `extras=` is a dictionary the library never
touches. `nsfw=` is accepted for compatibility, but Bisim does not use it.

You can also define a command on its own with `@app_commands.command()` and add it later with
`client.tree.add_command(...)`; this is how commands in a separate module or a cog are written.

## Where commands run

Bisim runs slash commands in server text channels and in the DM with the bot. A member needs the **Use
Application Commands** permission in the channel and must not be timed out. A global command exists only in
the servers the bot has been added to. To keep a command to servers or to DMs, see
[Permissions and checks](permissions.md).

## In this section

- [Registering and syncing](syncing.md): sending your commands to Bisim, globally or to one server.
- [Responding to commands](responding.md): answering, ephemeral messages, deferring and followups.
- [Options and choices](options.md): typed parameters, descriptions, ranges and fixed choices.
- [Autocomplete](autocomplete.md): suggestions while the member types.
- [Subcommands and groups](groups.md): `/note save`, `/note show` and nested groups.
- [Context menus](context-menus.md): commands on a message's or a user's menu.
- [Permissions and checks](permissions.md): who may run a command, and handling errors.
- [Translating commands](translations.md): Persian and English names and descriptions.

Every class and decorator is in the [API reference](../../reference/app-commands.md).
