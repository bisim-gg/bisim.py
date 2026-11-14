# Converters

Every argument of a prefix command arrives as text. A **converter** turns it into what the command needs, and you
choose one with the parameter's annotation. If a conversion fails, the command does not run and
`on_command_error` receives a `commands.BadArgument` (or one of its subclasses).

## Basic types

Any callable that takes a string works as a converter, so the built-in types do:

```python
@bot.command()
async def add(ctx: commands.Context, a: int, b: float) -> None:
    await ctx.send(f'{a} + {b} = {a + b}')
```

`bool` is special: `yes`, `y`, `true`, `t`, `1`, `enable` and `on` are `True`; `no`, `n`, `false`, `f`, `0`,
`disable` and `off` are `False`, in any letter case. Anything else raises `commands.BadBoolArgument`.

A function of your own works the same way:

```python
def lowercase(argument: str) -> str:
    return argument.lower()


@bot.command()
async def tag(ctx: commands.Context, name: lowercase) -> None:
    await ctx.send(f'Looking for {name}')
```

## Bisim objects

Annotate with a Bisim class and the argument is looked up for you. An ID and a mention always work; most also accept
a name:

| Annotation | Accepts |
| --- | --- |
| `bisim.Member` | ID, mention, username, display name or nickname, in the current server |
| `bisim.User` | ID, mention, username or display name |
| `bisim.TextChannel`, `bisim.VoiceChannel`, `bisim.CategoryChannel` | ID, mention, link or name |
| `bisim.abc.GuildChannel` | any of the three |
| `bisim.Role` | ID, mention or name |
| `bisim.Message`, `bisim.PartialMessage` | ID, `channel_id-message_id` or a message link |
| `bisim.Guild` | ID or name of a server the bot is in |
| `bisim.Emoji` | a server emoji (`<:name:id>`), its ID or its name |
| `bisim.PartialEmoji` | a custom emoji written `<:name:id>` |
| `bisim.GuildSticker` | ID or name |
| `bisim.Invite` | an invite link or code |
| `bisim.Colour` | `#1a66d6`, `0x1a66d6`, `rgb(26, 102, 214)` or a name such as `red` |
| `bisim.Game` | any text, as the game's name |
| `bisim.Object` | an ID or a mention, without a lookup |

```python
@bot.command()
@commands.guild_only()
async def avatar(ctx: commands.Context, member: bisim.Member) -> None:
    await ctx.send(member.display_avatar.url)
```

Each one is also a class you can use directly or subclass, such as `commands.MemberConverter`.

## Optional, Union and Literal

`typing.Optional[X]` tries `X`; if the word does not convert, the parameter gets `None` (or its default) and the
word is left for the next parameter. `typing.Union` tries each type in order. `typing.Literal` accepts only the
values listed:

```python
from typing import Literal, Optional, Union


@bot.command()
async def slap(ctx: commands.Context, member: Optional[bisim.Member] = None, *, reason: str = 'no reason') -> None:
    member = member or ctx.author
    await ctx.send(f'{ctx.author.display_name} slaps {member.display_name} for {reason}.')


@bot.command()
async def info(ctx: commands.Context, target: Union[bisim.Member, bisim.Role]) -> None:
    await ctx.send(f'{target.name}: {target.id}')


@bot.command()
async def shop(ctx: commands.Context, action: Literal['buy', 'sell'], amount: int = 1) -> None:
    await ctx.send(f'{action} {amount}')
```

## Greedy and Range

`commands.Greedy[X]` keeps converting words to `X` until one fails, and gives you a list. `commands.Range` limits a
number, or the length of a string:

```python
import random


@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx: commands.Context, members: commands.Greedy[bisim.Member], *, reason: str = 'no reason given') -> None:
    for member in members:
        await member.kick(reason=reason)
    await ctx.send(f'Kicked {len(members)} members.')


@bot.command()
async def roll(ctx: commands.Context, sides: commands.Range[int, 2, 100] = 6) -> None:
    await ctx.send(str(random.randint(1, sides)))
```

`!kick @a @b @c being rude` passes three members and the reason. A value out of range raises `commands.RangeError`.

## Files

A parameter annotated `bisim.Attachment` takes a file attached to the message, and `Optional[bisim.Attachment]`
one that may be missing. A missing required file raises `commands.MissingRequiredAttachment`.

## Converters of your own

For a conversion that needs the context, subclass `commands.Converter` and write an async `convert`:

```python
class Duration(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> int:
        units = {'s': 1, 'm': 60, 'h': 3600}
        try:
            return int(argument[:-1]) * units[argument[-1]]
        except (ValueError, KeyError):
            raise commands.BadArgument(f'{argument} is not a duration like 10m or 2h.')


@bot.command()
async def remind(ctx: commands.Context, when: Duration, *, text: str) -> None:
    await ctx.send(f'I will remind you in {when} seconds.')
```

`commands.clean_content` is a ready made one: it turns mentions into plain names, so the bot does not ping people
when it repeats the text.

## Defaults and names with `commands.parameter`

`commands.parameter()` (or its short name `commands.param()`) sets a converter, a default, a description and the
name or default shown in help. A callable default is called with the context, so it can depend on who ran the
command:

```python
@bot.command()
async def wave(ctx: commands.Context, to: bisim.User = commands.parameter(default=lambda ctx: ctx.author)) -> None:
    await ctx.send(f'Hello {to.mention}!')
```

`commands.Author`, `commands.CurrentChannel` and `commands.CurrentGuild` are ready made defaults:
`member: bisim.Member = commands.Author`.

!!! note
    discord.py's `FlagConverter` and hybrid commands are not in bisim.py. Use keyword-only parameters or converters
    for options, and `app_commands` for [slash commands](../slash-commands/index.md).

The converter classes are in the [API reference](../../reference/ext-commands.md).
