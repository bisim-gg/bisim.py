# The help command

`commands.Bot` comes with a `help` command. `!help` lists the commands, grouped by [cog](cogs.md); `!help roll`
shows one command and `!help Todo` one cog. Its text comes from your code, so good help starts with good
docstrings.

## Where the text comes from

```python
@bot.command(aliases=['dice'], brief='Rolls dice')
async def roll(ctx: commands.Context, dice: str = '1d6') -> None:
    """Rolls dice written like 2d6: two dice with six sides.

    Up to 20 dice with 2 to 100 sides each.
    """
```

- `help` is the long text shown by `!help roll`. It defaults to the function's docstring.
- `brief` is the short line in the list; without it, the first line of `help` is used.
- `description` is shown above the long text, and `usage` replaces the generated list of arguments.
- The signature, here `roll [dice=1d6]`, is generated from the parameters. `commands.parameter(description=...)`
  describes an argument, and `displayed_name=` and `displayed_default=` change how it is shown.
- `hidden=True` keeps a command out of the list; it still works.
- A cog's docstring describes the cog, and `commands.Bot(description=...)` is shown at the top of `!help`.

By default the list shows only the commands the person may run: checks are tried, and a command whose checks fail is
left out.

## The two ready made help commands

`commands.DefaultHelpCommand` is the default: a code block with the commands under their cogs.
`commands.MinimalHelpCommand` is plainer, without the code block. Pass either one, with options, to the bot:

```python
bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    help_command=commands.DefaultHelpCommand(no_category='Other', sort_commands=True, dm_help=False),
)
```

| Option | What it does |
| --- | --- |
| `no_category` | the heading for commands outside any cog (`"No Category"`) |
| `sort_commands` | list the commands alphabetically (`True`) |
| `dm_help` | `True` sends the help by DM, `None` only when it is long, `False` never (the default) |
| `show_hidden` | list hidden commands too (`False`) |
| `verify_checks` | leave out the commands whose checks fail (`True`) |
| `command_attrs` | options for the help command itself, such as `{'name': 'commands', 'aliases': ['h']}` |
| `commands_heading`, `arguments_heading` | headings, useful for a Persian help (`DefaultHelpCommand`) |
| `width` | the line width of `DefaultHelpCommand` (80) |

`help_command=None` removes the help command, and `bot.help_command = ...` replaces it while the bot runs.

## A help command of your own

Subclass `commands.HelpCommand` and override what you want to change. Each method sends one view of the help, and
`self.context` is the context of the `!help` message:

```python
class EmbedHelp(commands.HelpCommand):
    def get_destination(self):
        return self.context.channel

    async def send_bot_help(self, mapping) -> None:
        embed = bisim.Embed(title='Commands', colour=bisim.Colour.blurple())
        for cog, cmds in mapping.items():
            visible = await self.filter_commands(cmds, sort=True)
            if visible:
                name = cog.qualified_name if cog else 'Other'
                embed.add_field(name=name, value=' '.join(f'`{c.name}`' for c in visible), inline=False)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog) -> None:
        commands_ = await self.filter_commands(cog.get_commands(), sort=True)
        lines = [f'`{self.get_command_signature(c)}` {c.short_doc}' for c in commands_]
        await self.get_destination().send('\n'.join(lines) or 'Nothing here.')

    async def send_group_help(self, group) -> None:
        await self.send_command_help(group)

    async def send_command_help(self, command) -> None:
        embed = bisim.Embed(title=self.get_command_signature(command), description=command.help or 'No help yet.')
        if command.aliases:
            embed.add_field(name='Aliases', value=', '.join(command.aliases))
        await self.get_destination().send(embed=embed)


bot.help_command = EmbedHelp()
```

| Method | Called for |
| --- | --- |
| `send_bot_help(mapping)` | `!help`; `mapping` maps each cog (or `None`) to its commands |
| `send_cog_help(cog)` | `!help CogName` |
| `send_group_help(group)` | `!help group` |
| `send_command_help(command)` | `!help command` |
| `send_error_message(error)` | an unknown command or subcommand; by default it sends the error text |
| `get_destination()` | where the help goes; the channel by default |

`filter_commands` applies `show_hidden` and `verify_checks` for you, `get_command_signature` builds the usage line
and `command.short_doc` is the brief line. To use the help from code, `await ctx.send_help()` sends the bot's help
and `await ctx.send_help(command)` that of one command.

To keep the help in a cog, set `bot.help_command.cog = self` in the cog's `__init__`; it then appears under that cog.

The help classes are in the [API reference](../../reference/ext-commands.md).
