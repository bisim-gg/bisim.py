# Options and choices

A command's options are the parameters of its function, after the interaction. The type annotation decides
what kind of option Bisim shows, and the value arrives already converted:

```python
@client.tree.command(description='Give a member some points')
async def give(interaction: bisim.Interaction, member: bisim.Member, points: int, reason: str) -> None:
    await interaction.response.send_message(f'{member.mention} got {points} points: {reason}')
```

| Annotation | Option on Bisim | What the function receives |
| --- | --- | --- |
| `str` | text | `str` |
| `int` | whole number | `int` |
| `float` | number | `float` |
| `bool` | true or false | `bool` |
| `bisim.User`, `bisim.Member` | a user | `Member` in a server, `User` in a DM |
| `bisim.Role` | a role | `Role` |
| `bisim.abc.GuildChannel`, `bisim.TextChannel`, `bisim.VoiceChannel`, `bisim.CategoryChannel` | a channel, of those kinds only | the channel |
| `Union[bisim.Member, bisim.Role]` | a user or a role | `Member`, `User` or `Role` |
| `bisim.Attachment` | a file the member uploads | `Attachment` |

Every parameter needs an annotation; one without raises `TypeError` when the command is defined. Bisim has
text, voice and category channels, so those are the channel kinds an option can ask for.

!!! note
    `bisim.Member` only accepts members. If the command also runs in the DM with the bot, annotate
    `Union[bisim.Member, bisim.User]`: you get a `Member` in a server and a `User` in the DM.

## Optional options and defaults

An option with a default is optional. `Optional[...] = None` is the usual way:

```python
@client.tree.command(description='Show a member')
async def whois(interaction: bisim.Interaction, member: Optional[bisim.Member] = None) -> None:
    member = member or interaction.user
    await interaction.response.send_message(f'{member.display_name} joined at {member.joined_at}')
```

Bisim wants the required options before the optional ones; bisim.py orders them for you.

## Descriptions

Each option shows a description of up to 100 characters. Give it with `@app_commands.describe`, or in the
docstring (Google, NumPy and Sphinx styles are read):

```python
@client.tree.command()
@app_commands.describe(member='The member to warn', reason='Why, in a few words')
async def warn(interaction: bisim.Interaction, member: bisim.Member, reason: str) -> None:
    """Warn a member."""
    await interaction.response.send_message(f'{member.mention} was warned: {reason}')
```

## Renaming an option

The option's name is the parameter's name. To show another one, for example a word that is reserved in
Python, use `@app_commands.rename`. Other decorators still use the parameter's name:

```python
@client.tree.command(description='Pick a colour for your role')
@app_commands.rename(colour_hex='colour')
@app_commands.describe(colour_hex='A colour like #c8f53c')
async def paint(interaction: bisim.Interaction, colour_hex: str) -> None:
    await interaction.response.send_message(f'Your colour is now {colour_hex}.', ephemeral=True)
```

Option names follow the same rule as command names: 1 to 32 characters of `a` to `z`, digits, `-` and `_`.

## Ranges

`app_commands.Range` limits a number, or the length of a text:

```python
@client.tree.command(description='Roll some dice')
async def roll(
    interaction: bisim.Interaction,
    dice: app_commands.Range[int, 1, 20],
    sides: app_commands.Range[int, 2, 100] = 6,
    label: Optional[app_commands.Range[str, 1, 30]] = None,
) -> None:
    results = [random.randint(1, sides) for _ in range(dice)]
    await interaction.response.send_message(f'{label or "Roll"}: {sum(results)}')
```

`Range[int, 10]` sets only a minimum and `Range[int, None, 10]` only a maximum. Bisim refuses values outside
the range before the command reaches your bot.

## Fixed choices

When only a few values make sense, offer them as choices (up to 25, each name up to 100 characters):

```python
from bisim.app_commands import Choice


@client.tree.command(description='Order a drink')
@app_commands.choices(drink=[
    Choice(name='Tea', value='tea'),
    Choice(name='Coffee', value='coffee'),
    Choice(name='Doogh', value='doogh'),
])
async def order(interaction: bisim.Interaction, drink: Choice[str]) -> None:
    await interaction.response.send_message(f'One {drink.name}, coming up.')
```

Annotated with `Choice[str]` (or `Choice[int]`, `Choice[float]`) the function receives the chosen `Choice`;
annotated with `str` it receives only the value. Two shorter ways give the same result:

```python
@client.tree.command(description='Choose a size')
async def size(interaction: bisim.Interaction, size: Literal['small', 'medium', 'large']) -> None:
    await interaction.response.send_message(f'You chose {size}.')


class Speed(enum.Enum):
    slow = 1
    normal = 2
    fast = 3


@client.tree.command(description='Set the speed')
async def speed(interaction: bisim.Interaction, speed: Speed) -> None:
    await interaction.response.send_message(f'Speed set to {speed.name}.')
```

For choices that depend on what the member types, use [autocomplete](autocomplete.md) instead.

## Transformers

A transformer turns the text a member typed into any object you like. Subclass `app_commands.Transformer` and
annotate the parameter with `app_commands.Transform`:

```python
class Point(typing.NamedTuple):
    x: int
    y: int


class PointTransformer(app_commands.Transformer):
    async def transform(self, interaction: bisim.Interaction, value: str) -> Point:
        x, _, y = value.partition(',')
        return Point(x=int(x.strip()), y=int(y.strip()))


@client.tree.command(description='Plot a point, written like 3, 4')
async def plot(interaction: bisim.Interaction, point: app_commands.Transform[Point, PointTransformer]) -> None:
    await interaction.response.send_message(f'x={point.x}, y={point.y}')
```

When `transform()` raises, the error handlers get an `app_commands.TransformerError`. A transformer can also
set `type`, `min_value`, `max_value` and `choices`, or implement `autocomplete()`. All of these are in the
[API reference](../../reference/app-commands.md).
